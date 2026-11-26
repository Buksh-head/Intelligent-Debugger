"""Live speed comparison: the same eval cases under different effort and thinking
settings, timed side by side in one run, with the eval's quality checks beside the times.

Claude only (needs ANTHROPIC_API_KEY); the model comes from DEBUGGER_MODEL as usual.
For every case it asks for a stage 1 hint and then one follow-up (to the reply "I'm not
sure"), under each setting in turn. The settings take turns case by case, so a slow
minute on the API side hits all of them alike.

    DEBUGGER_MODEL=claude-haiku-5-5 python -m evals.compare_speed
    python -m evals.compare_speed --settings medium,low          # just these two
    python -m evals.compare_speed --cases str-isvowel,sum-range  # just these cases

A setting is an effort level, optionally with ":off" to turn thinking off
(e.g. "low:off"). Default: medium (today's setting), low, low:off.

Real tokens: two to four calls per case and setting, about 75 cases' worth for the
default three settings. On Haiku 5.5 that is well under a dollar; on Opus 5.5 it is
roughly forty times as much.

The checks are the eval's own (the hint came from the model, passed the guardrails, and
pointed at the right line / named the right kind of mistake). They catch leaks, not
whether a question is genuinely helpful, so read the questions side by side in the
written report before choosing a faster setting.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from debugger.analysis import analyse
from debugger.followup import followup_for_report
from debugger.guardrails import check_question
from debugger.hints import hint_for_report, logic_hint_for_report
from debugger.logic import analyse_logic
from debugger.providers import DEFAULT_CLAUDE_MODEL, ClaudeHintModel
from debugger.runner import run_student_code
from evals import cases as error_cases
from evals import logic_cases

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "deployment" / ".env")

REPLY = "I'm not sure"


@dataclass
class Totals:
    hint_seconds: list[float] = field(default_factory=list)
    followup_seconds: list[float] = field(default_factory=list)
    hints_passed: int = 0
    followups_from_model: int = 0
    redrafts: int = 0  # extra model calls because the guardrails rejected a draft
    cases: int = 0


def _parse_setting(text: str) -> tuple[str, bool]:
    effort, _, thinking = text.strip().partition(":")
    return effort, thinking.lower() != "off"


def _prepared_cases(selected: set[str]):
    """(id, code, report, pass check) for every case that still shows its error."""
    out = []
    for case in error_cases.CASES:
        if selected and case.id not in selected:
            continue
        report = analyse(run_student_code(case.code, stdin=case.stdin))

        def ok(hint, case=case, report=report):
            problems = check_question(hint.question or "", giveaways=report.giveaways | set(case.must_not_say),
                                      code=case.code, student_line_text=report.line_text)
            return hint.source == "model" and not problems and hint.cause_line == case.cause_line

        out.append((case.id, case.code, report, ok))
    for case in logic_cases.CASES:
        if selected and case.id not in selected:
            continue
        run = run_student_code(case.code, stdin=case.stdin)
        report = analyse_logic(case.code, run.stdout, case.expected)
        if report is None:
            continue

        def ok(hint, case=case):
            return (hint.source == "model" and hint.category == case.category
                    and (not case.cause_lines or hint.cause_line in case.cause_lines))

        out.append((case.id, case.code, report, ok))
    return out


def _fmt(values: list[float]) -> tuple[str, str]:
    if not values:
        return "-", "-"
    return f"{statistics.median(values):.1f} s", f"{max(values):.1f} s"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--settings", default="medium,low,low:off")
    parser.add_argument("--cases", default="")
    args = parser.parse_args(argv)

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("Set ANTHROPIC_API_KEY to run the speed comparison.")
        return 2
    import anthropic

    client = anthropic.Anthropic()
    model_id = os.environ.get("DEBUGGER_MODEL", DEFAULT_CLAUDE_MODEL)
    names = [s.strip() for s in args.settings.split(",") if s.strip()]
    models = {n: ClaudeHintModel(client, model_id, *_parse_setting(n)) for n in names}
    totals = {n: Totals() for n in names}
    cases = _prepared_cases({c.strip() for c in args.cases.split(",") if c.strip()})
    print(f"Model: {model_id}; settings: {', '.join(names)}; {len(cases)} cases\n")

    report_lines = [f"# Speed comparison: {model_id}", ""]
    for i, (case_id, code, report, ok) in enumerate(cases):
        report_lines += [f"## {case_id}", ""]
        # Rotate the order each case, so no setting always goes first.
        for name in names[i % len(names):] + names[:i % len(names)]:
            model, t = models[name], totals[name]
            t.cases += 1
            started = perf_counter()
            if report.kind == "logic":
                hint = logic_hint_for_report(code, report, model=model)
            else:
                hint = hint_for_report(code, report, model=model)
            t.hint_seconds.append(perf_counter() - started)
            t.redrafts += max(len(hint.internal.get("model_seconds", [])) - 1, 0)
            passed = ok(hint)
            t.hints_passed += passed

            started = perf_counter()
            follow = followup_for_report(code, report, [(hint.question or "", REPLY)], model=model)
            t.followup_seconds.append(perf_counter() - started)
            t.followups_from_model += follow.source == "model"

            print(f"[{'PASS' if passed else 'FAIL'}] {case_id:20} {name:10} "
                  f"hint {t.hint_seconds[-1]:4.1f} s [{hint.source}], follow-up {t.followup_seconds[-1]:4.1f} s "
                  f"[{follow.source}]")
            report_lines += [
                f"**{name}** ({'pass' if passed else 'FAIL'}, {t.hint_seconds[-1]:.1f} s + "
                f"{t.followup_seconds[-1]:.1f} s)",
                f"- Hint: {hint.question}",
                f"- After \"{REPLY}\": {follow.text}",
                "",
            ]

    header = ("| Setting | Hints passed | Hint median | Hint slowest | Redrafts "
              "| Follow-ups from model | Follow-up median | Follow-up slowest |")
    table = [header, "|" + "---|" * 8]
    for name in names:
        t = totals[name]
        hm, hs = _fmt(t.hint_seconds)
        fm, fs = _fmt(t.followup_seconds)
        table.append(f"| {name} | {t.hints_passed}/{t.cases} | {hm} | {hs} | {t.redrafts} "
                     f"| {t.followups_from_model}/{t.cases} | {fm} | {fs} |")
    print("\n" + "\n".join(table))
    out = Path(__file__).parent / f"speed-{model_id}.md"
    out.write_text("\n".join(report_lines[:2] + table + [""] + report_lines[2:]) + "\n")
    print(f"\nThe questions side by side: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
