"""Routes for the debugging sessions saved to a student's account.

The Student View registers each session when it starts, saves the chat
and run state as the student works, and loads them back when the student
continues a session from their history. Every route needs a student
login, and a session that belongs to someone else gets the same 404 as
one that doesn't exist.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth import get_current_student
from app.models import (
    ChatMessagesAppend,
    StudentSessionCreate,
    StudentSessionDetail,
    StudentSessionRename,
    StudentSessionState,
    StudentSessionSummary,
)
from app.services import student_sessions

router = APIRouter(prefix="/api/student/sessions", tags=["student-sessions"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(
    payload: StudentSessionCreate, username: str = Depends(get_current_student)
) -> Response:
    created = student_sessions.create_session(
        username=username,
        session_id=str(payload.id),
        course=payload.course,
        language=payload.language,
    )
    if not created:
        # Session IDs are random UUIDs, so this only happens if a student
        # reuses an ID from someone else's session.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Session ID already in use"
        )
    return Response(status_code=status.HTTP_201_CREATED)


@router.get("", response_model=list[StudentSessionSummary])
def list_sessions(
    username: str = Depends(get_current_student),
) -> list[StudentSessionSummary]:
    return [
        StudentSessionSummary(**row) for row in student_sessions.list_sessions(username)
    ]


@router.get("/{session_id}", response_model=StudentSessionDetail)
def get_session(
    session_id: UUID, username: str = Depends(get_current_student)
) -> StudentSessionDetail:
    detail = student_sessions.get_session(username, str(session_id))
    if detail is None:
        raise _NOT_FOUND
    return StudentSessionDetail(**detail)


@router.patch("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def rename_session(
    session_id: UUID,
    payload: StudentSessionRename,
    username: str = Depends(get_current_student),
) -> Response:
    if not student_sessions.rename_session(username, str(session_id), payload.title):
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
def append_messages(
    session_id: UUID,
    payload: ChatMessagesAppend,
    username: str = Depends(get_current_student),
) -> Response:
    messages = [message.model_dump() for message in payload.messages]
    if not student_sessions.append_messages(username, str(session_id), messages):
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{session_id}/state", status_code=status.HTTP_204_NO_CONTENT)
def save_state(
    session_id: UUID,
    payload: StudentSessionState,
    username: str = Depends(get_current_student),
) -> Response:
    saved = student_sessions.save_state(
        username,
        str(session_id),
        code=payload.code,
        last_execution=(
            payload.last_execution.model_dump() if payload.last_execution else None
        ),
    )
    if not saved:
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)
