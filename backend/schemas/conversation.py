from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ConversationListItem(BaseModel):
    id: str
    title: str
    active_file: str | None
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    conversations: list[ConversationListItem]


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None
    created_at: datetime


class ConversationMessages(BaseModel):
    id: str
    title: str
    active_file: str | None
    messages: list[MessageItem]