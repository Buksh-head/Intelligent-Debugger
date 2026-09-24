"""Verifies Supabase-issued JWTs to gate instructor-only routes (#5, #17).

Supabase Auth signs JWTs with an asymmetric key (ES256); the matching
public key is fetched from the project's JWKS endpoint and cached by
PyJWT's PyJWKClient - no shared secret is involved. Student submissions
stay anonymous and never touch this - only instructor accounts
(registered via Supabase Auth's email/password) authenticate through
this dependency.
"""
import os
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    supabase_url = os.environ.get("SUPABASE_URL")
    if not supabase_url:
        raise RuntimeError("SUPABASE_URL must be set to verify instructor logins")
    return jwt.PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json")


def get_current_instructor(authorization: str | None = Header(default=None)) -> str:
    """Returns the authenticated instructor's email, or raises 401 if the
    Authorization header is missing or the token is invalid/expired.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ")
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(token, signing_key.key, algorithms=["ES256"], audience="authenticated")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Token has no email claim")
    return email
