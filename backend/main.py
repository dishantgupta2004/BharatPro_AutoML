from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from core.config import settings
from core.logger import get_logger
from core.mcp_pool import MCPClientPool
from core.orchestrator import stream_chat
from database import Conversation, Message, derive_title, get_session, init_db
from schemas.chat import (
    ChatRequest,
    DatasetItem,
    DatasetListResponse,
    HealthResponse,
    UploadResponse,
)
from schemas.conversation import (
    ConversationList,
    ConversationListItem,
    ConversationMessages,
    MessageItem,
)

log = get_logger("api")

BASE_DIR = Path(__file__).resolve().parent
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = SAFE_FILENAME_RE.sub("_", base).strip("._")
    return cleaned or "upload.csv"


# ----------------------------------------------------------------------------
# Lifespan — bring up the MCPClientPool, tear it down cleanly
# ----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("SQLite ready at automl_local.db")
    pool = MCPClientPool()
    try:
        await pool.start()
    except Exception as exc:
        log.exception("Pool startup encountered errors (continuing): %s", exc)
    app.state.pool = pool

    # Background refresher: every 15s, try to reconnect offline services
    async def refresher() -> None:
        while True:
            await asyncio.sleep(15.0)
            try:
                await pool.refresh_all()
            except Exception as exc:
                log.warning("refresh_all failed: %s", exc)

    refresh_task = asyncio.create_task(refresher())
    try:
        yield
    finally:
        refresh_task.cancel()
        with contextlib_suppress(asyncio.CancelledError):
            await refresh_task
        await pool.shutdown()


def contextlib_suppress(*exc_types):
    import contextlib
    return contextlib.suppress(*exc_types)


app = FastAPI(
    title="Unisole Empower — Distributed AutoML Orchestrator",
    version="0.3.0",
    description="Multi-MCP backend coordinating 5 microservices over HTTP/SSE.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mounts ---------------------------------------------------------------
app.mount("/static/outputs", StaticFiles(directory=str(settings.output_path)), name="outputs")
app.mount("/static/reports", StaticFiles(directory=str(settings.reports_path)), name="reports")
app.mount("/static/plots", StaticFiles(directory=str(settings.plots_path)), name="plots")
app.mount("/static/models", StaticFiles(directory=str(settings.models_path)), name="models")


# ----------------------------------------------------------------------------
# Health & service registry
# ----------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        groq_configured=bool(settings.GROQ_API_KEY),
        upload_dir=str(settings.upload_path),
        output_dir=str(settings.output_path),
    )


@app.get("/api/services")
def services() -> JSONResponse:
    """Snapshot of all microservices' health, tool/resource/prompt counts."""
    pool: MCPClientPool = app.state.pool
    return JSONResponse(pool.snapshot())


@app.post("/api/services/refresh")
async def refresh_services() -> JSONResponse:
    pool: MCPClientPool = app.state.pool
    await pool.refresh_all()
    return JSONResponse(pool.snapshot())


@app.get("/api/services/stream")
async def services_stream() -> StreamingResponse:
    """SSE stream of service status changes — consumed by the Network panel."""
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
def list_prompts() -> JSONResponse:
    """Native MCP prompts available across the network — drives the slash menu."""
    pool: MCPClientPool = app.state.pool
    return JSONResponse({"prompts": pool.snapshot()["prompts"]})


# ----------------------------------------------------------------------------
# Datasets & upload
# ----------------------------------------------------------------------------
@app.get("/api/datasets", response_model=DatasetListResponse)
def datasets() -> DatasetListResponse:
    upload_dir = settings.upload_path
    files = []
    for entry in sorted(upload_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() in {".csv", ".tsv", ".parquet"}:
            st = entry.stat()
            files.append(
                DatasetItem(
                    filename=entry.name,
                    size_kb=round(st.st_size / 1024, 2),
                    modified_unix=int(st.st_mtime),
                )
            )
    return DatasetListResponse(count=len(files), files=files)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".csv", ".tsv"}:
        raise HTTPException(status_code=400, detail="Only .csv or .tsv files accepted.")

    safe_name = _safe_filename(file.filename)
    target_path = settings.upload_path / safe_name
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    with target_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                target_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB.",
                )
            out.write(chunk)

    try:
        df_head = pd.read_csv(target_path, nrows=1)
        full = pd.read_csv(target_path)
        rows, cols = int(full.shape[0]), int(full.shape[1])
        column_names = list(df_head.columns)
    except Exception as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse: {exc}") from exc

    return UploadResponse(
        filename=safe_name,
        size_bytes=total,
        rows=rows,
        columns=cols,
        column_names=column_names,
    )


# ----------------------------------------------------------------------------
# Conversation endpoints (unchanged from Phase 2)
# ----------------------------------------------------------------------------
@app.get("/api/conversations", response_model=ConversationList)
def list_conversations(db: Session = Depends(get_session)) -> ConversationList:
    rows = (
        db.query(Conversation)
        .order_by(Conversation.updated_at.desc())
        .limit(200)
        .all()
    )
    return ConversationList(
        conversations=[
            ConversationListItem(
                id=r.id,
                title=r.title,
                active_file=r.active_file,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]
    )


@app.get("/api/conversations/{conversation_id}/messages", response_model=ConversationMessages)
def get_conversation_messages(
    conversation_id: str, db: Session = Depends(get_session)
) -> ConversationMessages:
    convo = db.get(Conversation, conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationMessages(
        id=convo.id,
        title=convo.title,
        active_file=convo.active_file,
        messages=[
            MessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                tool_calls=json.loads(m.tool_calls) if m.tool_calls else None,
                created_at=m.created_at,
            )
            for m in convo.messages
        ],
    )


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, db: Session = Depends(get_session)) -> None:
    convo = db.get(Conversation, conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    db.delete(convo)
    db.commit()


# ----------------------------------------------------------------------------
# Chat (SSE streaming) — now routes through MCPClientPool
# ----------------------------------------------------------------------------
@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured.")

    pool: MCPClientPool = app.state.pool

    # Resolve native MCP prompt if invoked via /prompt-name syntax
    prompt_inject: str | None = None
    user_text = req.query.strip()
    if req.prompt_name:
        try:
            prompt_result = await pool.get_prompt(
                req.prompt_name, req.prompt_arguments or {}
            )
            # fastmcp prompts return a list of messages; flatten the text payload
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

    # Conversation persistence: get-or-create
    db: Session = next(get_session())
    try:
        if req.conversation_id:
            convo = db.get(Conversation, req.conversation_id)
            if not convo:
                raise HTTPException(status_code=404, detail="Conversation not found.")
        else:
            convo = Conversation(
                title=derive_title(req.query), active_file=req.active_file
            )
            db.add(convo)
            db.commit()
            db.refresh(convo)

        if req.active_file and req.active_file != convo.active_file:
            convo.active_file = req.active_file

        user_msg = Message(conversation_id=convo.id, role="user", content=req.query)
        db.add(user_msg)
        db.commit()

        conversation_id = convo.id
        conversation_title = convo.title

        if not req.history:
            stored = (
                db.query(Message)
                .filter(
                    Message.conversation_id == convo.id,
                    Message.role.in_(("user", "assistant")),
                )
                .order_by(Message.created_at.asc())
                .all()
            )
            history = [
                {"role": m.role, "content": m.content}
                for m in stored
                if m.id != user_msg.id and m.content
            ]
        else:
            history = [{"role": m.role, "content": m.content} for m in req.history]

    finally:
        db.close()

    active_file = req.active_file

    async def event_generator():
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "meta",
                    "conversation_id": conversation_id,
                    "title": conversation_title,
                    "prompt_name": req.prompt_name,
                }
            )
            + "\n\n"
        )

        full_text = ""
        final_tool_calls: list[dict] = []

        async for chunk in stream_chat(
            query=user_text,
            active_file=active_file,
            history=history,
            pool=pool,
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

        # Persist assistant turn
        db2: Session = next(get_session())
        try:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_text,
                tool_calls=json.dumps(final_tool_calls, default=str) if final_tool_calls else None,
            )
            db2.add(assistant_msg)
            convo = db2.get(Conversation, conversation_id)
            if convo:
                convo.active_file = active_file or convo.active_file
            db2.commit()
        finally:
            db2.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/download/{filename}")
def download_output(filename: str) -> FileResponse:
    safe = Path(filename).name
    for base in (
        settings.output_path,
        settings.reports_path,
        settings.plots_path,
        settings.models_path,
    ):
        cand = base / safe
        if cand.exists() and cand.is_file():
            return FileResponse(path=str(cand), filename=safe)
    raise HTTPException(status_code=404, detail="File not found.")


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse(
        {
            "name": "Unisole Empower — Distributed AutoML Orchestrator",
            "version": "0.3.0",
            "support_email": "unisole.empower@gmail.com",
            "endpoints": {
                "health": "/api/health",
                "services": "/api/services",
                "services_stream": "/api/services/stream",
                "prompts": "/api/prompts",
                "upload": "POST /api/upload",
                "chat": "POST /api/chat (SSE)",
                "datasets": "/api/datasets",
                "conversations": "/api/conversations",
                "static": "/static/{outputs|reports|plots|models}/{filename}",
            },
        }
    )