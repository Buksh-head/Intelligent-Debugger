"""Verifies Supabase-issued JWTs and the account's role (#5, #17, #210).

Supabase Auth signs JWTs with an asymmetric key (ES256); the matching
public key is fetched from the project's JWKS endpoint and cached by
PyJWT's PyJWKClient, so no shared secret is involved. Every account is a
student or an instructor, read from the token's app_metadata.role.
Routes depend on get_current_student or get_current_instructor to get
the caller's email.
"""

import os
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    """Client that fetches Supabase's public keys. Created once and reused."""
    supabase_url = os.environ.get("SUPABASE_URL")
    if not supabase_url:
        raise RuntimeError("SUPABASE_URL must be set to verify instructor logins")
    return jwt.PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json")


def _verify_token(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer"):
        raise HTTPException(
            status_code=401, detail="Missing or malformed Authorisation header"
        )

    token = authorization.removeprefix("Bearer ")
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token, signing_key.key, algorithms=["ES256"], audience="authenticated"
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _require_role(authorization: str | None, role: str) -> str:
    payload = _verify_token(authorization)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Token has no email claim")
    if payload.get("app_metadata", {}).get("role") != role:
        raise HTTPException(status_code=403, detail="Not permitted")
    return email


def get_current_student(authorization: str | None = Header(default=None)) -> str:
    return _require_role(authorization, "student")


def get_current_instructor(authorization: str | None = Header(default=None)) -> str:
    return _require_role(authorization, "instructor")
