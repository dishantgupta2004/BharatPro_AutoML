"""FastAPI auth dependency. Verifies Supabase JWT, returns the authenticated user."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings
from core.logger import get_logger

log = get_logger("auth")

# auto_error=False so we can return a cleaner 401 ourselves
_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    """The verified user attached to a request."""
    id: str           # UUID, matches auth.users.id and public.profiles.id
    email: str | None
    role: str         # 'authenticated' | 'service_role' | etc.
    raw_token: str    # original JWT, in case downstream needs it


def _verify_jwt(token: str) -> dict:
    """Decode and verify the JWT using the project's HS256 secret.

    Raises jwt.* exceptions on failure; caller maps these to 401.
    """
    if not settings.SUPABASE_JWT_SECRET:
        raise RuntimeError("SUPABASE_JWT_SECRET not configured")
    return jwt.decode(
        token,
        settings.SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
        options={"verify_exp": True},
    )


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser:
    """FastAPI dependency. Every protected route should declare `user: AuthUser = Depends(get_current_user)`."""
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = creds.credentials
    try:
        payload = _verify_jwt(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired", {"WWW-Authenticate": "Bearer"})
    except jwt.InvalidAudienceError:
        raise HTTPException(401, "Invalid token audience", {"WWW-Authenticate": "Bearer"})
    except jwt.InvalidTokenError as exc:
        log.warning("JWT decode failed: %s", exc)
        raise HTTPException(401, "Invalid token", {"WWW-Authenticate": "Bearer"})

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Token missing sub claim")

    return AuthUser(
        id=user_id,
        email=payload.get("email"),
        role=payload.get("role", "authenticated"),
        raw_token=token,
    )


def get_current_user_optional(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser | None:
    """Like get_current_user but returns None on missing/invalid token.
    Use for endpoints that work both authed and anonymous (rare here)."""
    if creds is None:
        return None
    try:
        return get_current_user(creds)
    except HTTPException:
        return None