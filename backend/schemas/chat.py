from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    active_file: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, Any]
    result: Any
    error: str | None = None
    duration_ms: int


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallRecord]
    iterations: int


class UploadResponse(BaseModel):
    filename: str
    size_bytes: int
    rows: int
    columns: int
    column_names: list[str]


class DatasetItem(BaseModel):
    filename: str
    size_kb: float
    modified_unix: int


class DatasetListResponse(BaseModel):
    count: int
    files: list[DatasetItem]


class HealthResponse(BaseModel):
    status: str
    groq_configured: bool
    upload_dir: str
    output_dir: str
