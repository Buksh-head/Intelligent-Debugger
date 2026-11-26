"""Stage 2: respond to the student's reply to a hint question.

The student answers the stage 1 question in their own words. The model reads
the reply, decides how close the student is (found_it / partly / wrong_idea /
unsure / off_topic) and branches:

* found_it            -> a short answer confirming the cause and explaining it
* partly              -> a narrower question about the missing part
* wrong_idea          -> a question from a different angle that tests their idea
* unsure / off_topic  -> a smaller, more concrete question

The student can reply to each follow-up question. After MAX_FOLLOWUP_QUESTIONS
follow-up questions the tool gives an answer whatever the reply was, so a
student is never left going round in circles.

Every response goes through the same kind of deterministic checks as stage 1
(no fix, no giveaway names, anchored to the code); one retry with the
checker's feedback, then a rule-based response.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from .analysis import ErrorReport, analyse
from .explain import explain
from .fallback import followup_fallback, logic_explanation, logic_followup_fallback, logic_reply_found_it
from .guardrails import (
    MAX_FOLLOWUP_QUESTION_WORDS,
    _IDENT_RE,
    check_answer,
    check_question,
    new_code_problems,
    repeats_earlier_question,
    tone_problems,
    visible_error_text,
)
from .prompts import (
    FOLLOWUP_PROMPT_VERSION,
    FOLLOWUP_SYSTEM_PROMPT,
    MAX_FOLLOWUP_QUESTIONS,
    build_followup_message,
)
from .providers import HintModel, default_hint_model, record_model_seconds
from .runner import RunResult

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2
Assessment = Literal["found_it", "partly", "wrong_idea", "unsure", "off_topic"]


class FollowUpDraft(BaseModel):
    """What the model returns. Only `text` is shown to the student."""

    assessment: Assessment = Field(description="How close the student's latest reply is to the real cause.")
    assessment_reason: str = Field(description="One sentence for teachers. Never shown to the student.")
    root_cause: str = Field(description="One sentence for teachers. Never shown to the student.")
    cause_line: int = Field(description="Line number the student should look at.")
    giveaways: list[str] = Field(description="Words or identifiers that would give away the fix.")
    response_type: Literal["question", "answer"] = Field(description="Whether text is a question or an answer.")
    text: str = Field(description="What the student sees.")


@dataclass
class FollowUp:
    kind: str                    # "question" | "answer"
    text: str
    assessment: str              # see Assessment; "unknown" for rule-based responses
    cause_line: int | None
    source: str                  # "model" | "fallback"
    turn: int                    # 1 = first follow-up
    final: bool                  # True when no more replies are expected
    internal: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def followup_for_run(
    run: RunResult, turns: list[tuple[str, str]], model: HintModel | None = None,
    expected: str | None = None,
) -> FollowUp | None:
    """`turns`: every (question, reply) so far, oldest first; the last reply is the one
    to respond to. `expected`: the output the student expected, for logic errors.
    Returns None when the run had no error."""
    from .hints import report_for_run

    report = report_for_run(run, expected)
    if not report.has_error:
        return None
    return followup_for_report(run.code, report, turns, model=model)


def followup_for_report(
    code: str, report: ErrorReport, turns: list[tuple[str, str]], model: HintModel | None = None
) -> FollowUp:
    turn = len(turns)  # the stage 1 question is turns[0], so this is the follow-up number
    final = turn >= MAX_FOLLOWUP_QUESTIONS
    replies = [r for _, r in turns]
    earlier_questions = [q for q, _ in turns]
    # Words the student wrote themselves (their failing line and their replies) may be quoted back.
    student_words = set(_IDENT_RE.findall(report.line_text or "")) | set(
        _IDENT_RE.findall(report.details.get("expected", "") if report.kind == "logic" else "")) | {
        w for r in replies for w in _IDENT_RE.findall(r)
    }
    if model is None:
        model = default_hint_model()
    internal: dict[str, Any] = {
        "prompt_version": FOLLOWUP_PROMPT_VERSION,
        "model": model.name if model else None,
        "turns": [{"question": q, "reply": r} for q, r in turns],
    }
    if model is None:
        internal["fallback_reason"] = "no API key configured for the chosen provider"
        return _fallback(report, turns, turn, final, student_words, internal)

    feedback: str | None = None
    rejected: list[dict[str, Any]] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = perf_counter()
        try:
            draft = model.structured(
                FOLLOWUP_SYSTEM_PROMPT,
                build_followup_message(code, report, turns, final, feedback),
                FollowUpDraft,
            )
        except Exception as exc:  # network, auth, refusal, schema: never leave the student with nothing
            record_model_seconds(internal, started)
            log.warning("stage 2 model call failed: %s", exc)
            internal["fallback_reason"] = f"model call failed: {type(exc).__name__}: {exc}"
            break
        record_model_seconds(internal, started)
        problems = _check(draft, report, code, final, student_words, earlier_questions)
        if not problems:
            log.info("stage 2 %s (%s) from %s on attempt %d", draft.response_type, draft.assessment,
                     model.name, attempt)
            internal.update(assessment_reason=draft.assessment_reason, root_cause=draft.root_cause,
                            giveaways=sorted(set(draft.giveaways)), attempts=attempt, rejected=rejected)
            is_answer = draft.response_type == "answer"
            return FollowUp(kind=draft.response_type, text=draft.text.strip(), assessment=draft.assessment,
                            cause_line=draft.cause_line, source="model", turn=turn,
                            final=is_answer, internal=internal)
        log.warning("stage 2 attempt %d rejected: %r -> %s", attempt, draft.text, "; ".join(problems))
        rejected.append({"text": draft.text, "assessment": draft.assessment, "problems": problems})
        feedback = "\n".join(f"- {p}" for p in problems)
    else:
        internal["fallback_reason"] = "model responses failed the guardrails"
    internal["rejected"] = rejected
    return _fallback(report, turns, turn, final, student_words, internal)


def _check(draft: FollowUpDraft, report: ErrorReport, code: str, final: bool,
           student_words: set[str], earlier_questions: list[str]) -> list[str]:
    giveaways = set(report.giveaways) | {g for g in draft.giveaways if g}
    visible = visible_error_text(report.error_type, report.message) if report.kind != "logic" else ""
    problems: list[str] = []
    should_answer = final or draft.assessment == "found_it"
    if should_answer and draft.response_type != "answer":
        problems.append("Write an answer here (the student found the cause, or this is the last follow-up).")
    if not should_answer and draft.response_type != "question":
        problems.append(f"For the assessment '{draft.assessment}', write a question, not an answer.")
    problems += tone_problems(draft.text)
    if draft.response_type == "answer":
        # On the last follow-up the answer may name things; it still must not write the fix as code.
        problems += check_answer(draft.text, giveaways=set() if final else giveaways, code=code,
                                 allowed_words=student_words, visible_text=visible)
    else:
        problems += check_question(draft.text, giveaways=giveaways, code=code,
                                   student_line_text=" ".join(sorted(student_words)),
                                   max_words=MAX_FOLLOWUP_QUESTION_WORDS, visible_text=visible)
        if repeats_earlier_question(draft.text, earlier_questions):
            problems.append("It repeats an earlier question; ask something more specific.")
    if report.kind == "logic":
        # The fix for a logic error is usually a tiny piece of code; never write it out.
        problems += new_code_problems(draft.text, code)
    return problems


def _fallback(report: ErrorReport, turns: list[tuple[str, str]], turn: int, final: bool,
              student_words: set[str], internal: dict[str, Any]) -> FollowUp:
    """No model, or its responses failed the checks. Without a model the reply can't be
    understood reliably, so: if the reply names a giveaway or the cause line's own words
    plus a hint of the problem, treat it as found; otherwise step down to a more concrete
    question, and on the last turn explain the error plainly."""
    log.warning("stage 2 used the rule-based response: %s", internal.get("fallback_reason"))
    reply = turns[-1][1] if turns else ""
    line = report.line
    found = any(
        re.search(rf"(?<![A-Za-z0-9_]){re.escape(g)}(?![A-Za-z0-9_])", reply) for g in report.giveaways
    ) or (report.kind == "logic" and logic_reply_found_it(report, reply))
    if found or final:
        friendly = explain(report)
        lead = "Yes, you've got it. " if found else "You've worked hard on this one, so here's what's going on. "
        where = (f" Have a go at changing line {line}, then run it again." if line
                 else " Have a go at changing it, then run it again.")
        body = logic_explanation(report) if report.kind == "logic" else (friendly.message if friendly else "")
        text = f"{lead}{body}{where}".strip()
        return FollowUp(kind="answer", text=text, assessment="found_it" if found else "unknown",
                        cause_line=line, source="fallback", turn=turn, final=True, internal=internal)
    question = logic_followup_fallback(report, turn) if report.kind == "logic" else followup_fallback(report, turn)
    return FollowUp(kind="question", text=f"{_fallback_lead(reply, turn)} {question}", assessment="unknown",
                    cause_line=line, source="fallback", turn=turn, final=False, internal=internal)


# Without a model the reply can't be understood, so the opening only reacts to the
# kind of reply that is easy to spot, and otherwise stays neutral. It never claims
# the reply helped or was close, since it can't know that.
_UNSURE_RE = re.compile(
    r"\b(i ?d(?:on'?t|unno)|idk|dunno|no idea|not sure|unsure|no clue|confused|lost|help|"
    r"don'?t (?:know|get it|understand))\b|^\W*\?+\W*$",
    re.IGNORECASE,
)
_ASKS_FOR_ANSWER_RE = re.compile(
    r"\b(just )?(tell|give|show) me\b|\bwhat(?:'s| is) the (answer|fix)\b", re.IGNORECASE
)
_UNSURE_LEADS = [
    "That's okay, this one catches a lot of people out. Let's take a smaller step.",
    "No worries, let's make it even smaller.",
]
_ANSWER_LEADS = [
    "I'd rather help you spot it yourself, because it'll stick better. Let's take a small step.",
    "I know it's frustrating. Let's try one small thing first.",
]
_NEUTRAL_LEADS = [
    "Okay, let's look at it from a slightly different angle.",
    "Alright, let's narrow it down a bit more.",
]


def _fallback_lead(reply: str, turn: int) -> str:
    if _ASKS_FOR_ANSWER_RE.search(reply):
        leads = _ANSWER_LEADS
    elif _UNSURE_RE.search(reply) or len(reply.split()) <= 2:
        leads = _UNSURE_LEADS
    else:
        leads = _NEUTRAL_LEADS
    return leads[(turn - 1) % len(leads)]
