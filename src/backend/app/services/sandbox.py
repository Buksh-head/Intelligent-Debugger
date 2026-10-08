"""Isolated Execution Sandbox (see Epic #4 / Feature: Isolated Execution Sandbox).

Runs submitted code inside Piston (https://github.com/engineer-man/piston),
a self-hosted, containerised code-execution service. Piston handles the
actual isolation (timeouts, memory limits, no network access), this module
just calls it and extracts a beginner-relevant error summary from the result.
"""
import os
import re

import httpx

PISTON_URL = os.environ.get("PISTON_URL", "http://piston:2000")
RUNTIME_VERSIONS = {
    "python": os.environ.get("PISTON_PYTHON_VERSION", "3.12.0"),
    "java": os.environ.get("PISTON_JAVA_VERSION", "15.0.2"),
    "javascript": os.environ.get("PISTON_JAVASCRIPT_VERSION", "20.11.1"),
}

_TRACEBACK_LINE_RE = re.compile(r'File "[^"]*", line (\d+)')
_ERROR_LINE_RE = re.compile(r"^(\w+(?:Error|Exception|Warning)): ?(.*)$")


def run_in_sandbox(source: str, language: str = "Python") -> dict:
    """Execute source in the sandbox and return a structured result.

    Returns a dict with stdout, stderr, exit_code, status, timed_out, and
    error (a beginner-relevant {error_type, message, line_number} summary,
    or None if the code ran cleanly).
    """
    piston_language = language.lower()
    if piston_language not in RUNTIME_VERSIONS:
        piston_language = "python"

    response = httpx.post(
        f"{PISTON_URL}/api/v2/execute",
        json={
            "language": piston_language,
            "version": RUNTIME_VERSIONS[piston_language],
            "files": [{"content": source}],
        },
        timeout=15.0,
    )
    response.raise_for_status()
    run = response.json()["run"]

    # "TO" = wall-clock timeout (e.g. `while True: pass`). "OL" = output
    # limit exceeded (e.g. `while True: print(...)`).
    # Both cases mean the same thing to a student: an infinite loop.
    ran_out_of_control = run["status"] in ("TO", "OL")

    return {
        "stdout": run["stdout"],
        "stderr": run["stderr"],
        "exit_code": run["code"],
        "status": run["status"],
        "timed_out": ran_out_of_control,
        "error": _extract_error(run["stderr"]) if run["stderr"] and not ran_out_of_control else None,
    }


def _extract_error(stderr: str) -> dict | None:
    """
    Pull a beginner-relevant error summary out of a raw traceback.
    """
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    if not lines:
        return None

    match = _ERROR_LINE_RE.match(lines[-1])

    line_number = None
    code_snippet = None
    for i, line in enumerate(lines):
        frame_match = _TRACEBACK_LINE_RE.search(line)
        if frame_match:
            line_number = int(frame_match.group(1))
            if i + 1 < len(lines):
                code_snippet = lines[i + 1].strip()

    return {
        "error_type": match.group(1) if match else "Error",
        "message": match.group(2) if match else lines[-1],
        "line_number": line_number,
        "code_snippet": code_snippet,
    }
