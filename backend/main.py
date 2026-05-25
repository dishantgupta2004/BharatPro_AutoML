from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.logger import get_logger
from core.orchestrator import run_chat
from schemas.chat import (
    ChatRequest,
    ChatResponse,
    DatasetItem,
    DatasetListResponse,
    HealthResponse,
    UploadResponse,
)
from tools.data_analysis import list_uploaded_files

log = get_logger("api")

BASE_DIR = Path(__file__).resolve().parent
MCP_SERVER_SCRIPT = str(BASE_DIR / "mcp_server.py")

SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = SAFE_FILENAME_RE.sub("_", base).strip("._")
    return cleaned or "upload.csv"


app = FastAPI(
    title="AutoML MCP Platform — Phase 1",
    version="0.1.0",
    description="FastAPI backend acting as an MCP client + Groq orchestrator.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/static/outputs",
    StaticFiles(directory=str(settings.output_path)),
    name="outputs",
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        groq_configured=bool(settings.GROQ_API_KEY),
        upload_dir=str(settings.upload_path),
        output_dir=str(settings.output_path),
    )


@app.get("/api/datasets", response_model=DatasetListResponse)
def datasets() -> DatasetListResponse:
    raw = list_uploaded_files()
    files = [DatasetItem(**f) for f in raw["files"]]
    return DatasetListResponse(count=raw["count"], files=files)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".csv", ".tsv"}:
        raise HTTPException(status_code=400, detail="Only .csv or .tsv files are accepted.")

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
                    detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_MB} MB.",
                )
            out.write(chunk)

    try:
        df = pd.read_csv(target_path, nrows=1)
        full = pd.read_csv(target_path)
        rows, cols = int(full.shape[0]), int(full.shape[1])
        column_names = list(df.columns)
    except Exception as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}") from exc

    log.info("Uploaded file=%s bytes=%d rows=%d cols=%d", safe_name, total, rows, cols)
    return UploadResponse(
        filename=safe_name,
        size_bytes=total,
        rows=rows,
        columns=cols,
        column_names=column_names,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY is not configured. Add it to backend/.env",
        )
    try:
        return await run_chat(
            query=req.query,
            active_file=req.active_file,
            history=req.history,
            mcp_server_script=MCP_SERVER_SCRIPT,
        )
    except Exception as exc:
        log.exception("Chat orchestration failed")
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc


@app.get("/api/download/{filename}")
def download_output(filename: str) -> FileResponse:
    safe = Path(filename).name
    path = settings.output_path / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path=str(path), filename=safe)


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse(
        {
            "name": "AutoML MCP Platform — Phase 1",
            "endpoints": {
                "health": "/api/health",
                "upload": "POST /api/upload",
                "chat": "POST /api/chat",
                "datasets": "/api/datasets",
                "download": "/api/download/{filename}",
                "static_outputs": "/static/outputs/{filename}",
            },
        }
    )
