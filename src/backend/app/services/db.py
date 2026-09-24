"""Persistence for code submissions and execution errors (see Epic #4:
Data Aggregation Pipeline).

Writes only, for now: one row per submission and (if the run failed) one
row per error. No query/read functions yet, that's for whoever builds the
LLM feed / instructor dashboard on top of this.

Table definitions is in app.db_models.
"""
import hashlib
import os

from sqlmodel import Session, create_engine

from app.db_models import ErrorLog, Submission


def _sqlalchemy_url() -> str:
    """SQLModel/SQLAlchemy need an explicit driver in the URL; DATABASE_URL
    is a plain postgresql:// string, so point it at psycopg (v3) explicitly.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set to persist executions")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


_engine = None


def get_engine():
    """Lazily create the engine so importing this module never requires
    DATABASE_URL to be set, only actually opening a Session does. Public
    since app.routers.generation also needs a Session on the same engine.
    """
    global _engine
    if _engine is None:
        # pool_pre_ping: Supabase's pooler drops idle connections; this
        # validates a pooled connection before reuse and reconnects if dead.
        _engine = create_engine(_sqlalchemy_url(), pool_pre_ping=True)
    return _engine


def save_execution(
    *,
    session_id: str,
    code: str,
    expected_behaviour: str,
    error: dict | None,
    course: str | None = None,
) -> int | None:
    """Insert a submissions row, and an error_logs row if execution failed.

    error is the {error_type, message, line_number, code_snippet} dict from
    sandbox.run_in_sandbox(), or None if the code ran cleanly.

    Returns error_id of the error.
    """
    code_hash = "sha256:" + hashlib.sha256(code.encode()).hexdigest()

    with Session(get_engine()) as session:
        submission = Submission(
            session_id=session_id,
            code=code,
            code_hash=code_hash,
            expected_behaviour=expected_behaviour,
            course=course,
        )
        session.add(submission)
        session.flush()  # populate submission.id without committing yet

        error_log_id = None
        if error is not None:
            error_log = ErrorLog(
                submission_id=submission.id,
                error_type=error["error_type"],
                message=error["message"],
                line_number=error["line_number"],
                code_snippet=error["code_snippet"],
            )
            session.add(error_log)
            session.flush()
            error_log_id = error_log.id

        session.commit()
        return error_log_id
