"""Sessions saved to a student's account: list, continue, rename, delete.

The team's routes and queries, kept the same so the frontend's session
history works unchanged. Sessions are keyed by the student's account email
(student_sessions.username), as before, so sessions saved by the team's
version still show up.

Every route needs a student login. A session that belongs to someone else
gets the same 404 as one that doesn't exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.auth import Account, current_student
from app.db import ChatMessage, StudentSession, get_engine, get_read_engine

router = APIRouter(prefix="/api/student", tags=["student-sessions"])

_NOT_FOUND = HTTPException(404, "Session not found")


# === Schemas (mirrored in frontend/src/types.ts) ===

ChatRole = Literal["student", "assistant", "event"]


class StudentSessionCreate(BaseModel):
    id: UUID
    course: str | None = Field(default=None, max_length=50)
    language: str | None = Field(default=None, max_length=50)


class StudentSessionSummary(BaseModel):
    id: str
    course: str | None = None
    language: str | None = None
    title: str | None = None
    latest_error_type: str | None = None
    latest_error_message: str | None = None
    has_unresolved_error: bool = False
    last_run_passed: bool | None = None  # None until the code has been run
    last_activity: datetime


class ChatMessageRecord(BaseModel):
    position: int = Field(ge=0)
    role: ChatRole
    body: dict[str, Any]


class ChatMessagesAppend(BaseModel):
    messages: list[ChatMessageRecord] = Field(max_length=200)


class StudentSessionRename(BaseModel):
    title: str | None = Field(default=None, max_length=100)


class StudentSessionState(BaseModel):
    code: str = Field(max_length=20_000)
    # The last run as the frontend shows it (an ExecutionResponse, plus the input it ran with).
    last_execution: dict[str, Any] | None = None
    # What the student expects the program to print (Expected behaviour tab).
    expected_output: str | None = Field(default=None, max_length=5_000)


class StudentSessionDetail(BaseModel):
    id: str
    course: str | None = None
    language: str | None = None
    code: str | None = None
    last_execution: dict[str, Any] | None = None
    expected_output: str | None = None
    # The hint conversation: hints, the student's replies, and an event at each new run.
    messages: list[ChatMessageRecord]


# === Queries ===

# The latest error of each session, whether any error is still unresolved,
# whether the last run finished without an error or timeout (NULL if the code
# hasn't been run), and when the session was last used. Unchanged from the team's.
_LIST_SQL = text("""
    SELECT ss.id,
           ss.course,
           ss.language,
           ss.title,
           latest.error_type AS latest_error_type,
           latest.message AS latest_error_message,
           EXISTS (
               SELECT 1
               FROM error_logs el
               JOIN submissions s ON s.id = el.submission_id
               WHERE s.session_id = ss.id AND el.resolved_at IS NULL
           ) AS has_unresolved_error,
           CASE WHEN jsonb_typeof(ss.last_execution) = 'object'
                THEN ss.last_execution->>'error' IS NULL
                     AND NOT COALESCE((ss.last_execution->>'timed_out')::boolean, false)
           END AS last_run_passed,
           GREATEST(
               ss.updated_at,
               (SELECT max(s.created_at) FROM submissions s WHERE s.session_id = ss.id)
           ) AS last_activity
    FROM student_sessions ss
    LEFT JOIN LATERAL (
        SELECT el.error_type, el.message
        FROM error_logs el
        JOIN submissions s ON s.id = el.submission_id
        WHERE s.session_id = ss.id
        ORDER BY el.created_at DESC, el.id DESC
        LIMIT 1
    ) latest ON true
    WHERE ss.username = :username
    ORDER BY last_activity DESC
""")


def owned_session(db: Session, username: str, session_id: str, *, lock: bool = False) -> StudentSession | None:
    query = select(StudentSession).where(StudentSession.id == session_id, StudentSession.username == username)
    if lock:
        query = query.with_for_update()
    return db.exec(query).first()


def create_session(*, username: str, session_id: str, course: str | None, language: str | None) -> bool:
    """False if the ID belongs to another student. Registering twice is fine."""
    with Session(get_engine()) as db:
        existing = db.get(StudentSession, session_id)
        if existing is not None:
            return existing.username == username
        db.add(StudentSession(id=session_id, username=username, course=course, language=language))
        db.commit()
        return True


def list_sessions(username: str) -> list[dict]:
    with Session(get_read_engine()) as db:
        rows = db.execute(_LIST_SQL, {"username": username}).mappings().all()
        return [{**row, "id": str(row["id"])} for row in rows]


def get_session(username: str, session_id: str) -> dict | None:
    with Session(get_read_engine()) as db:
        owned = owned_session(db, username, session_id)
        if owned is None:
            return None
        messages = db.exec(
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.position)
        ).all()
        return {
            "id": str(owned.id),
            "course": owned.course,
            "language": owned.language,
            "code": owned.code,
            "last_execution": owned.last_execution if isinstance(owned.last_execution, dict) else None,
            "expected_output": owned.expected_output,
            "messages": [{"position": m.position, "role": m.role, "body": m.body} for m in messages],
        }


def append_messages(username: str, session_id: str, messages: list[dict]) -> bool:
    """Save messages, skipping positions already saved (so a retried save adds nothing twice)."""
    with Session(get_engine()) as db:
        owned = owned_session(db, username, session_id)
        if owned is None:
            return False
        if messages:
            db.execute(
                insert(ChatMessage)
                .values([{**m, "session_id": session_id} for m in messages])
                .on_conflict_do_nothing(constraint="chat_messages_position_key")
            )
        owned.updated_at = datetime.now(timezone.utc)
        db.add(owned)
        db.commit()
        return True


def delete_session(username: str, session_id: str) -> bool:
    """Delete the session and everything stored for it. delete_session_data() first adds
    its errors to the daily counts, so the dashboard keeps its numbers. One transaction."""
    with Session(get_engine()) as db:
        owned = owned_session(db, username, session_id, lock=True)
        if owned is None:
            return False
        db.execute(text("SELECT delete_session_data(CAST(:id AS uuid))"), {"id": session_id})
        db.delete(owned)
        db.commit()
        return True


def rename_session(username: str, session_id: str, title: str | None) -> bool:
    """Renaming doesn't count as activity, so the session keeps its place."""
    with Session(get_engine()) as db:
        owned = owned_session(db, username, session_id)
        if owned is None:
            return False
        owned.title = (title or "").strip() or None
        db.add(owned)
        db.commit()
        return True


def save_state(
    username: str, session_id: str, *, code: str, last_execution: dict | None, expected_output: str | None = None
) -> bool:
    with Session(get_engine()) as db:
        owned = owned_session(db, username, session_id)
        if owned is None:
            return False
        owned.code = code
        owned.last_execution = last_execution
        owned.expected_output = expected_output if (expected_output or "").strip() else None
        owned.updated_at = datetime.now(timezone.utc)
        db.add(owned)
        db.commit()
        return True


# === Routes ===


@router.get("/me")
def whoami(account: Account = Depends(current_student)) -> dict:
    return {"email": account.email}


@router.post("/sessions", status_code=201)
async def create(payload: StudentSessionCreate, account: Account = Depends(current_student)) -> Response:
    ok = await run_in_threadpool(
        create_session, username=account.email, session_id=str(payload.id),
        course=payload.course, language=payload.language,
    )
    if not ok:
        raise HTTPException(409, "Session ID already in use")
    return Response(status_code=201)


@router.get("/sessions", response_model=list[StudentSessionSummary])
async def list_(account: Account = Depends(current_student)) -> list[StudentSessionSummary]:
    rows = await run_in_threadpool(list_sessions, account.email)
    return [StudentSessionSummary(**row) for row in rows]


@router.get("/sessions/{session_id}", response_model=StudentSessionDetail)
async def get(session_id: UUID, account: Account = Depends(current_student)) -> StudentSessionDetail:
    detail = await run_in_threadpool(get_session, account.email, str(session_id))
    if detail is None:
        raise _NOT_FOUND
    return StudentSessionDetail(**detail)


@router.patch("/sessions/{session_id}", status_code=204)
async def rename(
    session_id: UUID, payload: StudentSessionRename, account: Account = Depends(current_student)
) -> Response:
    if not await run_in_threadpool(rename_session, account.email, str(session_id), payload.title):
        raise _NOT_FOUND
    return Response(status_code=204)


@router.post("/sessions/{session_id}/messages", status_code=204)
async def append(
    session_id: UUID, payload: ChatMessagesAppend, account: Account = Depends(current_student)
) -> Response:
    messages = [m.model_dump() for m in payload.messages]
    if not await run_in_threadpool(append_messages, account.email, str(session_id), messages):
        raise _NOT_FOUND
    return Response(status_code=204)


@router.put("/sessions/{session_id}/state", status_code=204)
async def state(
    session_id: UUID, payload: StudentSessionState, account: Account = Depends(current_student)
) -> Response:
    saved = await run_in_threadpool(
        save_state, account.email, str(session_id), code=payload.code,
        last_execution=payload.last_execution, expected_output=payload.expected_output,
    )
    if not saved:
        raise _NOT_FOUND
    return Response(status_code=204)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete(session_id: UUID, account: Account = Depends(current_student)) -> Response:
    if not await run_in_threadpool(delete_session, account.email, str(session_id)):
        raise _NOT_FOUND
    return Response(status_code=204)
