"""Who is calling: verifies the Supabase login token and looks up the account's role.

The frontend signs in with Supabase Auth and sends the access token as
`Authorization: Bearer <token>`. The token is checked against the project's
public keys (JWKS, for the asymmetric ES256/RS256 keys Supabase uses now), or
against SUPABASE_JWT_SECRET for a project still on the legacy HS256 secret.

The role comes from public.profiles, the same table the frontend reads and
only the sign-up trigger writes (src/database/schema/auth-roles.sql). The
team's version read it from the token's app_metadata instead, which Supabase
only fills in when an extra hook is set up; profiles is always there.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock

import jwt
from fastapi import Header, HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.db import get_read_engine, require_database


@dataclass(frozen=True)
class Account:
    user_id: str
    email: str
    role: str  # "student" | "instructor"


@lru_cache(maxsize=4)
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True)


def _supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or os.environ.get("VITE_SUPABASE_URL") or "").strip()


def verify_token(authorization: str | None) -> dict:
    """The token's claims, or 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please log in again.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            secret = os.environ.get("SUPABASE_JWT_SECRET", "")
            if not secret:
                raise HTTPException(401, "Please log in again.")
            key = secret
        else:
            url = _supabase_url()
            if not url:
                raise HTTPException(503, "Logins are not set up on this server (SUPABASE_URL is missing).")
            key = _jwks_client(url).get_signing_key_from_jwt(token).key
        return jwt.decode(
            token, key, algorithms=["HS256", "ES256", "RS256"], audience="authenticated"
        )
    except HTTPException:
        raise
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(401, "Please log in again.") from exc


# Roles are set once, by the sign-up trigger, so a found role is kept for a few minutes
# instead of being looked up again on every request (each lookup is a trip to the database).
ROLE_CACHE_SECONDS = 300
_roles: dict[str, tuple[str, float]] = {}
_roles_lock = Lock()


def role_of(user_id: str) -> str | None:
    now = time.monotonic()
    with _roles_lock:
        cached = _roles.get(user_id)
    if cached and now - cached[1] < ROLE_CACHE_SECONDS:
        return cached[0]
    with Session(get_read_engine()) as db:
        role = db.execute(
            text("SELECT role FROM profiles WHERE id = CAST(:id AS uuid)"), {"id": user_id}
        ).scalar()
    if role is not None:  # an account without a profile yet is looked up again next time
        with _roles_lock:
            if len(_roles) > 10_000:
                _roles.clear()
            _roles[user_id] = (role, now)
    return role


def _account(authorization: str | None, role: str) -> Account:
    require_database()
    claims = verify_token(authorization)
    user_id, email = claims.get("sub"), claims.get("email")
    if not user_id or not email:
        raise HTTPException(401, "Please log in again.")
    if role_of(user_id) != role:
        raise HTTPException(403, f"This needs a{'n' if role == 'instructor' else ''} {role} account.")
    return Account(user_id=user_id, email=email, role=role)


def current_student(authorization: str | None = Header(default=None)) -> Account:
    return _account(authorization, "student")


def current_instructor(authorization: str | None = Header(default=None)) -> Account:
    return _account(authorization, "instructor")
