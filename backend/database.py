"""Thin Postgres access layer via supabase-py. Replaces SQLAlchemy.

Every function takes user_id explicitly and filters on it — RLS-style isolation,
enforced at the application layer because we use service-role.
"""
from __future__ import annotations

import json
from typing import Any

from core.logger import get_logger
from core.supabase_client import sb

log = get_logger("db")


def init_db() -> None:
    """No-op kept for main.py compatibility. Schema is managed in Supabase SQL editor."""
    log.info("Postgres ready (Supabase) — schema managed via SQL migrations")


# ── Conversations ────────────────────────────────────────────────────
def derive_title(query: str, limit: int = 60) -> str:
    cleaned = " ".join(query.split())
    if len(cleaned) <= limit:
        return cleaned or "New Conversation"
    return cleaned[: limit - 1].rstrip() + "…"


def list_conversations(user_id: str, limit: int = 200) -> list[dict[str, Any]]:
    res = (
        sb().table("conversations")
        .select("id,title,active_file,created_at,updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_conversation(user_id: str, conversation_id: str) -> dict[str, Any] | None:
    res = (
        sb().table("conversations")
        .select("*")
        .eq("user_id", user_id)
        .eq("id", conversation_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def create_conversation(
    user_id: str, *, title: str, active_file: str | None = None,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    row = {
        "user_id": user_id,
        "title": title,
        "active_file": active_file,
        "dataset_id": dataset_id,
    }
    res = sb().table("conversations").insert(row).execute()
    return res.data[0]


def touch_conversation(
    user_id: str, conversation_id: str,
    *, active_file: str | None = None,
) -> None:
    patch: dict[str, Any] = {}
    if active_file is not None:
        patch["active_file"] = active_file
    if not patch:
        return
    (sb().table("conversations")
        .update(patch)
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute())


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    res = (
        sb().table("conversations")
        .delete()
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    return bool(res.data)


# ── Messages ─────────────────────────────────────────────────────────
def list_messages(user_id: str, conversation_id: str) -> list[dict[str, Any]]:
    res = (
        sb().table("messages")
        .select("*")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )
    rows = res.data or []
    for r in rows:
        if isinstance(r.get("tool_calls"), str):
            try:
                r["tool_calls"] = json.loads(r["tool_calls"])
            except (json.JSONDecodeError, TypeError):
                r["tool_calls"] = None
    return rows


def insert_message(
    user_id: str, conversation_id: str, *,
    role: str, content: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "tool_calls": tool_calls,  # jsonb column accepts list/dict directly
    }
    res = sb().table("messages").insert(row).execute()
    return res.data[0]


def history_for_llm(
    user_id: str, conversation_id: str, exclude_message_id: str | None = None,
) -> list[dict[str, str]]:
    """Return chat history shaped for the LLM (role+content only)."""
    rows = list_messages(user_id, conversation_id)
    out = []
    for r in rows:
        if exclude_message_id and r["id"] == exclude_message_id:
            continue
        if r["role"] not in ("user", "assistant"):
            continue
        if not r["content"]:
            continue
        out.append({"role": r["role"], "content": r["content"]})
    return out