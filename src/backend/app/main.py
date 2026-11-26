"""HTTP API for the Error Guide frontend.

Routes:
  GET  /health             liveness check
  POST /api/execute        run the student's code in the sandbox
  POST /api/hints/stage1   one leading question for the error in that run
  POST /api/hints/followup stage 2: respond to the student's reply to a hint
  POST /api/answer         Socratic mode: the diagnosis and fix, with how it was worked out
  POST /api/check-output   compare a finished run's output with what the student expected
  /api/student/...         saved sessions (app/student_sessions.py), needs a student login
  /api/analytics/...       instructor dashboard (app/dashboard.py), needs an instructor login

With DATABASE_URL set (the Supabase Postgres connection string), every run is
saved for the instructor dashboard, as in the team's version. Without it
nothing is saved and the routes that need the database answer 503.

Run locally:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import uuid
from time import perf_counter

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import db
from app.dashboard import router as dashboard_router
from app.student_sessions import router as student_sessions_router
from debugger.analysis import analyse
from debugger.answer import answer_for_run
from debugger.explain import explain
from debugger.followup import followup_for_run
from debugger.hints import hint_for_run, strip_suggestion
from debugger.logic import CATEGORY_LABELS, compare_output, describe_difference
from debugger.explainability.service import Explanation
from debugger.runner import RunResult, SandboxUnavailable, run_student_code

# Uvicorn only sets up its own loggers; without this the debugger's messages
# (including why a fallback question was used) never reach the container log.
logging.basicConfig(
    level=os.environ.get("DEBUGGER_LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s:     %(name)s: %(message)s",
)
log = logging.getLogger("debugger.api")
MAX_CODE_CHARS = 20_000
MAX_STDIN_CHARS = 5_000
MAX_EXPECTED_CHARS = 5_000

app = FastAPI(title="Error Guide API - progressive hints")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


class _RequestTimer:
    """Logs how long each API request took, e.g. "GET /api/student/sessions 200 in 0.21 s",
    so a slow screen can be traced to the request behind it. A plain ASGI wrapper, so it
    adds nothing measurable to the request itself."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        started = perf_counter()

        async def send_and_note(message):
            if message["type"] == "http.response.start":
                log.info("%s %s %s in %.2f s", scope["method"], scope["path"], message["status"],
                         perf_counter() - started)
            await send(message)

        await self.app(scope, receive, send_and_note)


app.add_middleware(_RequestTimer)
app.include_router(student_sessions_router)
app.include_router(dashboard_router)


# === Schemas (mirrored in frontend/src/types.ts) ===


class ExecutionError(BaseModel):
    error_type: str
    message: str  # Python's own message, exactly as Python wrote it
    line_number: int | None
    code_snippet: str | None
    # The same error in plain English for beginners (debugger/explain.py).
    friendly_title: str
    friendly_message: str


class ExecutionResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int | None
    status: str | None
    timed_out: bool
    error: ExecutionError | None
    error_id: int | None = None  # the error_logs row for this run's error, when saved
    submission_id: int | None = None  # the submissions row for this run, when saved


class ExecuteRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)
    stdin: str = Field(default="", max_length=MAX_STDIN_CHARS)
    course: str | None = None
    language: str | None = None
    session_id: str | None = None
    # The output the student expects, if they have typed one (saved with the run).
    expected: str | None = Field(default=None, max_length=MAX_EXPECTED_CHARS)


class RunForHint(BaseModel):
    stdout: str = ""
    stderr: str = Field(default="", max_length=50_000)
    exit_code: int | None = None
    timed_out: bool = False


class SavedError(BaseModel):
    """Which saved error a hint is for, so it is recorded for the dashboard. The
    session must be the one the error was saved under. Both optional."""

    session_id: str | None = Field(default=None, max_length=64)
    error_id: int | None = None


class Stage1Request(SavedError):
    code: str = Field(max_length=MAX_CODE_CHARS)
    stdin: str = Field(default="", max_length=MAX_STDIN_CHARS)
    execution: RunForHint
    # The output the student expected. When the run finished but printed something
    # else, the hint is about that logic error.
    expected: str | None = Field(default=None, max_length=MAX_EXPECTED_CHARS)


class CheckOutputRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)  # to drop input() prompts from the output
    stdout: str = Field(max_length=50_000)
    expected: str = Field(max_length=MAX_EXPECTED_CHARS)
    # The saved run being checked (ExecutionResponse.submission_id) and its session.
    session_id: str | None = Field(default=None, max_length=64)
    submission_id: int | None = None


class CheckOutputResponse(BaseModel):
    matches: bool
    title: str
    message: str
    first_diff: int | None  # 1-based output line where they first differ
    expected_line: str | None
    actual_line: str | None
    error_id: int | None = None  # the LogicError saved for a difference, for the hints


class HintTurn(BaseModel):
    question: str = Field(max_length=1_000)
    reply: str = Field(min_length=1, max_length=1_000)


class FollowUpRequest(SavedError):
    code: str = Field(max_length=MAX_CODE_CHARS)
    stdin: str = Field(default="", max_length=MAX_STDIN_CHARS)
    execution: RunForHint
    # Every question asked so far (the stage 1 question first) with the student's reply.
    turns: list[HintTurn] = Field(min_length=1, max_length=10)
    expected: str | None = Field(default=None, max_length=MAX_EXPECTED_CHARS)


class FollowUpResponse(BaseModel):
    kind: str  # "question": the student can reply again; "answer": the hints are done
    text: str
    assessment: str  # found_it | partly | wrong_idea | unsure | off_topic | unknown
    cause_line: int | None
    turn: int
    final: bool
    source: str  # "model" or "fallback"


class Stage1Response(BaseModel):
    question: str
    error_type: str | None
    error_line: int | None
    cause_line: int | None
    source: str  # "model" or "fallback"
    # Logic errors only: the kind of mistake, e.g. "off_by_one", and how it is named to the
    # student, e.g. "an off-by-one mistake" (shown as "Looks like an off-by-one mistake").
    category: str | None = None
    category_label: str | None = None


class AnswerResponse(BaseModel):
    diagnosis: str | None  # what the code does and why it fails
    fix: str | None  # the change that resolves it, may contain code
    error_type: str | None
    error_line: int | None
    source: str  # "model" or "fallback"
    # How the answer was reached: the model's reasoning, the misconception the classifier
    # picked and what in the code pointed there. None when that layer is unavailable.
    explanation: Explanation | None = None


# === Routes ===


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/execute", response_model=ExecutionResponse)
async def execute(req: ExecuteRequest) -> ExecutionResponse:
    if req.language and req.language.lower() != "python":
        raise HTTPException(422, f"{req.language} is not supported yet. Only Python code can be run for now.")
    try:
        run = await run_in_threadpool(run_student_code, req.code, req.stdin)
    except SandboxUnavailable as exc:
        log.error("sandbox unavailable: %s", exc)
        raise HTTPException(503, "The code runner is unavailable right now. Try again in a moment.") from exc

    report = analyse(run)
    error = None
    if report.kind in ("runtime", "syntax"):
        friendly = explain(report)
        error = ExecutionError(
            error_type=report.error_type or "Error",
            # Shown as is in the Output tab, including any "Did you mean" suggestion.
            message=report.message or "",
            line_number=report.line,
            code_snippet=report.line_text,
            friendly_title=friendly.title,
            friendly_message=friendly.message,
        )
    status = "TO" if run.timed_out else ("RE" if error else None)
    response = ExecutionResponse(
        stdout=run.stdout,
        stderr=run.stderr,
        exit_code=run.returncode,
        status=status,
        timed_out=run.timed_out,
        error=error,
    )
    if db.database_enabled():
        response.submission_id, response.error_id = await _save_run(req, response)
    return response


def _logged_error(response: ExecutionResponse) -> dict | None:
    """What goes in error_logs: the crash, or a timeout (shown on the dashboard as "Timeout")."""
    if response.error is not None:
        e = response.error
        # The Output tab shows Python's full message, but the dashboard groups errors by
        # message, so the saved one leaves out "Did you mean: 'total'?" (as before).
        return {"error_type": e.error_type, "message": strip_suggestion(e.message),
                "line_number": e.line_number, "code_snippet": e.code_snippet}
    if response.timed_out:
        return {"error_type": "Timeout", "message": "The program did not finish within the time limit.",
                "line_number": None, "code_snippet": None}
    return None


async def _save_run(req: ExecuteRequest, response: ExecutionResponse) -> tuple[int | None, int | None]:
    """Saves the run for the dashboard. A database problem never stops the student
    seeing their result, so it is only logged."""
    try:
        return await run_in_threadpool(
            db.save_execution,
            session_id=_session_uuid(req.session_id),
            code=req.code,
            course=req.course,
            error=_logged_error(response),
            expected_behaviour=req.expected,
        )
    except Exception:
        log.exception("could not save the run")
        return None, None


def _valid_uuid(value: str | None) -> str | None:
    try:
        return str(uuid.UUID(value or ""))
    except ValueError:
        return None


def _session_uuid(session_id: str | None) -> str:
    """The frontend's session ID, or a fresh one (submissions.session_id is a UUID)."""
    return _valid_uuid(session_id) or str(uuid.uuid4())


@app.post("/api/hints/stage1", response_model=Stage1Response)
async def stage1_hint(req: Stage1Request, background: BackgroundTasks) -> Stage1Response:
    started = perf_counter()
    # The frontend sends back the run it already has, so the code is not run twice
    # (a second run could also behave differently, e.g. with random numbers).
    run = RunResult(
        code=req.code,
        stdin=req.stdin,
        stdout=req.execution.stdout,
        stderr=req.execution.stderr,
        returncode=req.execution.exit_code,
        timed_out=req.execution.timed_out,
    )
    hint = await run_in_threadpool(hint_for_run, run, None, req.expected)
    if hint.status != "hint" or not hint.question:
        raise HTTPException(422, "This run has no error to give a hint about.")
    # Internal analysis (root cause, misconception, giveaways) is for teachers and
    # later stages; it is logged, never sent to the student.
    log.info("stage1 %s", hint.to_dict())
    # Saved after the response is sent, so the student doesn't wait for the database.
    if hint.category:
        label = CATEGORY_LABELS.get(hint.category)
        background.add_task(_record_hint, req, 1, hint.question, concept=hint.category,
                            message=f"Looks like {label}" if label else None)
    else:
        background.add_task(_record_hint, req, 1, hint.question, concept=hint.internal.get("concept"))
    _log_timing("stage1", started, hint.internal, hint.source)
    return Stage1Response(
        question=hint.question,
        error_type=hint.error_type,
        error_line=hint.error_line,
        cause_line=hint.cause_line,
        source=hint.source or "fallback",
        category=hint.category,
        category_label=CATEGORY_LABELS.get(hint.category) if hint.category else None,
    )


@app.post("/api/check-output", response_model=CheckOutputResponse)
async def check_output(req: CheckOutputRequest) -> CheckOutputResponse:
    """Compare what a finished run printed with what the student expected. No model, no run.
    For a saved run, a difference is saved as a LogicError and a match resolves the session's errors."""
    cmp = compare_output(req.stdout, req.expected, req.code)
    title, message = describe_difference(cmp)
    error_id = None
    session_id = _valid_uuid(req.session_id)
    if db.database_enabled() and session_id and req.submission_id:
        try:
            error_id = await run_in_threadpool(
                db.record_output_check, session_id=session_id, submission_id=req.submission_id,
                matches=cmp.matches, expected=req.expected,
            )
        except Exception:
            log.exception("could not save the output check")
    return CheckOutputResponse(matches=cmp.matches, title=title, message=message, first_diff=cmp.first_diff,
                               expected_line=cmp.expected_line, actual_line=cmp.actual_line, error_id=error_id)


def _log_timing(route: str, started: float, internal: dict, source: str | None) -> None:
    """One line per hint request saying where the wait went: the model calls (more than
    one when the guardrails rejected a draft) and our own checks. Saving is logged
    separately, since it happens after the response is sent."""
    total = perf_counter() - started
    calls = internal.get("model_seconds", [])
    model = sum(calls)
    log.info(
        "%s timing: %.2f s total = model %.2f s over %d call(s) [%s] + checks %.2f s; source %s",
        route, total, model, len(calls), ", ".join(f"{c:.2f}" for c in calls), max(total - model, 0), source,
    )


async def _record_hint(req: SavedError, stage: int, text: str, **found) -> None:
    """Saves a hint the student was shown, for the dashboard. Runs after the response is
    sent. Only logged if it fails."""
    session_id = _valid_uuid(req.session_id)
    if not (db.database_enabled() and session_id and req.error_id):
        return
    started = perf_counter()
    try:
        await run_in_threadpool(
            db.record_hint, session_id=session_id, error_id=req.error_id, stage=stage, text=text, **found
        )
    except Exception:
        log.exception("could not save the hint")
    else:
        log.info("saved hint stage %d in %.2f s (after the response)", stage, perf_counter() - started)


@app.post("/api/hints/followup", response_model=FollowUpResponse)
async def followup_hint(req: FollowUpRequest, background: BackgroundTasks) -> FollowUpResponse:
    """Stage 2: respond to the student's reply with a new question or an answer."""
    started = perf_counter()
    run = RunResult(
        code=req.code,
        stdin=req.stdin,
        stdout=req.execution.stdout,
        stderr=req.execution.stderr,
        returncode=req.execution.exit_code,
        timed_out=req.execution.timed_out,
    )
    turns = [(t.question, t.reply.strip()) for t in req.turns]
    result = await run_in_threadpool(followup_for_run, run, turns, None, req.expected)
    if result is None:
        raise HTTPException(422, "This run has no error to give a hint about.")
    log.info("stage2 %s", result.to_dict())
    # Stage 1 was the first question; the follow-up to reply n is stage n + 1. Saved after
    # the response is sent, so the student doesn't wait for the database.
    background.add_task(_record_hint, req, len(turns) + 1, result.text)
    _log_timing("stage2", started, result.internal, result.source)
    return FollowUpResponse(
        kind=result.kind,
        text=result.text,
        assessment=result.assessment,
        cause_line=result.cause_line,
        turn=result.turn,
        final=result.final,
        source=result.source,
    )


@app.post("/api/answer", response_model=AnswerResponse)
async def socratic_answer(req: Stage1Request) -> AnswerResponse:
    """Socratic mode: the whole answer in one turn. As in the team version, it is not run
    through the hint guardrails, since giving the answer is the point."""
    started = perf_counter()
    run = RunResult(
        code=req.code,
        stdin=req.stdin,
        stdout=req.execution.stdout,
        stderr=req.execution.stderr,
        returncode=req.execution.exit_code,
        timed_out=req.execution.timed_out,
    )
    answer = await run_in_threadpool(answer_for_run, run, None, req.expected)
    if answer.status != "answer":
        raise HTTPException(422, "This run has no error to explain.")
    log.info("answer %s", answer.to_dict())
    _log_timing("answer", started, answer.internal, answer.source)
    return AnswerResponse(
        diagnosis=answer.diagnosis,
        fix=answer.fix,
        error_type=answer.error_type,
        error_line=answer.error_line,
        source=answer.source or "fallback",
        explanation=answer.explanation,
    )
