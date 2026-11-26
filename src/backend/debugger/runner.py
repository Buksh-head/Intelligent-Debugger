"""Run a student's Python program and capture the outcome.

Two backends:

* Piston (the sandbox in deployment/docker-compose.yml), used whenever
  PISTON_URL is set. This is what runs in Docker and in production.
* A local subprocess, used when PISTON_URL is not set (tests, quick local
  runs). It uses a fresh interpreter in isolated mode, an empty temp dir,
  a timeout and CPU/memory limits, but it is not a security sandbox.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass

STUDENT_FILENAME = "main.py"
DEFAULT_TIMEOUT_S = 5.0
MAX_OUTPUT_CHARS = 20_000


@dataclass(frozen=True)
class RunResult:
    code: str
    stdin: str
    stdout: str
    stderr: str
    returncode: int | None
    timed_out: bool

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.returncode == 0


def _limit_resources() -> None:  # pragma: no cover - runs in the child
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        mem = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    except Exception:
        pass


def run_student_code(
    code: str, stdin: str = "", timeout_s: float = DEFAULT_TIMEOUT_S
) -> RunResult:
    piston_url = os.environ.get("PISTON_URL")
    if piston_url:
        return run_in_piston(code, stdin, piston_url)
    return run_locally(code, stdin, timeout_s)


class SandboxUnavailable(RuntimeError):
    """Piston could not be reached or returned something unusable."""


def run_in_piston(code: str, stdin: str, piston_url: str) -> RunResult:
    payload = {
        "language": "python",
        "version": os.environ.get("PISTON_PYTHON_VERSION", "3.12.0"),
        "files": [{"name": STUDENT_FILENAME, "content": code}],
        "stdin": stdin,
    }
    request = urllib.request.Request(
        piston_url.rstrip("/") + "/api/v2/execute",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SandboxUnavailable(f"Could not reach the code sandbox: {exc}") from exc

    if "run" not in body:
        raise SandboxUnavailable(body.get("message", "The code sandbox returned no result."))
    return result_from_piston(code, stdin, body["run"])


# Python wrote its own error report (a traceback, or a SyntaxError pointing at main.py).
_PYTHON_ERROR_RE = re.compile(r'Traceback \(most recent call last\)|File "[^"]*main\.py", line \d+')
# What Piston/isolate says when it, rather than Python, stopped the program.
_SANDBOX_KILL_RE = re.compile(
    r"Sandbox keeper received fatal signal|Time limit exceeded|Caught fatal signal|"
    r"(?:stdout|stderr|output) length exceeded|Output limit exceeded",
    re.IGNORECASE,
)
_LOOP_RE = re.compile(r"^\s*(?:while|for|def)\b", re.MULTILINE)


def result_from_piston(code: str, stdin: str, run: dict) -> RunResult:
    """Turn Piston's `run` object into a RunResult.

    A program stuck in a loop can be stopped in several ways depending on the
    Piston version and limits: status "TO" (time limit), "OL" (too much output),
    a SIGKILL, or the sandbox itself aborting ("Sandbox keeper received fatal
    signal 6"), which typically happens when an endless loop floods the output.
    All of these are reported as a timeout so students see the infinite-loop
    explanation instead of sandbox internals.
    """
    status = run.get("status")
    stderr = run.get("stderr") or ""
    sandbox_text = f"{run.get('message') or ''}\n{stderr}"
    python_error = bool(_PYTHON_ERROR_RE.search(stderr))
    sandbox_killed = (
        status in ("TO", "OL", "EL", "SG", "XX")
        or bool(run.get("signal"))
        or bool(_SANDBOX_KILL_RE.search(sandbox_text))
    )
    timed_out = status == "TO" or (sandbox_killed and not python_error)
    if timed_out and status == "XX" and not _LOOP_RE.search(code):
        # An internal sandbox failure on code that cannot loop is not the student's fault.
        raise SandboxUnavailable(run.get("message") or "The code sandbox failed.")
    if timed_out and not python_error:
        stderr = ""  # only sandbox noise; the student sees the timeout explanation instead
    return RunResult(
        code=code,
        stdin=stdin,
        stdout=_clip(run.get("stdout")),
        stderr=_clip(stderr),
        returncode=None if timed_out else run.get("code"),
        timed_out=timed_out,
    )


def run_locally(code: str, stdin: str = "", timeout_s: float = DEFAULT_TIMEOUT_S) -> RunResult:
    with tempfile.TemporaryDirectory(prefix="student-") as workdir:
        path = os.path.join(workdir, STUDENT_FILENAME)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            proc = subprocess.run(
                [sys.executable, "-I", STUDENT_FILENAME],
                cwd=workdir,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=env,
                preexec_fn=_limit_resources if os.name == "posix" else None,
            )
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                code=code,
                stdin=stdin,
                stdout=_clip(exc.stdout),
                stderr=_clip(exc.stderr),
                returncode=None,
                timed_out=True,
            )
        return RunResult(
            code=code,
            stdin=stdin,
            stdout=_clip(proc.stdout),
            stderr=_clip(proc.stderr),
            returncode=proc.returncode,
            timed_out=False,
        )


def _clip(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n...[output truncated]"
    return text
