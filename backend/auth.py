"""FastAPI auth dependency — modern Supabase-compatible JWT verification.

Verification strategy (in order):
  1. FAST PATH  — if SUPABASE_JWT_SECRET is set: local HS256 decode (no network).
  2. SLOW PATH  — if no secret: call Supabase Auth API GET /auth/v1/user with the
                  user's Bearer token. supabase-py handles it synchronously;
                  FastAPI runs sync deps in a thread pool so the event loop stays free.

Both paths produce the same AuthUser. No RuntimeError is raised when the secret
is absent — the API-validation path handles it transparently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings
from core.logger import get_logger

log = get_logger("auth")

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    """The verified user attached to a request."""
    id: str           # UUID — matches auth.users.id
    email: str | None
    role: str         # 'authenticated' | 'service_role' | etc.
    raw_token: str    # original JWT, forwarded to MCP tools when needed


# ── Fast path: local HS256 (only when SUPABASE_JWT_SECRET is configured) ──
def _local_hs256(token: str) -> AuthUser:
    """Decode + verify the JWT locally. Raises jwt.* on failure."""
    secret = settings.SUPABASE_JWT_SECRET  # already guaranteed non-empty by caller
    try:
        payload = jwt.decode(
            token, secret, algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
    except jwt.InvalidAudienceError:
        # Some Supabase projects omit or vary the 'aud' claim — retry without it.
        payload = jwt.decode(
            token, secret, algorithms=["HS256"],
            options={"verify_exp": True, "verify_aud": False},
        )
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise jwt.InvalidTokenError("Token missing 'sub' claim")
    return AuthUser(
        id=user_id,
        email=payload.get("email"),
        role=payload.get("role", "authenticated"),
        raw_token=token,
    )


# ── Slow path: Supabase Auth API (no JWT secret required) ─────────────────
def _supabase_api(token: str) -> AuthUser:
    """Validate the token via POST /auth/v1/user.

    supabase-py's auth.get_user(jwt) passes the provided JWT as the Bearer
    token, so the call validates against the user's own session — not the
    service-role key. Works with any valid Supabase project.
    """
    from core.supabase_client import get_anon_client

    try:
        client = get_anon_client()
        response = client.auth.get_user(token)
    except Exception as exc:
        log.warning("Supabase auth.get_user failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed — Supabase Auth API unavailable",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = getattr(response, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = getattr(user, "id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user ID",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthUser(
        id=str(user_id),
        email=getattr(user, "email", None),
        role=getattr(user, "role", None) or "authenticated",
        raw_token=token,
    )


# ── Public FastAPI dependency ──────────────────────────────────────────────
def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser:
    """FastAPI dependency. Every protected route should declare:

        user: Annotated[AuthUser, Depends(get_current_user)]
    """
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creds.credentials

    # ── Fast path ──────────────────────────────────────────────────────────
    if settings.SUPABASE_JWT_SECRET:
        try:
            return _local_hs256(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as exc:
            # Secret was set but decode failed — don't silently fall through to
            # the API path, as that could mask a misconfigured secret.
            log.warning("Local JWT decode failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # ── Slow path (no secret configured) ──────────────────────────────────
    log.debug(
        "SUPABASE_JWT_SECRET not set — validating token via Supabase Auth API. "
        "Set SUPABASE_JWT_SECRET in .env for faster local verification."
    )
    return _supabase_api(token)


def get_current_user_optional(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser | None:
    """Like get_current_user but returns None instead of 401 on missing/bad token."""
    if creds is None or not creds.credentials:
        return None
    try:
        return get_current_user(creds)
    except HTTPException:
        return None
