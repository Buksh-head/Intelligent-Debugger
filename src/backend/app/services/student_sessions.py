"""Reads and writes for the sessions a student has saved to their account.

Every function takes the username from the student's login and only
touches a session that belongs to it. A session owned by someone else is
treated the same as one that doesn't exist, so callers can't tell the two
apart.

Table definitions are in app.db_models.
"""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.db_models import ChatMessage, StudentSession
from app.services.db import get_engine

# The latest error of each session, whether any error is still unresolved,
# whether the last run finished without an error or timeout (NULL if the
# code hasn't been run), and when the session was last used (chat saves
# bump updated_at, runs add a submission). GREATEST skips NULLs, so
# sessions with no runs still sort.
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
           -- A session that hasn't run stores JSON null, not SQL NULL, so
           -- only an object counts as a run.
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


def owned_session(
    session: Session, username: str, session_id: str, *, lock: bool = False
) -> StudentSession | None:
    """The session if it belongs to the student, otherwise None. With lock,
    the row is held until the transaction ends."""
    query = select(StudentSession).where(
        StudentSession.id == session_id,
        StudentSession.username == username,
    )
    if lock:
        query = query.with_for_update()
    return session.exec(query).first()


def create_session(*, username: str, session_id: str, course: str | None, language: str | None) -> bool:
    """Record a new session for the student.

    Returns False if the ID is already taken by another student. Registering
    the same session twice for the same student is allowed, so a retried
    request doesn't fail.
    """
    with Session(get_engine()) as session:
        existing = session.get(StudentSession, session_id)
        if existing is not None:
            return existing.username == username

        session.add(StudentSession(id=session_id, username=username, course=course, language=language))
        session.commit()
        return True


def list_sessions(username: str) -> list[dict]:
    """The student's sessions, most recently used first."""
    with Session(get_engine()) as session:
        rows = session.execute(_LIST_SQL, {"username": username}).mappings().all()
        return [{**row, "id": str(row["id"])} for row in rows]


def get_session(username: str, session_id: str) -> dict | None:
    """One session with its chat in order, or None if it isn't the student's."""
    with Session(get_engine()) as session:
        owned = owned_session(session, username, session_id)
        if owned is None:
            return None

        messages = session.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.position)
        ).all()
        return {
            "id": owned.id,
            "course": owned.course,
            "language": owned.language,
            "code": owned.code,
            "last_execution": owned.last_execution,
            "messages": [{"position": m.position, "role": m.role, "body": m.body} for m in messages],
        }


def append_messages(username: str, session_id: str, messages: list[dict]) -> bool:
    """Save chat messages, skipping any position already saved.

    Returns False if the session isn't the student's.
    """
    with Session(get_engine()) as session:
        owned = owned_session(session, username, session_id)
        if owned is None:
            return False

        if messages:
            session.execute(
                insert(ChatMessage)
                .values([{**message, "session_id": session_id} for message in messages])
                .on_conflict_do_nothing(constraint="chat_messages_position_key")
            )
        owned.updated_at = datetime.now(timezone.utc)
        session.add(owned)
        session.commit()
        return True


def delete_session(username: str, session_id: str) -> bool:
    """Delete one of the student's sessions and everything stored for it.

    delete_session_data() first adds the session's errors to the daily count
    tables, so the instructor dashboard keeps its numbers, then deletes its
    submissions (cascading to error logs and hint events). Deleting the
    session row removes its chat. All of it is one transaction.

    Returns False, deleting nothing, if the session isn't the student's.
    """
    with Session(get_engine()) as session:
        owned = owned_session(session, username, session_id, lock=True)
        if owned is None:
            return False

        session.execute(text("SELECT delete_session_data(:session_id)"), {"session_id": session_id})
        session.delete(owned)
        # Without this commit the deletion is rolled back when the Session closes.
        session.commit()
        return True


def rename_session(username: str, session_id: str, title: str | None) -> bool:
    """Set the session's name, or clear it with a blank or None title.

    Renaming doesn't count as activity, so the session keeps its place in
    the history. Returns False if the session isn't the student's.
    """
    with Session(get_engine()) as session:
        owned = owned_session(session, username, session_id)
        if owned is None:
            return False

        owned.title = (title or "").strip() or None
        session.add(owned)
        session.commit()
        return True


def save_state(username: str, session_id: str, *, code: str, last_execution: dict | None) -> bool:
    """Save the editor code and latest run result.

    Returns False if the session isn't the student's.
    """
    with Session(get_engine()) as session:
        owned = owned_session(session, username, session_id)
        if owned is None:
            return False

        owned.code = code
        owned.last_execution = last_execution
        owned.updated_at = datetime.now(timezone.utc)
        session.add(owned)
        session.commit()
        return True
