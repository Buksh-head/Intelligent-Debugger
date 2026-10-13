"""Student data deletion

A logged-in student deletes one of their own sessions: its chat,
submissions, error logs and hint events. Before deleting, the database
function delete_session_data() adds the session's errors to the daily
count tables, so the instructor dashboard keeps its numbers without
keeping any student code.

The session must belong to the student's username. A session that
belongs to someone else gets the same 404 as one that doesn't exist, so
the response can't be used to check which session IDs exist.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth import get_current_student
from app.services import student_sessions

router = APIRouter(prefix="/api/student/sessions", tags=["student-data"])


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student_session(session_id: UUID, username: str = Depends(get_current_student)) -> Response:
    """Delete all stored data for one of the student's sessions."""
    if not student_sessions.delete_session(username, str(session_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
