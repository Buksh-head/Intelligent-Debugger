"""Stage 1 hint generation: one leading question per error."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any

from .analysis import ErrorReport, analyse
from pydantic import Field

from .fallback import fallback_question, logic_fallback_question
from .guardrails import check_question, logic_giveaway_problems, new_code_problems, visible_error_text
from .logic import CATEGORIES, analyse_logic
from .prompts import LOGIC_PROMPT_VERSION, LOGIC_SYSTEM_PROMPT, PROMPT_VERSION, build_logic_message
from .providers import HintDraft, HintModel, default_hint_model, record_model_seconds
from .runner import RunResult, run_student_code

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2


@dataclass
class Stage1Hint:
    status: str                         # "hint" | "no_error"
    question: str | None = None         # what the student sees
    error_type: str | None = None
    error_message: str | None = None
    error_line: int | None = None
    cause_line: int | None = None
    source: str | None = None           # "model" | "fallback"
    # Logic errors only: off_by_one | recursion_base_case | calculation | other.
    category: str | None = None
    # Internal: for teachers, logs and the later hint stages. Not for the student.
    internal: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""

    def student_view(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "question": self.question,
            "error_type": self.error_type,
            # Python's own "Did you mean: 'x'?" suggestion is the answer; hold it back at stage 1.
            "error_message": strip_suggestion(self.error_message),
            "error_line": self.error_line,
            "cause_line": self.cause_line,
            "stdout": self.stdout,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SUGGESTION_RE = re.compile(r"\.?\s*(Did you mean|Maybe you meant)\b.*$")


def strip_suggestion(message: str | None) -> str | None:
    """Python's message without its 'Did you mean' / 'Maybe you meant' suggestion,
    which is the answer and is held back at stage 1."""
    if not message:
        return message
    return _SUGGESTION_RE.sub("", message).rstrip()


def generate_stage1_hint(code: str, stdin: str = "", model: HintModel | None = None) -> Stage1Hint:
    """Run the code, then write a stage 1 hint for whatever went wrong."""
    return hint_for_run(run_student_code(code, stdin=stdin), model=model)


def report_for_run(run: RunResult, expected: str | None = None):
    """The crash, timeout or (when the student gave their expected output) logic error in a run."""
    report = analyse(run)
    if report.has_error or expected is None or not run.ok:
        return report
    return analyse_logic(run.code, run.stdout, expected) or report


def hint_for_run(run: RunResult, model: HintModel | None = None, expected: str | None = None) -> Stage1Hint:
    """Write a stage 1 hint for a run that has already happened. With `expected`, a run
    that finished but printed something else gets a logic-error hint."""
    code = run.code
    report = report_for_run(run, expected)
    if not report.has_error:
        return Stage1Hint(status="no_error", stdout=run.stdout)
    if report.kind == "logic":
        hint = logic_hint_for_report(code, report, model=model)
    else:
        hint = hint_for_report(code, report, model=model)
    hint.stdout = run.stdout
    return hint


class LogicDraft(HintDraft):
    """HintDraft plus the kind of logic mistake."""

    category: str = Field(description="off_by_one, recursion_base_case, calculation or other.")


def logic_hint_for_report(code: str, report: ErrorReport, model: HintModel | None = None) -> Stage1Hint:
    """Stage 1 for a program that ran but printed something the student didn't expect."""
    guess = report.details.get("category", "other")
    base = dict(status="hint", error_type=report.error_type, error_message=report.message, error_line=None)
    if model is None:
        model = default_hint_model()
    internal: dict[str, Any] = {"prompt_version": LOGIC_PROMPT_VERSION, "model": model.name if model else None,
                                "facts": report.facts, "first_guess": guess}
    if model is None:
        internal["fallback_reason"] = "no API key configured for the chosen provider"
        log.warning("logic hint used the fallback question: %s", internal["fallback_reason"])
        return Stage1Hint(**base, question=logic_fallback_question(report), cause_line=report.line,
                          source="fallback", category=guess, internal=internal)

    allowed = f"{code}\n{report.details.get('expected', '')}\n{report.details.get('actual', '')}"
    feedback: str | None = None
    rejected: list[dict[str, Any]] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = perf_counter()
        try:
            draft = model.structured(LOGIC_SYSTEM_PROMPT, build_logic_message(code, report, feedback), LogicDraft)
        except Exception as exc:  # never leave the student with nothing
            record_model_seconds(internal, started)
            log.warning("logic hint model call failed: %s", exc)
            internal["fallback_reason"] = f"model call failed: {type(exc).__name__}: {exc}"
            break
        record_model_seconds(internal, started)
        giveaways = {g for g in draft.giveaways if g}
        cause_text = _line_text(code, draft.cause_line)
        problems = check_question(draft.question, giveaways=giveaways, code=code, student_line_text=cause_text)
        problems += new_code_problems(draft.question, code)
        problems += logic_giveaway_problems(draft.question, giveaways, allowed)
        if not problems:
            category = draft.category if draft.category in CATEGORIES else guess
            internal.update(root_cause=draft.root_cause, misconception=draft.misconception, concept=draft.concept,
                            giveaways=sorted(giveaways), attempts=attempt, rejected=rejected)
            return Stage1Hint(**base, question=draft.question.strip(), cause_line=draft.cause_line,
                              source="model", category=category, internal=internal)
        log.warning("logic hint attempt %d rejected: %r -> %s", attempt, draft.question, "; ".join(problems))
        rejected.append({"question": draft.question, "problems": problems})
        feedback = "\n".join(f"- {p}" for p in problems)
    else:
        internal["fallback_reason"] = "model questions failed the guardrails"
    internal["rejected"] = rejected
    log.warning("logic hint used the fallback question (%s): %s", model.name, internal["fallback_reason"])
    return Stage1Hint(**base, question=logic_fallback_question(report), cause_line=report.line,
                      source="fallback", category=guess, internal=internal)


def _line_text(code: str, line: int | None) -> str:
    lines = code.splitlines()
    return lines[line - 1] if line and 1 <= line <= len(lines) else ""


def hint_for_report(code: str, report: ErrorReport, model: HintModel | None = None) -> Stage1Hint:
    base = dict(
        status="hint",
        error_type=report.error_type,
        error_message=report.message,
        error_line=report.line,
    )
    if model is None:
        model = default_hint_model()
    internal: dict[str, Any] = {
        "prompt_version": PROMPT_VERSION,
        "model": model.name if model else None,
        "facts": report.facts,
    }
    if model is None:
        internal["fallback_reason"] = "no API key configured for the chosen provider"
        log.warning("stage 1 used the fallback question: %s", internal["fallback_reason"])
        return Stage1Hint(**base, question=fallback_question(report), cause_line=report.line,
                          source="fallback", internal=internal)

    feedback: str | None = None
    rejected: list[dict[str, Any]] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = perf_counter()
        try:
            draft = model.draft(code, report, feedback)
        except Exception as exc:  # network, auth, refusal, schema: never leave the student with nothing
            record_model_seconds(internal, started)
            log.warning("stage 1 model call failed: %s", exc)
            internal["fallback_reason"] = f"model call failed: {type(exc).__name__}: {exc}"
            break
        record_model_seconds(internal, started)
        giveaways = set(report.giveaways) | {g for g in draft.giveaways if g}
        problems = check_question(
            draft.question, giveaways=giveaways, code=code, student_line_text=report.line_text,
            visible_text=visible_error_text(report.error_type, report.message),
        )
        if not problems:
            log.info("stage 1 hint from %s on attempt %d", model.name, attempt)
            internal.update(
                root_cause=draft.root_cause,
                misconception=draft.misconception,
                concept=draft.concept,
                giveaways=sorted(giveaways),
                attempts=attempt,
                rejected=rejected,
            )
            return Stage1Hint(**base, question=draft.question.strip(), cause_line=draft.cause_line,
                              source="model", internal=internal)
        log.warning("stage 1 attempt %d rejected by guardrails: %r -> %s",
                    attempt, draft.question, "; ".join(problems))
        rejected.append({"question": draft.question, "problems": problems})
        feedback = "\n".join(f"- {p}" for p in problems)
    else:
        internal["fallback_reason"] = "model questions failed the guardrails"

    internal["rejected"] = rejected
    log.warning("stage 1 used the fallback question (%s): %s", model.name, internal["fallback_reason"])
    return Stage1Hint(**base, question=fallback_question(report), cause_line=report.line,
                      source="fallback", internal=internal)
