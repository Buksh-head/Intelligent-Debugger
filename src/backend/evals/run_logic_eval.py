"""Live eval for logic-error hints: one stage 1 hint and one follow-up per sample program.

Uses the provider chosen by DEBUGGER_PROVIDER, like run_eval.py (try it with
DEBUGGER_MODEL=claude-haiku-5-5). Two to four model calls per case.

    python -m evals.run_logic_eval                  # all cases
    python -m evals.run_logic_eval sum-range fib-base

Automatic checks per case: the hint came from the model, passed the guardrails, named
the right kind of mistake and pointed at the right line. Read the questions too.
"""

from __future__ import annotations

import sys

from debugger.followup import followup_for_report
from debugger.hints import logic_hint_for_report
from debugger.logic import analyse_logic
from debugger.providers import default_hint_model
from debugger.runner import run_student_code
from evals.logic_cases import CASES


def main(selected: list[str]) -> int:
    model = default_hint_model()
    if model is None:
        print("Set ANTHROPIC_API_KEY (or DEBUGGER_PROVIDER=gemini and GEMINI_API_KEY) to run the live eval.")
        return 2
    print(f"Model: {model.name}\n")
    passed = total = 0
    for case in [c for c in CASES if not selected or c.id in selected]:
        run = run_student_code(case.code, stdin=case.stdin)
        report = analyse_logic(case.code, run.stdout, case.expected)
        if report is None:
            print(f"[SKIP] {case.id}: the output matched")
            continue
        total += 1
        hint = logic_hint_for_report(case.code, report, model=model)
        ok = (hint.source == "model" and hint.category == case.category
              and (not case.cause_lines or hint.cause_line in case.cause_lines))
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {case.id:20} {hint.category} (want {case.category}), "
              f"line {hint.cause_line} (want {'/'.join(map(str, case.cause_lines))}) [{hint.source}]")
        print(f"       1: {hint.question}")
        for r in hint.internal.get("rejected", []):
            print(f"       rejected: {r['question']}\n         -> {'; '.join(r['problems'])}")
        follow = followup_for_report(case.code, report, [(hint.question, "i don't know")], model=model)
        print(f"       2 (after 'i don't know', {follow.source}): {follow.text}\n")
    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
