"""Classifies a student's reply against the specific task given for the
current debugging stage, so the backend knows whether to advance, hold,
or soft-advance the stage (see issues #11, #60).
"""
from enum import IntEnum
from typing import Literal, NamedTuple
import logging

from openai import OpenAI
from pydantic import BaseModel
import os

logger = logging.getLogger(__name__)

# Number of vague replies in a row at the same stage, before soft-advancing
MAX_VAGUE_ATTEMPTS = 2  


class Stage(IntEnum):
    """
    Current Stage the student is on
    """
    NOTICE = 1
    UNDERSTAND = 2
    LOCATE = 3
    CONCEPTUAL_FIX = 4
    REDIRECT = 5


class ClassificationResult(BaseModel):
    """
    The classification of the student's response by the LLM
    Contains the classified intent and the student's raw response
    """
    intent: str
    raw_response: str


class StageDecision(NamedTuple):
    """Returned by resolve_next_stage. A NamedTuple rather than a bare
    tuple so adding a field later doesn't silently break call sites that
    unpack positionally."""
    next_stage: int
    next_vague_attempts: int
    advanced: bool
    advanced_softly: bool
    clear_gate: bool


# The type of intention classifications that the model can classify the student's response into
INTENT = Literal[
    "genuinely_completed",
    "vague_affirmation",
    "asking_analogy",
    "asking_question",
    "off_topic",
    "reviewed_resource",
    "skipped_resource",
]

# System prompt for the classification of every student response
_CLASSIFIER_SYSTEM_PROMPT = """You are classifying a student's reply during a guided debugging exercise.
Respond with ONLY one label, nothing else, no punctuation, no explanation."""

_client: OpenAI | None = None

VALID_INTENTS = set(INTENT.__args__)
GATE_INTENTS = {"reviewed_resource", "skipped_resource"}

def _get_client() -> OpenAI:
    """Lazily construct the client so importing this module (e.g. for unit
    tests of resolve_next_stage) never requires credentials to be present."""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ.get("GROQ_API_TOKEN"),
            base_url=os.environ.get("GROQ_API_URL"),
        )
    return _client

def _gate_prompt(student_message: str, check_prompt: str) -> str:
    """
    Gives the prompt for gating the student at a stage when a resource has been supplied.

    Parameters
    ----------
    student_message: str
        The response provided by the student
    
    check_prompt: str
        The question to ask the student to check if they understand the concept in the resource provided

    Returns
    --------
    str: The prompt
    """
    return f"""The student was asked to read a linked explainer and then answer this question: "{check_prompt}"

            Classify their reply into exactly one of these labels:
            - reviewed_resource: they give a specific, substantive answer showing they actually engaged with the material
            - skipped_resource: they claim to have read it ("done", "read it", "makes sense", "ok") with no substance, or clearly did not read it
            - asking_question: they are asking about the material rather than answering the question
            - off_topic: unrelated to the material or the debugging task

            Student message: "{student_message}"

            Respond with only the single label."""


def _stage_prompt(student_message: str, stage_task: str) -> str:
    """
    Gives the prompt for classifying the student's response at every stage.

    Parameters
    ----------
    student_message: str
        The response provided by the student
    
    stage_task: str
        The task that the student was asked to complete immediately before their response

    Returns
    --------
    str: The prompt
    """
    return f"""The student was asked: "{stage_task}"

            FIRST decide what kind of answer that task calls for:
            - If it asks a yes/no or either/or question, then a bare "yes" or "no" IS a complete answer.
            - If it asks them to go look at something and report what they found, then a reply with no specifics is incomplete.

            Then classify their reply into exactly one of these labels:
            - genuinely_completed: the reply actually answers what was asked. This INCLUDES a bare "yes"/"no" when a yes/no question was asked, and INCLUDES short factual statements about the code ("the name does not exist", "line 3", "it's empty", "nothing assigns it").
            - vague_affirmation: the student signals completion WITHOUT answering - "ok", "done", "got it", "I looked", "makes sense": when the task asked them to report something specific.
            - asking_analogy: student is confused and wants a simpler explanation or analogy.
            - asking_question: student is asking a clarifying question, not answering.
            - off_topic: unrelated to the debugging task.

            Examples:
            Task: "Did you create that variable earlier?" / Reply: "no" -> genuinely_completed
            Task: "What does a NameError mean?" / Reply: "the name does not exist" -> genuinely_completed
            Task: "Look at line 3 and tell me what you see." / Reply: "ok done" -> vague_affirmation
            Task: "What number are you asking for there?" / Reply: "I checked it" -> vague_affirmation

            Student message: "{student_message}"

            Respond with only the single label."""

def classify_student_message(
    student_message: str,
    stage_task: str,
    pending_check_prompt: str | None = None,
    model: str = "qwen/qwen3.8-27b",
) -> ClassificationResult:
    """Classifies student_message against the specific task given this stage.

    Parameters:
        student_message: the student's reply to classify
        stage_task: the specific task the student was asked to do this stage
        pending_check_prompt: if a resource was offered, the check prompt to classify against
        model: the model to use for classification
        
    Returns:
        ClassificationResult: the classification result, including the intent and raw response
    """
    gated = bool(pending_check_prompt)
    prompt = (
        _gate_prompt(student_message, pending_check_prompt)
        if gated
        else _stage_prompt(student_message, stage_task)
    )

    # API call to the LLM model to classify a student's message
    try:
        response = _get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=10,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip().lower()
    except Exception as e:
        logger.error(f"Stage classification failed: {e}")
        logger.error(f"Stage classification failed (gated={gated}): {e}")
        fallback = "skipped_resource" if gated else "vague_affirmation"
        # Fail safe: treat unclassifiable replies as vague rather than
        # silently advancing or silently blocking the student.
        return ClassificationResult(intent=fallback, raw_response="")

    if raw not in VALID_INTENTS:
        raw = "skipped_resource" if gated else "vague_affirmation"
    # A gate intent returned outside gate mode (or vice versa) is hallucination;
    # coerce rather than let it flow into resolve_next_stage.
    elif gated and raw not in GATE_INTENTS | {"asking_question", "off_topic"}:
        raw = "skipped_resource"
    elif not gated and raw in GATE_INTENTS:
        raw = "vague_affirmation"

    return ClassificationResult(intent=raw, raw_response=raw)


def resolve_next_stage(
    current_stage: int,
    vague_attempts_this_stage: int,
    intent: str,
    has_pending_resource: bool = False,
) -> StageDecision:
    """Given current state and this turn's classification, determine the next state of the hint system.
    
    Parameters:
        current_stage: the current stage of the hint system (1-5)
        vague_attempts_this_stage: the number of vague attempts made at the current stage
        intent: the classification of the student's response

    Returns:
        next_stage: the stage to move to next
        next_vague_attempts: the updated count of vague attempts
        advanced: whether the student has advanced to the next stage
        advanced_softly: whether the student has advanced softly (e.g., by reaching the vague attempt limit)

    Kept separate from any DB/request code so it's trivially unit-testable.
    """
    # Resource introduced: the stage cannot advance at all until student answers the question
    if has_pending_resource:
        if intent == "reviewed_resource":
            # Gate opens, stage does NOT advance: reading about a concept
            # is not the same as completing the stage's task.
            return StageDecision(current_stage, 0, False, False, True)

        if intent == "skipped_resource":
            next_vague = vague_attempts_this_stage + 1
            if next_vague >= MAX_VAGUE_ATTEMPTS:
                return StageDecision(current_stage, 0, False, True, True)
            return StageDecision(current_stage, next_vague, False, False, False)

        # asking_question / off_topic: hold, counters untouched.
        return StageDecision(current_stage, vague_attempts_this_stage, False, False, False)

    # The stage increment based off classification
    if intent == "genuinely_completed":
        if current_stage < Stage.REDIRECT:
            return StageDecision(current_stage + 1, 0, True, False, False)
        return StageDecision(current_stage, 0, False, False, False)

    if intent == "vague_affirmation":
        next_vague = vague_attempts_this_stage + 1
        if next_vague >= MAX_VAGUE_ATTEMPTS and current_stage < Stage.REDIRECT:
            return StageDecision(current_stage + 1, 0, True, True, False)
        return StageDecision(current_stage, next_vague, False, False, False)

    return StageDecision(current_stage, vague_attempts_this_stage, False, False, False)
