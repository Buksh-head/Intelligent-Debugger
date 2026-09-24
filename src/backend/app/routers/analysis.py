"""Routes for static analysis (issue #7)."""
from fastapi import APIRouter

from app.models import SubmissionRequest, SubmissionResponse
from app.services.static_analysis import analyse_code

router = APIRouter(prefix="/api", tags=["static-analysis"])


@router.post("/submit", response_model=SubmissionResponse)
def submit_code(payload: SubmissionRequest) -> SubmissionResponse:
    """Accepts student code and returns static analysis findings.

    Sandboxed execution (#4) and staged hint generation (#9, #11)
    are not wired in yet, this currently only runs static analysis.
    """
    findings = analyse_code(payload.code)
    return SubmissionResponse(status="analysed", findings=findings)
