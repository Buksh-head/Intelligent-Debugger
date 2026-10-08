"""Student data deletion

Deletes everything stored for one session: submissions, error logs and
hint events. Before deleting, the database function delete_session_data()
adds the session's errors to the daily count tables, so the instructor
dashboard keeps its numbers without keeping any student code.

The session ID is a random UUID held only in the student's browser tab,
so knowing it is what authorises the deletion.
"""
from uuid import UUID

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlmodel import Session

from app.services.db import get_engine

router = APIRouter(prefix="/api/student-data", tags=["student-data"])


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student_data(session_id: UUID) -> Response:
    """Delete all stored data for a session.

    Always returns 204, whether or not the session had any data, so the
    response can't be used to check which session IDs exist.
    """
    with Session(get_engine()) as session:
        session.execute(
            text("SELECT delete_session_data(:session_id)"),
            {"session_id": session_id},
        )
        # Without this commit the deletion is rolled back when the Session closes.
        session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)