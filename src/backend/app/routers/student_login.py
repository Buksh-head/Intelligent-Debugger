"""Routes for student login (#165)"""

from fastapi import APIRouter, Depends
from app.auth import get_current_student

router = APIRouter(prefix="/api/student", tags=["student"])


@router.get("/student")
def which_student(email: str = Depends(get_current_student)) -> dict:
    return {"student_email": email}
