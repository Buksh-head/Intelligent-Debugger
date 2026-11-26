"""Intelligent debugger for first-year Python students.

Stage 1: given a student's program, run it, find the error, and return ONE
leading question that points the student at the cause without giving away
the fix.
"""

from .hints import Stage1Hint, generate_stage1_hint
from .runner import RunResult, run_student_code
from .analysis import ErrorReport, analyse

__all__ = [
    "RunResult",
    "run_student_code",
    "ErrorReport",
    "analyse",
    "Stage1Hint",
    "generate_stage1_hint",
]
