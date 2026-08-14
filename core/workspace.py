"""Local filesystem workspace — replaces the Supabase storage layer.

Two flat registries:
  * datasets  — uploaded input files (CSV/TSV/Parquet), keyed by filename.
  * artifacts — generated outputs (plots, models, notebooks, PDFs).

No user scoping, no signed URLs, no database. Everything lives under
`settings.data_path` on disk. Fine for a single-user research tool.
"""
from __future__ import annotations

import json
import mimetypes
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.config import settings
from core.logger import get_logger

log = get_logger("workspace")


# ── Paths ────────────────────────────────────────────────────────────
def _uploads() -> Path:
    return settings.uploads_path


def _artifacts() -> Path:
    return settings.artifacts_path


def _artifacts_index() -> Path:
    return _artifacts() / "_index.json"


def _safe_stem(name: str) -> str:
    base = Path(name).name
    stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in base).strip(".")
    return stem or "file"


def _mime_for(path: Path) -> str:
    guess, _ = mimetypes.guess_type(path.name)
    return guess or "application/octet-stream"


# ── Dataset registry ─────────────────────────────────────────────────
@dataclass
class DatasetRecord:
    id: str
    filename: str
    path: str  # absolute path on disk
    size_bytes: int
    row_count: int | None = None
    column_count: int | None = None
    column_names: list[str] | None = None
    created_at: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def save_uploaded_dataset(
    filename: str,
    data: bytes,
    *,
    row_count: int | None = None,
    column_count: int | None = None,
    column_names: list[str] | None = None,
) -> DatasetRecord:
    """Persist an uploaded dataset under data/uploads/ and return the record."""
    safe = _safe_stem(filename)
    dest = _uploads() / safe
    if dest.exists():
        stem = Path(safe).stem
        suffix = Path(safe).suffix
        dest = _uploads() / f"{stem}_{int(time.time())}{suffix}"
    dest.write_bytes(data)
    return DatasetRecord(
        id=str(uuid.uuid4()),
        filename=dest.name,
        path=str(dest.resolve()),
        size_bytes=len(data),
        row_count=row_count,
        column_count=column_count,
        column_names=column_names,
    )


def list_datasets() -> list[dict[str, Any]]:
    """List all files in the uploads directory."""
    out: list[dict[str, Any]] = []
    for p in sorted(_uploads().iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.name.startswith("_"):
            continue
        st = p.stat()
        out.append({
            "filename": p.name,
            "path": str(p.resolve()),
            "size_bytes": st.st_size,
            "created_at": st.st_mtime,
        })
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out


def resolve_dataset(file_ref: str) -> Path:
    """Resolve a filename (or bare basename) to a local path under data/uploads."""
    if not file_ref:
        raise FileNotFoundError("file_path must be a non-empty string")
    candidate = Path(file_ref)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    direct = _uploads() / candidate.name
    if direct.exists():
        return direct
    for p in _uploads().iterdir():
        if p.name == file_ref or p.stem == file_ref:
            return p
    raise FileNotFoundError(
        f"Dataset not found: {file_ref}. Upload it via the Streamlit sidebar first."
    )


# ── Artifact registry ────────────────────────────────────────────────
@dataclass
class ArtifactRecord:
    id: str
    kind: str          # plot | model | xtrain_sample | training_notebook | pdf_report | ...
    category: str      # subfolder: plots | models | notebooks | reports | misc
    filename: str
    path: str
    size_bytes: int
    mime_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_KIND_TO_CATEGORY = {
    "plot": "plots",
    "model": "models",
    "xtrain_sample": "models",
    "training_notebook": "notebooks",
    "eda_notebook": "notebooks",
    "feature_eng_notebook": "notebooks",
    "pdf_report": "reports",
    "report": "reports",
    "csv_export": "exports",
    "zip": "exports",
}


def _load_artifact_index() -> list[dict[str, Any]]:
    idx = _artifacts_index()
    if not idx.exists():
        return []
    try:
        return json.loads(idx.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_artifact_index(records: list[dict[str, Any]]) -> None:
    _artifacts_index().write_text(
        json.dumps(records, indent=2, default=str), encoding="utf-8"
    )


def save_artifact(
    *,
    local_path: Path,
    kind: str,
    metadata: dict[str, Any] | None = None,
    move: bool = True,
) -> ArtifactRecord:
    """Register a generated file as an artifact.

    The file is moved (or copied) under data/artifacts/<category>/. Metadata is
    written to data/artifacts/_index.json for later listing.
    """
    if not local_path.exists():
        raise FileNotFoundError(f"Cannot register non-existent file: {local_path}")

    category = _KIND_TO_CATEGORY.get(kind, "misc")
    dest_dir = _artifacts() / category
    dest_dir.mkdir(parents=True, exist_ok=True)

    artifact_id = str(uuid.uuid4())
    safe = _safe_stem(local_path.name)
    dest_path = dest_dir / f"{artifact_id[:8]}__{safe}"

    if move:
        shutil.move(str(local_path), dest_path)
    else:
        shutil.copy2(local_path, dest_path)

    record = ArtifactRecord(
        id=artifact_id,
        kind=kind,
        category=category,
        filename=local_path.name,
        path=str(dest_path.resolve()),
        size_bytes=dest_path.stat().st_size,
        mime_type=_mime_for(dest_path),
        metadata=metadata or {},
    )

    idx = _load_artifact_index()
    idx.append(record.to_dict())
    _write_artifact_index(idx)

    log.info("Artifact saved: kind=%s id=%s", kind, artifact_id)
    return record


def save_artifact_bytes(
    *,
    filename: str,
    data: bytes,
    kind: str,
    metadata: dict[str, Any] | None = None,
) -> ArtifactRecord:
    tmp = settings.tmp_path / f"upload_{int(time.time()*1000)}_{_safe_stem(filename)}"
    tmp.write_bytes(data)
    return save_artifact(local_path=tmp, kind=kind, metadata=metadata, move=True)


def list_artifacts(kind: str | None = None) -> list[dict[str, Any]]:
    records = _load_artifact_index()
    if kind:
        records = [r for r in records if r.get("kind") == kind]
    records.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return records


def get_artifact(artifact_id: str) -> dict[str, Any]:
    for r in _load_artifact_index():
        if r["id"] == artifact_id:
            return r
    raise FileNotFoundError(f"Artifact not found: {artifact_id}")


def artifact_path(artifact_id: str) -> Path:
    row = get_artifact(artifact_id)
    return Path(row["path"])
