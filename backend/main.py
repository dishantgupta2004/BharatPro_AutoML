from __future__ import annotations

import asyncio
import contextlib
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from auth import AuthUser, get_current_user
from core.config import settings
from core.logger import get_logger
from core.mcp_pool import MCPClientPool, register_default_servers
from core.orchestrator import stream_chat
from database import (
    create_conversation, delete_conversation as db_delete_conversation,
    derive_title, get_conversation, history_for_llm, init_db,
    insert_message, list_conversations as db_list_conversations,
    list_messages, touch_conversation,
)
from core.storage import (
    list_datasets, signed_url_for_artifact, upload_dataset,
)
from schemas.chat import (
    ChatRequest, DatasetItem, DatasetListResponse,
    HealthResponse, UploadResponse,
)
from schemas.conversation import (
    ConversationList, ConversationListItem,
    ConversationMessages, MessageItem,
)

log = get_logger("api")

SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = SAFE_FILENAME_RE.sub("_", base).strip("._")
    return cleaned or "upload.csv"


# ── Lifespan ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # Auth mode announcement
    if settings.SUPABASE_JWT_SECRET:
        log.info("Auth mode: LOCAL HS256 (SUPABASE_JWT_SECRET is set — fast path active)")
    else:
        log.warning(
            "Auth mode: SUPABASE API (SUPABASE_JWT_SECRET not set). "
            "Each request makes a network call to Supabase Auth to validate the token. "
            "For better performance, set SUPABASE_JWT_SECRET in .env "
            "(Supabase Dashboard → Settings → API → JWT Secret)."
        )

    pool = MCPClientPool()
    register_default_servers(pool)
    try:
        await pool.start()
    except Exception as exc:
        log.exception("Pool startup encountered errors (continuing): %s", exc)
    app.state.pool = pool

    async def refresher():
        while True:
            await asyncio.sleep(60.0)
            try:
                await pool.refresh_all()
            except Exception as exc:
                log.warning("refresh_all failed: %s", exc)

    refresh_task = asyncio.create_task(refresher())
    try:
        yield
    finally:
        refresh_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await refresh_task
        await pool.shutdown()


app = FastAPI(
    title="NSK AI Labs BharatPro AutoML — Orchestrator",
    version="1.0.0",
    description="AI-native AutoML platform by NSK AI Labs. In-process MCP backend with Supabase auth + storage.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: static mounts are gone — outputs live in Supabase Storage, served via
# signed URLs. The frontend already calls those URLs directly.


# ── Health & registry ───────────────────────────────────────────────
@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        groq_configured=bool(settings.GROQ_API_KEY),
        supabase_configured=bool(
            settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY
        ),
        auth_mode="local_hs256" if settings.SUPABASE_JWT_SECRET else "supabase_api",
    )


@app.get("/api/services")
def services(user: Annotated[AuthUser, Depends(get_current_user)]) -> JSONResponse:
    return JSONResponse(app.state.pool.snapshot())


@app.post("/api/services/refresh")
async def refresh_services(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> JSONResponse:
    await app.state.pool.refresh_all()
    return JSONResponse(app.state.pool.snapshot())


@app.get("/api/services/stream")
async def services_stream(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> StreamingResponse:
    pool: MCPClientPool = app.state.pool

    async def event_gen():
        async for evt in pool.status_event_stream():
            yield "data: " + json.dumps(evt, default=str) + "\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/prompts")
def list_prompts(user: Annotated[AuthUser, Depends(get_current_user)]) -> JSONResponse:
    return JSONResponse({"prompts": app.state.pool.snapshot()["prompts"]})


# ── Datasets & upload ───────────────────────────────────────────────
@app.get("/api/datasets", response_model=DatasetListResponse)
def datasets(user: Annotated[AuthUser, Depends(get_current_user)]) -> DatasetListResponse:
    rows = list_datasets(user.id)
    items = [
        DatasetItem(
            id=r["id"], filename=r["filename"],
            size_kb=round((r.get("size_bytes") or 0) / 1024, 2),
            rows=r.get("row_count"), columns=r.get("column_count"),
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]
    return DatasetListResponse(count=len(items), files=items)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_csv(
    user: Annotated[AuthUser, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> UploadResponse:
    if not file.filename:
        raise HTTPException(400, "No filename provided.")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".csv", ".tsv"}:
        raise HTTPException(400, "Only .csv or .tsv files accepted.")

    safe_name = _safe_filename(file.filename)
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    # Stream the upload to a tmp file so we can parse + then upload to Supabase.
    tmp_dir = settings.tmp_path / user.id / "ingest"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / safe_name

    total = 0
    with tmp_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {settings.MAX_UPLOAD_MB} MB.")
            out.write(chunk)

    try:
        head = pd.read_csv(tmp_path, nrows=1)
        full = pd.read_csv(tmp_path)
        rows, cols = int(full.shape[0]), int(full.shape[1])
        column_names = list(head.columns)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, f"Failed to parse: {exc}") from exc

    try:
        record = upload_dataset(
            user_id=user.id, filename=safe_name, local_path=tmp_path,
            row_count=rows, column_count=cols, column_names=column_names,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return UploadResponse(
        dataset_id=record.id, filename=safe_name,
        size_bytes=total, rows=rows, columns=cols,
        column_names=column_names,
    )


# ── Conversation endpoints ──────────────────────────────────────────
@app.get("/api/conversations", response_model=ConversationList)
def conversations(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> ConversationList:
    rows = db_list_conversations(user.id)
    return ConversationList(
        conversations=[
            ConversationListItem(
                id=r["id"], title=r["title"],
                active_file=r.get("active_file"),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]
    )


@app.get(
    "/api/conversations/{conversation_id}/messages",
    response_model=ConversationMessages,
)
def get_conversation_messages(
    conversation_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> ConversationMessages:
    convo = get_conversation(user.id, conversation_id)
    if not convo:
        raise HTTPException(404, "Conversation not found.")
    msgs = list_messages(user.id, conversation_id)
    return ConversationMessages(
        id=convo["id"], title=convo["title"],
        active_file=convo.get("active_file"),
        messages=[
            MessageItem(
                id=m["id"], role=m["role"], content=m["content"],
                tool_calls=m.get("tool_calls"),
                created_at=m["created_at"],
            )
            for m in msgs
        ],
    )


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation_endpoint(
    conversation_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> None:
    if not db_delete_conversation(user.id, conversation_id):
        raise HTTPException(404, "Conversation not found.")


# ── Chat (SSE) ──────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> StreamingResponse:
    if not settings.GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY is not configured.")

    pool: MCPClientPool = app.state.pool

    # Prompt template resolution
    prompt_inject: str | None = None
    if req.prompt_name:
        try:
            prompt_result = await pool.get_prompt(
                req.prompt_name, req.prompt_arguments or {}
            )
            if hasattr(prompt_result, "messages") and prompt_result.messages:
                parts: list[str] = []
                for m in prompt_result.messages:
                    content = getattr(m, "content", None)
                    if isinstance(content, str):
                        parts.append(content)
                    elif hasattr(content, "text"):
                        parts.append(content.text)
                    elif isinstance(content, list):
                        for block in content:
                            txt = getattr(block, "text", None)
                            if txt:
                                parts.append(txt)
                prompt_inject = "\n\n".join(parts)
            else:
                prompt_inject = str(prompt_result)
        except Exception as exc:
            log.warning("Prompt resolution failed: %s", exc)

    # Get-or-create conversation, scoped to user
    if req.conversation_id:
        convo = get_conversation(user.id, req.conversation_id)
        if not convo:
            raise HTTPException(404, "Conversation not found.")
    else:
        convo = create_conversation(
            user.id, title=derive_title(req.query),
            active_file=req.active_file, dataset_id=req.dataset_id,
        )

    if req.active_file and req.active_file != convo.get("active_file"):
        touch_conversation(user.id, convo["id"], active_file=req.active_file)

    user_msg = insert_message(
        user.id, convo["id"], role="user", content=req.query,
    )

    conversation_id = convo["id"]
    conversation_title = convo["title"]
    active_file = req.active_file or convo.get("active_file")

    if not req.history:
        history = history_for_llm(
            user.id, conversation_id, exclude_message_id=user_msg["id"]
        )
    else:
        history = [{"role": m.role, "content": m.content} for m in req.history]

    async def event_generator():
        yield ("data: " + json.dumps({
            "type": "meta", "conversation_id": conversation_id,
            "title": conversation_title, "prompt_name": req.prompt_name,
        }) + "\n\n")

        full_text = ""
        final_tool_calls: list[dict] = []

        async for chunk in stream_chat(
            query=req.query, active_file=active_file,
            history=history, pool=pool,
            user_id=user.id, conversation_id=conversation_id,
            prompt_inject=prompt_inject,
        ):
            try:
                payload = json.loads(chunk.removeprefix("data: ").strip())
            except (json.JSONDecodeError, AttributeError):
                payload = None
            if payload:
                if payload.get("type") == "token":
                    full_text += payload.get("content", "")
                elif payload.get("type") == "done":
                    full_text = payload.get("answer", full_text)
                    final_tool_calls = payload.get("tool_calls", [])
            yield chunk

        try:
            insert_message(
                user.id, conversation_id,
                role="assistant", content=full_text,
                tool_calls=final_tool_calls or None,
            )
            if active_file:
                touch_conversation(user.id, conversation_id, active_file=active_file)
        except Exception as exc:
            log.warning("Failed to persist assistant message: %s", exc)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Artifact signed-URL endpoint (replaces /api/download/{filename}) ─
@app.get("/api/artifacts/{artifact_id}/url")
def artifact_signed_url(
    artifact_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> JSONResponse:
    """Get a fresh signed URL for an artifact (validates ownership)."""
    try:
        url = signed_url_for_artifact(user.id, artifact_id)
    except PermissionError:
        raise HTTPException(403, "Not your artifact.")
    except FileNotFoundError:
        raise HTTPException(404, "Artifact not found.")
    return JSONResponse({"url": url, "ttl_seconds": settings.SIGNED_URL_TTL})


@app.get("/api/artifacts/{artifact_id}/redirect")
def artifact_redirect(
    artifact_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> RedirectResponse:
    """Redirect to a fresh signed URL — convenient for <a href> in the UI."""
    try:
        url = signed_url_for_artifact(user.id, artifact_id)
    except PermissionError:
        raise HTTPException(403, "Not your artifact.")
    except FileNotFoundError:
        raise HTTPException(404, "Artifact not found.")
    return RedirectResponse(url=url, status_code=307)


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse({
        "name": "NSK AI Labs BharatPro AutoML — Orchestrator",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "services": "/api/services (auth)",
            "services_stream": "/api/services/stream (auth)",
            "prompts": "/api/prompts (auth)",
            "upload": "POST /api/upload (auth)",
            "chat": "POST /api/chat (SSE, auth)",
            "datasets": "/api/datasets (auth)",
            "conversations": "/api/conversations (auth)",
            "artifact_url": "/api/artifacts/{id}/url (auth)",
        },
    })