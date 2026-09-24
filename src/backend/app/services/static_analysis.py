"""Static Analysis Processor (see issue #7).

Deterministic AST-based checks for the curated subset of beginner
Python errors. Never executes submitted code — runtime checks belong
to the sandboxed execution service (#4).
"""
import ast


def analyse_code(source: str) -> list[dict]:
    """Parse ``source`` and return a list of finding dicts.

    Each finding has ``error_type``, ``line_number``, and
    ``failing_code_snippet`` per the schema #7 defines for the
    hint-generation service to consume.
    """
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return [
            {
                "error_type": type(exc).__name__,
                "line_number": exc.lineno,
                "failing_code_snippet": exc.text.strip() if exc.text else "",
            }
        ]
    return []
