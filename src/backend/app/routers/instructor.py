"""Routes gated behind instructor authentication (#5, #17)."""
from fastapi import APIRouter, Depends

from app.auth import get_current_instructor

router = APIRouter(prefix="/api/instructor", tags=["instructor"])


@router.get("/me")
def whoami(email: str = Depends(get_current_instructor)) -> dict:
    return {"email": email}
