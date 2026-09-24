"""Routes for sandboxed code execution (issue #13)."""
import uuid

from fastapi import APIRouter

from app.models import ExecutionResponse, SubmissionRequest
from app.services import db
from app.services.sandbox import run_in_sandbox

router = APIRouter(prefix="/api", tags=["execution"])


@router.post("/execute", response_model=ExecutionResponse)
def execute_code(payload: SubmissionRequest) -> ExecutionResponse:
    """Runs student code in the sandbox via Piston, persists the submission
    and any error to the database (#4), and returns the result.

    session_id isn't tracked client-side yet, so a fresh one is generated
    per request if the caller doesn't supply one.
    """
    result = run_in_sandbox(payload.code, payload.language)

    error_id = db.save_execution(
        session_id=payload.session_id or str(uuid.uuid4()),
        code=payload.code,
        expected_behaviour=payload.expected_behaviour,
        course=payload.course,
        error=result["error"],
    )

    return ExecutionResponse(**result, error_id=error_id)
