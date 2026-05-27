from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    active_file: str | None = None      # filename OR dataset UUID
    dataset_id: str | None = None       # explicit dataset uuid, preferred when known
    conversation_id: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)
    prompt_name: str | None = None
    prompt_arguments: dict[str, Any] | None = None


class ToolCallRecord(BaseModel):
    name: str
    service: str | None = None
    arguments: dict[str, Any]
    result: Any
    error: str | None = None
    duration_ms: int


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    size_bytes: int
    rows: int
    columns: int
    column_names: list[str]


class DatasetItem(BaseModel):
    id: str
    filename: str
    size_kb: float
    rows: int | None = None
    columns: int | None = None
    created_at: str


class DatasetListResponse(BaseModel):
    count: int
    files: list[DatasetItem]


class HealthResponse(BaseModel):
    status: str
    groq_configured: bool
    supabase_configured: bool