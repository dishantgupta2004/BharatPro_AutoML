"""Singleton Supabase clients — anon (rarely used backend-side) and service-role.

Service-role bypasses RLS. We rely on explicit `user_id` filters in every query
to enforce per-user isolation. RLS is the second line of defense if the frontend
ever talks to Postgres directly with the anon key.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from core.config import settings
from core.logger import get_logger

log = get_logger("supabase")


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """Backend-only client with full DB + Storage privileges. Bypasses RLS."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )
    client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
        options=ClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )
    log.info("Supabase service-role client initialized")
    return client


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """Anon client — used only for verifying user JWTs via the Auth API.
    Not used for DB queries; we trust the verified JWT and query with service-role.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env"
        )
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
        options=ClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


# Convenience aliases
sb = get_service_client  # call as sb()