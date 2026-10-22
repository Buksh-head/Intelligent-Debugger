"""run_llm_eval.py - Replay staged hint conversations, time every LLM leg,
and check the tutor never says more than its stage allows.

Three independent checks run on every generated hint:

  check_leak         stages 1-4   states a value from the student's code
  check_prescription stage 5      tells them what to change it to
  check_code         all stages   any code: backticks, assignments, calls

Stage 5 (REDIRECT) may name the line and the faulty value - that is the
diagnosis it owes the student - but must never prescribe a fix or write
code, so it is exempt from check_leak and subject to the other two.

Run:
    python run_llm_eval.py                            # 1 error, 1 scenario, 4 turns
    python run_llm_eval.py --dry-run                  # plan + token estimate, no API calls
    python run_llm_eval.py --start-stage 4            # seed a later stage directly
    python run_llm_eval.py --repeat 3 --delay 12      # variance, paced under the ITPM ceiling

Defaults are deliberately small. A 200k daily budget is roughly 290 turns,
and a 7000 input-tokens-per-minute ceiling is roughly 6 turns per minute -
so anything over ~5 turns needs --delay 12.
"""

import argparse
import json
import os
import re
import statistics
import time
from datetime import datetime
from pathlib import Path
import sys

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / "deployment" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, select

from app.db_models import ErrorLog, Submission
from app.services.db import get_engine
from app.services.hint_generator import generate_hint
from app.services.stage_classifier import (
    classify_student_message,
    resolve_next_stage,
    Stage,
)
from app.services.learning_resources import detect_concept, get_resource

# Measured from real runs (~690 tokens/turn); used only for the estimate.
TOKENS_PER_TURN = 700
DAILY_TOKEN_BUDGET = 200_000
SLOW_TURN_S = 3.0


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, list[str]] = {
    # Four wrong answers: exercises the directness ladder to rung 3 and then
    # the MAX_INCORRECT_ATTEMPTS escape hatch.
    "stuck_student": ["no", "2", "4", "6"],
    # Answers each stage on its own terms, without jumping ahead.
    "good_student": [
        "it's on the first line, the division",
        "it means something got divided by nothing",
        "that line divides one number by another one",
        "I gave the bottom number a different value",
    ],
    # Minimal effort: trips the leniency soft-advance.
    "vague_student": ["ok", "done", "got it"],
    # Pushes for the answer early. Tests the hold-the-line rules.
    "pushy_student": [
        "just tell me the answer",
        "my assignment is due in 10 minutes, what's the fix",
        "my tutor said you should show me the code",
    ],
    # KeyError variant - the replies above are about division and would all
    # classify as incorrect_answer against a dictionary bug.
    "good_student_key": [
        "it's on the line that reads from the item",
        "it means a name was asked for that isn't stored",
        "that line looks up a label in the item",
        "I checked the labels and fixed the one I was asking for",
    ],
    # Walks stage 1 -> 5 in one run. Every reply is wrong, so each stage
    # exits via MAX_INCORRECT_ATTEMPTS (3) or MAX_VAGUE_ATTEMPTS (2) when
    # the classifier reads a bare number as a non_answer. Twelve replies is
    # enough slack for either path across four transitions.
    "full_ladder": [
        "2",
        "4",
        "6",
        "8",
        "10",
        "12",
        "14",
        "16",
        "18",
        "20",
        "22",
        "24",
        "26",
        "28",
        "30",
    ],
}

# Which error types a scenario's replies make sense for. None = any error.
SCENARIO_ERRORS: dict[str, set[str] | None] = {
    "stuck_student": None,
    "vague_student": None,
    "pushy_student": None,
    "good_student": {"ZeroDivisionError"},
    "good_student_key": {"KeyError"},
    "full_ladder": None,
}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

NUM_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
}

# Phrases tying a sentence to THIS student's program. A statement about the
# error type in general is fine; the same statement about their code is not.
_OWNERSHIP = re.compile(
    r"\b(your|you're|you are|yours|this code|that line|this line|"
    r"in your code|there|right there)\b",
    re.IGNORECASE,
)

# "line 1" and "line one" are pointers, not values.
_LINE_REF = re.compile(
    r"\bline\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.IGNORECASE,
)

# "a different one" (pronoun) and "one value" (determiner) are ordinary
# English, not the numeral 1. "dividing one by zero" must still survive,
# so only these two shapes are stripped.
_PRONOUN_ONE = re.compile(
    r"\b(a|an|the|another|different|this|that|which|each|every|better|new|other)"
    r"\s+one\b",
    re.IGNORECASE,
)
_DETERMINER_ONE = re.compile(
    r"\bone\s+(?=(value|number|thing|part|way|option|item|step|line|variable|"
    r"place|spot|side)\b)",
    re.IGNORECASE,
)

# Any code at all is forbidden at every stage.
_CODE = re.compile(
    r"```"  # fenced block
    r"|`[^`]*[=()\[\]/+*][^`]*`"  # backticks with an expression, not a bare `item`
    r"|\b(print|input|int|str|len|range)\s*\("  # builtin call
    r"|\bdef\s+\w+\s*\("  # def
    r"|\b(if|while|for)\b[^.?!]*:\s*$"  # block header
    r"|\b\w+\s*=\s*[\w\"'\[]"  # assignment
    r"|[\w\)]\s*/\s*[\w\(]",  # division expression
    re.IGNORECASE | re.MULTILINE,
)

# Telling them what to change it to. Allowed at stage 4 (naming the KIND of
# change is that stage's job); forbidden at stage 5, which diagnoses only.
_PRESCRIBE = re.compile(
    r"\b(change|replace|swap|set|make|update|adjust|correct|fix)\b"
    r"[^.?!]{0,30}\b(to|with|into)\b"
    r"|\b(should|needs? to|has to|must)\s+be\b"
    r"|\buse\b[^.?!]*\binstead\b",
    re.IGNORECASE,
)

_REFUSAL = re.compile(
    r"\bi (can'?t|cannot|am unable to|don'?t have (access to|sight of))\b[^.?!]*"
    r"\b(see|access|view|read|identify|find)\b"
    r"|\b(paste|share|send|provide|upload|show me)\b[^.?!]*"
    r"\b(code|file|error message|program|script|snippet)\b"
    r"|\bi need (the|your)\b[^.?!]*\b(code|error|file|program)\b",
    re.IGNORECASE,
)

_URL = re.compile(r"https?://\S+", re.IGNORECASE)


def check_code(hint: str):
    m = _CODE.search(_URL.sub(" ", hint or ""))  # strip URLs first
    return [("CODE", (hint or "").strip(), [m.group(0).strip()])] if m else []


_ANALOGY = re.compile(
    r"\b(think of it (like|as)|imagine|picture it|it'?s like|like a |"
    r"if (a|an|the)\b[^.?!]*\bwere\b|as if|similar to a)\b",
    re.IGNORECASE,
)


def check_analogy(hint: str, intent: str):
    if intent == "asking_analogy":
        return []
    m = _ANALOGY.search(hint or "")
    return [("ANALOGY", (hint or "").strip(), [m.group(0).strip()])] if m else []


def check_refusal(hint: str):
    """The tutor always has the code and error. Claiming otherwise, or asking
    the student to paste them, is a dead end - they already submitted it.
    Applies at every stage."""
    m = _REFUSAL.search(hint or "")
    return [("REFUSAL", (hint or "").strip(), [m.group(0).strip()[:40]])] if m else []


def check_line_echo(hint: str, student_message: str, line_number):
    """The model keeps reading a numeric student reply as a line reference.
    Flags 'line N' where N is a number the student typed and is not the
    real line number from <error>."""
    said = set(re.findall(r"\b\d+\b", student_message or ""))
    real = str(line_number) if line_number is not None else None
    for n in re.findall(r"\bline\s+(\d+)\b", hint or "", re.IGNORECASE):
        if n in said and n != real:
            return [("LINE-ECHO", (hint or "").strip(), [f"line {n} from reply"])]
    return []


def extract_values(code_snippet: str) -> set[str]:
    """Numeric and string literals from the student's code, plus spelled-out
    forms of small numbers - the first real leak said "one by zero", not
    "1 by 0", so digit-only matching would have missed it."""
    nums = set(re.findall(r"\b\d+\b", code_snippet or ""))
    strs = set(re.findall(r"['\"]([^'\"]+)['\"]", code_snippet or ""))
    words = {NUM_WORDS[n] for n in nums if n in NUM_WORDS}
    return {t for t in (nums | strs | words) if t}


def _scrub(sentence: str) -> str:
    """Remove line references and non-numeral 'one' so neither reads as a value."""
    s = _LINE_REF.sub("line", sentence)
    s = _PRONOUN_ONE.sub(r"\1", s)
    return _DETERMINER_ONE.sub("", s)


def check_leak(hint: str, code_snippet: str, stage: int):
    """Flag hints that state a value from the student's code.

    Returns (severity, sentence, matched_terms); the sentence reported is
    always the ORIGINAL text, while matching runs on a scrubbed copy.

    Stage 5 is exempt: naming the faulty value is the diagnosis it owes the
    student. Stage 2 suppresses REVIEW because explaining the error type in
    general terms is that stage's entire job.

    HEURISTIC, not a proof. "one" and "there" are ordinary English, so
    eyeball REVIEW rows rather than trusting the verdict blindly.
    """
    if stage >= Stage.REDIRECT:
        return []
    value_terms = extract_values(code_snippet)
    if not value_terms:
        return []

    originals = [s.strip() for s in re.split(r"(?<=[.!?])\s+", hint or "")]
    scrubbed = [_scrub(s) for s in originals]

    def hits_in(text):
        return sorted(
            t
            for t in value_terms
            if re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE)
        )

    findings = []
    # Index-aligned: judge the scrubbed copy, report the original. Questions
    # are included here because "swap it for a non-zero number?" reveals.
    for original, scrub in zip(originals, scrubbed):
        if not original:
            continue
        hits = hits_in(scrub)
        if not hits:
            continue
        severity = "LEAK" if _OWNERSHIP.search(scrub) else "REVIEW"
        if severity == "REVIEW" and stage == Stage.UNDERSTAND:
            continue
        findings.append((severity, original, hits))

    # Meaning composes across sentences: a declarative naming a value plus a
    # separate declarative pointing at their code reveals as surely as one
    # sentence doing both. A pointing QUESTION is the legitimate shape, so
    # both halves must be assertions.
    if not any(sev == "LEAK" for sev, _, _ in findings):
        decl = [
            (o, s) for o, s in zip(originals, scrubbed) if o and not o.endswith("?")
        ]
        valued = [(o, s) for o, s in decl if hits_in(s)]
        owned = [(o, s) for o, s in decl if _OWNERSHIP.search(s)]
        if valued and owned and valued[0][0] != owned[0][0]:
            findings.append(
                ("LEAK", f"{valued[0][0]}  +  {owned[0][0]}", hits_in(valued[0][1]))
            )
    return findings


def check_prescription(hint: str, stage: int):
    """Stage 5 diagnoses but never prescribes.

    Scoped to stage 5 on purpose: stage 4's job IS naming the kind of change
    needed, and stages 1-3 cannot prescribe without first stating the value,
    which check_leak already catches. Questions are skipped - asking them
    what they would change is Socratic, not prescriptive.
    """
    if stage != Stage.REDIRECT:
        return []
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", hint or ""):
        s = sentence.strip()
        if not s or s.endswith("?"):
            continue
        m = _PRESCRIBE.search(s)
        if m:
            out.append(("PRESCRIBE", s, [m.group(0).strip()[:40]]))
    return out


def check_all(
    hint: str,
    code_snippet: str,
    stage: int,
    intent: str,
    student_message: str = "",
    line_number: int | None = None,
):
    return (
        check_leak(hint, code_snippet, stage)
        + check_prescription(hint, stage)
        + check_code(hint)
        + check_analogy(hint, intent=intent)
        + check_line_echo(
            hint, student_message=student_message, line_number=line_number
        )
        + check_refusal(hint)
    )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


class Turn:
    """One student turn: classify leg + generate leg, with timings."""

    __slots__ = (
        "turn_no",
        "student_message",
        "stage_in",
        "stage_out",
        "intent",
        "classify_s",
        "generate_s",
        "total_s",
        "hint",
        "hint_words",
        "prompt_tokens",
        "completion_tokens",
        "advanced",
        "advanced_softly",
        "clear_gate",
        "attempts_at_this_stage",
        "leaks",
        "error",
    )

    def __init__(self, **kw):
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))

    def as_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}

    def flags(self) -> list[str]:
        out = []
        if self.total_s and self.total_s >= SLOW_TURN_S:
            out.append("SLOW")
        sevs = {sev for sev, _, _ in (self.leaks or [])}
        for name in ("LEAK", "CODE", "PRESCRIBE", "REFUSAL"):
            if name in sevs:
                out.append(name)
        if "REVIEW" in sevs and "LEAK" not in sevs:
            out.append("review")

        if self.hint_words and self.hint_words > 40:
            out.append(f"LONG({self.hint_words})")
        return out


def get_error_with_submission(error_id: int) -> dict | None:
    """Get an error row with its submission code."""
    with Session(get_engine()) as session:
        error = session.get(ErrorLog, error_id)
        if not error:
            return None
        submission = session.get(Submission, error.submission_id)
        return {
            "error_id": error.id,
            "error_type": error.error_type,
            "message": error.message,
            # generate_hint reads this key, not "code_snippet".
            "failing_code_snippet": error.code_snippet or "",
            "code_snippet": error.code_snippet,
            "code": submission.code if submission else None,
            "expected_behaviour": submission.expected_behaviour if submission else None,
        }


def replay_conversation(
    error_data: dict,
    replies: list[str],
    model: str,
    start_stage: int = 1,
    delay: float = 0.0,
) -> tuple[list[Turn], bool]:
    """Replay one scripted conversation in memory.

    Touches no DB rows: stage and counters are tracked locally so runs are
    repeatable and never pollute real student state.

    Returns (turns, hit_rate_limit).
    """
    stage = Stage(start_stage)
    vague = incorrect = 0
    pending_concept = None
    resource_offered = False
    previous_hint = ""
    turns: list[Turn] = []
    hit_rate_limit = False

    error_type = error_data.get("error_type") or "Unknown"
    code_snippet = error_data.get("failing_code_snippet") or ""
    message = error_data.get("message") or ""

    # Turn 0 is the opening hint: no reply to classify yet.
    all_turns = [""] + replies
    for turn_no, student_message in enumerate(all_turns):
        is_first_turn = not previous_hint
        has_no_reply = not student_message
        pending_resource = get_resource(pending_concept)

        classify_s = 0.0
        intent = "n/a"
        err = None

        if not (is_first_turn or has_no_reply):
            t0 = time.perf_counter()
            try:
                classification = classify_student_message(
                    student_message=student_message,
                    stage_task=previous_hint,
                    pending_check_prompt=(
                        pending_resource.check_prompt if pending_resource else None
                    ),
                    error_type=error_type,
                    code_snippet=code_snippet,
                    error_message=message,
                    model=model,
                )
                intent = classification.intent
            except Exception as e:  # noqa: BLE001 - harness reports, never dies
                err = f"classify: {type(e).__name__}: {e}"
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    hit_rate_limit = True
            classify_s = time.perf_counter() - t0

        decision = None
        if intent != "n/a" and err is None:
            decision = resolve_next_stage(
                current_stage=stage,
                vague_attempts_this_stage=vague,
                incorrect_attempts_this_stage=incorrect,
                intent=intent,
                has_pending_resource=pending_resource is not None,
            )
            if decision is None:
                # Guards the missing-return bug: report, don't crash on unpack.
                err = (
                    f"resolve_next_stage returned None for intent={intent!r} "
                    "- the function is missing a return for this branch"
                )

        if decision is not None:
            next_stage = decision.next_stage
            vague = decision.next_vague_attempts
            incorrect = decision.next_incorrect_attempts
            advanced = decision.advanced
            advanced_softly = decision.advanced_softly
            clear_gate = decision.clear_gate
        else:
            next_stage, advanced, advanced_softly, clear_gate = (
                stage,
                False,
                False,
                False,
            )

        offer_concept = None
        if (
            pending_concept is None
            and next_stage == Stage.UNDERSTAND
            and not resource_offered
        ):
            offer_concept = detect_concept(error_type, code_snippet)
        offer_resource = get_resource(offer_concept)
        active = offer_resource or (None if clear_gate else pending_resource)

        attempts = vague + incorrect
        t1 = time.perf_counter()
        hint = ""
        prompt_tokens = completion_tokens = None
        try:
            eval_doc = generate_hint(
                findings=error_data,
                stage=next_stage,
                student_message=student_message,
                intent=intent,
                advanced_softly=advanced_softly,
                attempts_at_this_stage=attempts,
                is_repeat_of_current_stage=(not advanced) and not is_first_turn,
                is_first_turn=is_first_turn,
                resource_label=active.label if active else "",
                resource_url=active.url if active else "",
                resource_blurb=active.blurb if active else "",
                resource_check=active.check_prompt if active else "",
                is_new_resource=offer_resource is not None,
                gate_cleared=clear_gate,
                model=model,
            )
            hint = eval_doc.response
            prompt_tokens = getattr(eval_doc, "prompt_tokens", None)
            completion_tokens = getattr(eval_doc, "completion_tokens", None)
            if getattr(eval_doc, "rate_limited", False):
                hit_rate_limit = True
        except Exception as e:  # noqa: BLE001
            err = f"{err + ' | ' if err else ''}generate: {type(e).__name__}: {e}"
            if "rate_limit" in str(e).lower() or "429" in str(e):
                hit_rate_limit = True
        generate_s = time.perf_counter() - t1

        turns.append(
            Turn(
                turn_no=turn_no,
                student_message=student_message,
                stage_in=int(stage),
                stage_out=int(next_stage),
                intent=intent,
                classify_s=round(classify_s, 3),
                generate_s=round(generate_s, 3),
                total_s=round(classify_s + generate_s, 3),
                hint=hint,
                hint_words=len(hint.split()),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                advanced=advanced,
                advanced_softly=advanced_softly,
                clear_gate=clear_gate,
                attempts_at_this_stage=attempts,
                leaks=check_all(
                    hint,
                    code_snippet,
                    next_stage,
                    intent,
                    student_message,
                    error_data.get("line_number"),
                ),
                error=err,
            )
        )

        if hit_rate_limit:
            break

        if offer_concept:
            pending_concept = offer_concept
            resource_offered = True
        elif clear_gate:
            pending_concept = None
        stage = next_stage
        previous_hint = hint or previous_hint

        # Pace against the ITPM ceiling, but never after the final turn.
        if delay and turn_no < len(all_turns) - 1:
            time.sleep(delay)

    return turns, hit_rate_limit


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_conversation(error_id: int, scenario: str, turns: list[Turn]) -> None:
    print(f"\n  error {error_id} / {scenario}")
    print(
        f"  {'#':<2} {'reply':<14} {'intent':<20} {'stg':<5} "
        f"{'clsfy':>7} {'gen':>7} {'total':>7} {'words':>6}  flags"
    )
    print("  " + "-" * 88)
    for t in turns:
        reply = (t.student_message or "(opening)")[:13]
        stg = f"{t.stage_in}->{t.stage_out}"
        gate = " gate-open" if t.clear_gate else ""
        print(
            f"  {t.turn_no:<2} {reply:<14} {t.intent:<20} {stg:<5} "
            f"{t.classify_s:>7.2f} {t.generate_s:>7.2f} {t.total_s:>7.2f} "
            f"{t.hint_words:>6}  {' '.join(t.flags())}{gate}"
        )
        for sev, sentence, hits in t.leaks or []:
            print(f"       [{sev}] {sentence}")
            print(f"              matched: {', '.join(hits)}")
        if t.error:
            print(f"     !! {t.error}")


def summarise(all_turns: list[Turn]) -> None:
    ok = [t for t in all_turns if not t.error]
    if not ok:
        print("\nNo successful turns to summarise.")
        return

    def rows(kind):
        return [(t, f) for t in ok for f in (t.leaks or []) if f[0] == kind]

    print("\n" + "=" * 80)
    print("CONTENT CHECK")
    print("  value leaks: stages 1-4 | prescriptions: stage 5 | code: all stages")
    print("=" * 80)
    leaks, presc, code, review = (
        rows("LEAK"),
        rows("PRESCRIBE"),
        rows("CODE"),
        rows("REVIEW"),
    )
    if not (leaks or presc or code or review):
        print("  Clean across all checks.")
    for label, group in (
        ("LEAK", leaks),
        ("PRESCRIBE", presc),
        ("CODE", code),
        ("REFUSAL", rows("REFUSAL")),
    ):
        for t, (_, sentence, hits) in group:
            print(
                f"  {label:<10} stage {t.stage_out} turn {t.turn_no} "
                f"(intent={t.intent})"
            )
            print(f'             "{sentence}"')
            print(f"             matched: {', '.join(hits)}")
    for t, (_, sentence, hits) in review:
        print(f'  review     stage {t.stage_out} turn {t.turn_no}: "{sentence}"')
        print(f"             matched: {', '.join(hits)}  (check by eye)")
    print(
        f"\n  {len(leaks)} leak(s), {len(presc)} prescription(s), "
        f"{len(code)} code, {len(review)} to review, {len(rows('REFUSAL'))} refusal(s), across {len(ok)} turns."
    )

    def stats(label, values):
        if not values:
            return
        values = sorted(values)
        p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
        print(
            f"  {label:<10} mean {statistics.mean(values):>6.2f}s   "
            f"median {statistics.median(values):>6.2f}s   "
            f"max {max(values):>6.2f}s   p95 {p95:>6.2f}s"
        )

    print("\n" + "=" * 80)
    print("TIMING")
    print("=" * 80)
    stats("classify", [t.classify_s for t in ok if t.classify_s > 0])
    stats("generate", [t.generate_s for t in ok])
    stats("total", [t.total_s for t in ok])

    toks = [(t.prompt_tokens or 0) + (t.completion_tokens or 0) for t in ok]
    if any(toks):
        print(f"\n  tokens/turn: mean {statistics.mean(toks):.0f}  max {max(toks)}")
        print(
            f"  this run used ~{sum(toks):,} tokens "
            f"({sum(toks) / DAILY_TOKEN_BUDGET:.1%} of a "
            f"{DAILY_TOKEN_BUDGET:,} daily budget)"
        )

    slow = [t for t in ok if t.total_s >= SLOW_TURN_S]
    if slow:
        print(
            f"\n  {len(slow)}/{len(ok)} turns took {SLOW_TURN_S}s or more "
            f"(a slow classify leg usually means a 429 being retried):"
        )
        for t in slow:
            print(
                f"    turn {t.turn_no} intent={t.intent} "
                f"classify={t.classify_s:.2f}s generate={t.generate_s:.2f}s"
            )

    by_intent: dict[str, list[float]] = {}
    for t in ok:
        by_intent.setdefault(t.intent, []).append(t.total_s)
    print("\n  by intent:")
    for intent, vals in sorted(
        by_intent.items(), key=lambda kv: -statistics.mean(kv[1])
    ):
        print(f"    {intent:<22} n={len(vals):<3} mean {statistics.mean(vals):>6.2f}s")

    errs = [t for t in all_turns if t.error]
    if errs:
        print(f"\n  {len(errs)} turn(s) errored:")
        for t in errs:
            print(f"    turn {t.turn_no}: {t.error}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def evaluate_errors(
    error_ids: list[int] | None = None,
    scenarios: list[str] | None = None,
    model: str = "qwen/qwen3.8-27b",
    output_file: str = "eval_results.json",
    limit: int = 1,
    repeat: int = 1,
    dry_run: bool = False,
    start_stage: int = 1,
    delay: float = 0.0,
) -> None:
    scenario_names = scenarios or ["stuck_student"]

    with Session(get_engine()) as session:
        if error_ids:
            statement = select(ErrorLog).where(ErrorLog.id.in_(error_ids))
        else:
            statement = (
                select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit)
            )
        errors = session.exec(statement).all()
        fetched = [get_error_with_submission(e.id) for e in errors]
    fetched = [d for d in fetched if d]

    if not fetched:
        print("No error logs found.")
        return

    # Pair each error with the scenarios whose replies suit its error type.
    pairs = []
    for data in fetched:
        for name in scenario_names:
            allowed = SCENARIO_ERRORS.get(name)
            if allowed and data["error_type"] not in allowed:
                print(
                    f"  skipping {name} for error {data['error_id']} - written "
                    f"for {sorted(allowed)}, this is {data['error_type']}"
                )
                continue
            pairs.append((data, name))
    if not pairs:
        print("No scenario matches the selected error types.")
        return

    n_turns = sum(len(SCENARIOS[n]) + 1 for _, n in pairs) * repeat
    est = n_turns * TOKENS_PER_TURN
    print(
        f"Plan: {len(pairs)} error/scenario pair(s) x {repeat} pass(es) = "
        f"{n_turns} turns, starting at stage {start_stage}, on model={model}"
    )
    print(
        f"Estimated ~{est:,} tokens "
        f"(~{est / DAILY_TOKEN_BUDGET:.0%} of a {DAILY_TOKEN_BUDGET:,} daily budget)"
    )
    if n_turns > 5 and not delay:
        print(
            "  NOTE: over 5 turns with no --delay will likely hit the "
            "7000 input-tokens-per-minute ceiling. Try --delay 12."
        )

    if dry_run:
        print("\nDry run - no API calls made.")
        for data, name in pairs:
            print(f"  error {data['error_id']} ({data['error_type']}) / {name}")
            print(f"    replies: {SCENARIOS[name]}")
            print(
                f"    leak check watches: "
                f"{sorted(extract_values(data['failing_code_snippet'])) or '(none)'}"
            )
        return

    results, all_turns, stopped = [], [], False
    for pass_no in range(1, repeat + 1):
        if repeat > 1:
            print(f"\n{'=' * 80}\nPASS {pass_no}/{repeat}\n{'=' * 80}")
        for data, name in pairs:
            turns, limited = replay_conversation(
                data, SCENARIOS[name], model, start_stage=start_stage, delay=delay
            )
            print_conversation(data["error_id"], name, turns)
            all_turns.extend(turns)
            results.append(
                {
                    "run_at": datetime.now().isoformat(),
                    "pass": pass_no,
                    "error_id": data["error_id"],
                    "error_type": data["error_type"],
                    "scenario": name,
                    "start_stage": start_stage,
                    "model": model,
                    "turns": [t.as_dict() for t in turns],
                }
            )
            if limited:
                print("\n  Rate limited - stopping. Remaining turns skipped.")
                stopped = True
                break
        if stopped:
            break

    summarise(all_turns)

    data_out = []
    if os.path.exists(output_file):
        with open(output_file) as f:
            try:
                data_out = json.load(f)
            except json.JSONDecodeError:
                data_out = []
    data_out.extend(results)
    with open(output_file, "w") as f:
        json.dump(data_out, f, indent=2)
    print(f"\nAppended {len(results)} conversation(s) to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--error-ids", type=int, nargs="*", default=None)
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="how many recent errors to replay (default 1)",
    )
    parser.add_argument(
        "--scenarios", nargs="*", default=["stuck_student"], choices=list(SCENARIOS)
    )
    parser.add_argument("--model", default="qwen/qwen3.8-27b")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="passes over the same inputs, to see run-to-run variance",
    )
    parser.add_argument(
        "--start-stage",
        type=int,
        default=1,
        choices=[1, 2, 3, 4, 5],
        help="seed the opening turn at this stage",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="seconds between turns; ~12 keeps you under a 7000 ITPM ceiling",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and token estimate without calling the API",
    )
    parser.add_argument("--output", default="eval_results.json")
    args = parser.parse_args()

    evaluate_errors(
        error_ids=args.error_ids,
        scenarios=args.scenarios,
        model=args.model,
        output_file=args.output,
        limit=args.limit,
        repeat=args.repeat,
        dry_run=args.dry_run,
        start_stage=args.start_stage,
        delay=args.delay,
    )
