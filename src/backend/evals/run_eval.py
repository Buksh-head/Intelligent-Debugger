"""Live eval: generate a stage 1 hint for every case and check it.

Uses the provider chosen by DEBUGGER_PROVIDER (claude by default, needs
ANTHROPIC_API_KEY; or gemini, needs GEMINI_API_KEY). One or two model calls
per case: real tokens on Claude, free-tier quota on Gemini.

    python -m evals.run_eval              # all cases
    python -m evals.run_eval str-isvowel  # selected cases

Automatic checks per case: the hint came from the model (not the fallback),
it passes the guardrails including the case's own must_not_say list, and the
model's cause_line matches the known cause line. Read the questions too: the
checks catch leaks and format problems, not whether a question is genuinely
helpful.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from debugger.analysis import analyse
from debugger.guardrails import check_question
from debugger.hints import hint_for_report
from debugger.providers import default_hint_model
from debugger.runner import run_student_code
from evals.cases import CASES


def main(selected: list[str]) -> int:
    model = default_hint_model()
    if model is None:
        print("Set ANTHROPIC_API_KEY (or DEBUGGER_PROVIDER=gemini and GEMINI_API_KEY) to run the live eval.")
        return 2
    print(f"Model: {model.name}\n")
    cases = [c for c in CASES if not selected or c.id in selected]
    rows = []
    for case in cases:
        report = analyse(run_student_code(case.code, stdin=case.stdin))
        hint = hint_for_report(case.code, report, model=model)
        problems = check_question(
            hint.question or "",
            giveaways=report.giveaways | set(case.must_not_say),
            code=case.code,
            student_line_text=report.line_text,
        )
        row = {
            "id": case.id,
            "source": hint.source,
            "question": hint.question,
            "cause_line": hint.cause_line,
            "expected_cause_line": case.cause_line,
            "cause_line_ok": hint.cause_line == case.cause_line,
            "guardrail_problems": problems,
            "pass": hint.source == "model" and not problems and hint.cause_line == case.cause_line,
            "internal": hint.internal,
        }
        rows.append(row)
        mark = "PASS" if row["pass"] else "FAIL"
        print(f"[{mark}] {case.id:18} line {hint.cause_line} (want {case.cause_line}) [{hint.source}]\n"
              f"       {hint.question}")
        for p in problems:
            print(f"       ! {p}")
    passed = sum(r["pass"] for r in rows)
    print(f"\n{passed}/{len(rows)} passed")
    out = Path(__file__).parent / f"results-{model.name.replace(':', '-')}.json"
    out.write_text(json.dumps(rows, indent=2, default=str))
    print(f"Details written to {out}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
