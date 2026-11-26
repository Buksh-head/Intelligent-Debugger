"""Supabase Postgres: the connection and the table models.

The tables are the team's, unchanged: see src/database/schema/schema.sql
(the source of truth, applied by hand in the Supabase SQL Editor) and
src/database/migrations/ for the columns added since. These classes
describe the existing tables; they never create or migrate them.

Everything here is optional. Without DATABASE_URL the API still runs code
and gives hints, it just saves nothing: the session routes answer 503 and
the dashboard routes answer 503.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, ForeignKey, SmallInteger, func, text, update
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlmodel import Field, Session, SQLModel, create_engine, select

log = logging.getLogger("debugger.db")


# === Connection ===


def database_enabled() -> bool:
    return bool(os.environ.get("DATABASE_URL", "").strip())


def _sqlalchemy_url() -> str:
    """DATABASE_URL is a plain postgresql:// string (Supabase's connection string);
    SQLAlchemy needs the psycopg (v3) driver named in it."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


_engine = None
_engine_url: str | None = None


def get_engine():
    """Created on first use, so importing this module never needs DATABASE_URL.
    Recreated if DATABASE_URL changes (only happens in tests)."""
    global _engine, _engine_url
    url = _sqlalchemy_url()
    if _engine is None or url != _engine_url:
        # pool_pre_ping: Supabase's pooler drops idle connections; check before reuse.
        # prepare_threshold=None: the pooler (transaction mode) shares server
        # connections between clients, so psycopg's automatic prepared
        # statements clash or go missing (team issue #129).
        _engine = create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})
        _engine_url = url
    return _engine


def get_read_engine():
    """The same connections, in autocommit mode, for reads that change nothing. Each read
    then skips the BEGIN and ROLLBACK round trips to the database (with Supabase a
    round trip is tens to hundreds of milliseconds, depending on its region)."""
    return get_engine().execution_options(isolation_level="AUTOCOMMIT")


def require_database() -> None:
    """For routes that only make sense with a database."""
    if not database_enabled():
        raise HTTPException(503, "Saving is not set up on this server (DATABASE_URL is missing).")


# === Tables (mirror src/database/schema/schema.sql) ===


class Submission(SQLModel, table=True):
    """One run of a student's code."""

    __tablename__ = "submissions"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(sa_column=Column(PGUUID(as_uuid=False), nullable=False))
    code: str
    code_hash: str
    expected_behaviour: str | None = None
    course: str | None = None
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class ErrorLog(SQLModel, table=True):
    """An error in a run: a crash, a timeout, or (error_type LogicError) output that
    differs from what the student expected."""

    __tablename__ = "error_logs"

    id: int | None = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="submissions.id")
    error_type: str
    message: str | None = None
    concept: str | None = None
    line_number: int | None = None
    code_snippet: str | None = None
    hint_stage_reached: int = Field(
        default=1, sa_column=Column(SmallInteger, nullable=False, server_default="1")
    )
    vague_attempts_this_stage: int = Field(
        default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0")
    )
    incorrect_attempts_this_stage: int = Field(
        default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0")
    )
    pending_resource_concept: str | None = None
    resource_offered: bool = Field(default=False, sa_column=Column(nullable=False, server_default="false"))
    resolved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class HintEvent(SQLModel, table=True):
    """One hint shown for an error."""

    __tablename__ = "hint_events"

    id: int | None = Field(default=None, primary_key=True)
    error_log_id: int = Field(foreign_key="error_logs.id")
    stage: int = Field(sa_column=Column(SmallInteger, nullable=False))
    hint_text: str
    shown_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class StudentSession(SQLModel, table=True):
    """A debugging session owned by one student account."""

    __tablename__ = "student_sessions"

    id: str = Field(sa_column=Column(PGUUID(as_uuid=False), primary_key=True))
    username: str
    course: str | None = None
    language: str | None = None
    title: str | None = None
    code: str | None = None
    last_execution: dict | None = Field(default=None, sa_column=Column(JSONB))
    expected_output: str | None = None  # migrations/001_expected_output.sql
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class ChatMessage(SQLModel, table=True):
    """One message of a session's hint conversation, in the shape the Student View renders it."""

    __tablename__ = "chat_messages"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(
        sa_column=Column(
            PGUUID(as_uuid=False),
            ForeignKey("student_sessions.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    position: int
    role: str
    body: dict = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


# === Saving runs ===


def code_hash(code: str) -> str:
    return "sha256:" + hashlib.sha256(code.encode()).hexdigest()


def save_execution(
    *,
    session_id: str,
    code: str,
    course: str | None,
    error: dict | None,
    expected_behaviour: str | None = None,
) -> tuple[int, int | None]:
    """Insert a submissions row, and an error_logs row if the run crashed or timed out.

    `error` has error_type, message, line_number and code_snippet, or is None for a run
    that finished. A run that finishes resolves the session's earlier crashes, as in the
    team's version, so the dashboard can count them as resolved. Logic errors are only
    resolved when the output matches (see resolve_session_errors).

    Returns (submission_id, error_id or None).
    """
    # One statement, so one trip to the database (plus the connection check) instead of
    # a transaction of four to six. A single statement is atomic on its own.
    with Session(get_read_engine()) as db:
        row = db.execute(_SAVE_EXECUTION_SQL, {
            "session_id": session_id, "code": code, "code_hash": code_hash(code),
            "expected": expected_behaviour or None, "course": course,
            "resolve": error is None, "has_error": error is not None,
            "error_type": (error or {}).get("error_type"), "message": (error or {}).get("message"),
            "line_number": (error or {}).get("line_number"), "code_snippet": (error or {}).get("code_snippet"),
        }).one()
        return row.submission_id, row.error_id


# A finished run resolves the session's earlier crashes (not its logic errors); the
# UPDATE can't see the submission inserted beside it, as in the team's version.
_SAVE_EXECUTION_SQL = text("""
WITH resolved AS (
    UPDATE error_logs SET resolved_at = now()
    WHERE CAST(:resolve AS boolean) AND resolved_at IS NULL AND error_type <> 'LogicError'
      AND submission_id IN (SELECT id FROM submissions WHERE session_id = CAST(:session_id AS uuid))
    RETURNING id
), sub AS (
    INSERT INTO submissions (session_id, code, code_hash, expected_behaviour, course)
    VALUES (CAST(:session_id AS uuid), :code, :code_hash, :expected, :course)
    RETURNING id
), err AS (
    INSERT INTO error_logs (submission_id, error_type, message, line_number, code_snippet)
    SELECT id, :error_type, :message, :line_number, :code_snippet FROM sub WHERE CAST(:has_error AS boolean)
    RETURNING id
)
SELECT (SELECT id FROM sub) AS submission_id, (SELECT id FROM err) AS error_id,
       (SELECT count(*) FROM resolved) AS resolved
""")


def _resolve(db: Session, session_id: str, *, include_logic: bool) -> None:
    """Marks the session's open errors resolved, in one UPDATE (not one per error)."""
    in_session = select(Submission.id).where(Submission.session_id == session_id)
    query = (
        update(ErrorLog)
        .where(ErrorLog.submission_id.in_(in_session), ErrorLog.resolved_at.is_(None))
        .values(resolved_at=datetime.now(timezone.utc))
    )
    if not include_logic:
        query = query.where(ErrorLog.error_type != "LogicError")
    db.execute(query)


# === Logic errors and hints ===

LOGIC_ERROR = "LogicError"
LOGIC_MESSAGE = "The output differs from what was expected"


def _submission_in_session(db: Session, submission_id: int, session_id: str) -> Submission | None:
    sub = db.get(Submission, submission_id)
    return sub if sub is not None and str(sub.session_id) == session_id else None


def record_output_check(
    *, session_id: str, submission_id: int, matches: bool, expected: str
) -> int | None:
    """After the student checks a finished run's output against what they expected.

    A match resolves every open error of the session, logic errors included. A
    difference is logged once per run as a LogicError, so the dashboard counts
    wrong output next to crashes. Returns that error's id, or None.

    The run must belong to the session; the session ID is the frontend's random
    UUID, so an ID guessed from another session does nothing.
    """
    with Session(get_engine()) as db:
        sub = _submission_in_session(db, submission_id, session_id)
        if sub is None:
            return None
        sub.expected_behaviour = expected
        db.add(sub)
        if matches:
            _resolve(db, session_id, include_logic=True)
            db.commit()
            return None
        existing = db.exec(
            select(ErrorLog).where(ErrorLog.submission_id == submission_id, ErrorLog.error_type == LOGIC_ERROR)
        ).first()
        if existing is None:
            existing = ErrorLog(submission_id=submission_id, error_type=LOGIC_ERROR, message=LOGIC_MESSAGE)
            db.add(existing)
            db.flush()
        error_id = existing.id
        db.commit()
        return error_id


def record_hint(
    *,
    session_id: str,
    error_id: int,
    stage: int,
    text: str,
    concept: str | None = None,
    message: str | None = None,
) -> bool:
    """A hint the student was shown: one hint_events row, and the error's
    hint_stage_reached raised to `stage` (the dashboard counts an error with a
    reply as "attempted"). `concept` and `message` fill in what the hint found out,
    e.g. the kind of logic mistake, where the error doesn't have them yet.

    Stage 1 is the first question; each reply's follow-up is the next stage.
    False (and nothing saved) if the error isn't from this session.
    """
    with Session(get_engine()) as db:
        err = db.get(ErrorLog, error_id)
        if err is None or _submission_in_session(db, err.submission_id, session_id) is None:
            return False
        db.add(HintEvent(error_log_id=error_id, stage=min(stage, 32767), hint_text=text))
        err.hint_stage_reached = max(err.hint_stage_reached or 1, min(stage, 32767))
        if concept and not err.concept:
            err.concept = concept
        if message and err.error_type == LOGIC_ERROR:
            err.message = message
        db.add(err)
        db.commit()
        return True
