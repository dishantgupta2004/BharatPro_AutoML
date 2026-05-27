"""Unified storage helper for datasets + artifacts.

Every read goes: Supabase Storage -> /tmp/<scoped path> (cached).
Every write goes: local file/bytes -> Supabase Storage + artifacts row.
Every returned URL is a short-lived signed URL.
"""
from __future__ import annotations

import hashlib
import mimetypes
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import settings
from core.logger import get_logger
from supabase_client import sb

log = get_logger("storage")


# ── tmp workspace helpers ────────────────────────────────────────────
def _scoped_tmp_dir(user_id: str) -> Path:
    p = settings.tmp_path / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_stem(name: str) -> str:
    base = Path(name).name
    stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in base).strip(".")
    return stem or "file"


def _mime_for(path: Path) -> str:
    guess, _ = mimetypes.guess_type(path.name)
    return guess or "application/octet-stream"


# ── Dataset ops ──────────────────────────────────────────────────────
@dataclass
class DatasetRecord:
    id: str
    user_id: str
    filename: str
    storage_path: str  # "<user_id>/<id>.csv"
    size_bytes: int
    row_count: int | None
    column_count: int | None
    column_names: list[str] | None


def upload_dataset(
    user_id: str,
    filename: str,
    local_path: Path,
    *,
    project_id: str | None = None,
    row_count: int | None = None,
    column_count: int | None = None,
    column_names: list[str] | None = None,
) -> DatasetRecord:
    """Upload a CSV to the `datasets` bucket and insert a row in public.datasets."""
    safe = _safe_stem(filename)
    dataset_id = str(uuid.uuid4())
    object_path = f"{user_id}/{dataset_id}__{safe}"
    size = local_path.stat().st_size

    client = sb()
    with local_path.open("rb") as fh:
        client.storage.from_(settings.BUCKET_DATASETS).upload(
            path=object_path,
            file=fh,
            file_options={
                "content-type": _mime_for(local_path),
                "upsert": "false",
            },
        )

    row = {
        "id": dataset_id,
        "user_id": user_id,
        "project_id": project_id,
        "filename": filename,
        "storage_path": object_path,
        "size_bytes": size,
        "row_count": row_count,
        "column_count": column_count,
        "column_names": column_names,
    }
    client.table("datasets").insert(row).execute()
    log.info("Dataset uploaded: user=%s id=%s", user_id, dataset_id)
    return DatasetRecord(
        id=dataset_id, user_id=user_id, filename=filename,
        storage_path=object_path, size_bytes=size,
        row_count=row_count, column_count=column_count,
        column_names=column_names,
    )


def list_datasets(user_id: str) -> list[dict[str, Any]]:
    res = (
        sb().table("datasets")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def get_dataset(user_id: str, dataset_id: str) -> dict[str, Any] | None:
    res = (
        sb().table("datasets")
        .select("*")
        .eq("user_id", user_id)
        .eq("id", dataset_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def get_dataset_by_filename(user_id: str, filename: str) -> dict[str, Any] | None:
    res = (
        sb().table("datasets")
        .select("*")
        .eq("user_id", user_id)
        .eq("filename", filename)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def download_dataset_to_tmp(user_id: str, dataset_id_or_filename: str) -> Path:
    """Resolve a dataset by id (UUID) or filename, download to /tmp/<user>/, return local path.

    Caches in tmp dir keyed by hash(storage_path); skips redownload if present.
    """
    # Resolve to a row
    row: dict[str, Any] | None = None
    try:
        uuid.UUID(dataset_id_or_filename)
        row = get_dataset(user_id, dataset_id_or_filename)
    except ValueError:
        row = get_dataset_by_filename(user_id, dataset_id_or_filename)
    if not row:
        raise FileNotFoundError(
            f"Dataset not found for user {user_id}: {dataset_id_or_filename}"
        )

    object_path: str = row["storage_path"]
    cache_dir = _scoped_tmp_dir(user_id)
    digest = hashlib.sha1(object_path.encode()).hexdigest()[:12]
    suffix = Path(row["filename"]).suffix or ".csv"
    local_path = cache_dir / f"ds_{digest}{suffix}"

    if local_path.exists() and local_path.stat().st_size == (row.get("size_bytes") or 0):
        return local_path

    blob = sb().storage.from_(settings.BUCKET_DATASETS).download(object_path)
    local_path.write_bytes(blob)
    log.info("Dataset cached: %s -> %s (%d bytes)", object_path, local_path, len(blob))
    return local_path


# ── Artifact ops (generic — used by every MCP tool that produces files) ─
@dataclass
class ArtifactRecord:
    id: str
    bucket: str
    storage_path: str
    filename: str
    signed_url: str


def upload_artifact(
    *,
    user_id: str,
    bucket: str,
    local_path: Path,
    kind: str,
    conversation_id: str | None = None,
    job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ArtifactRecord:
    """Upload a generated file to storage, insert artifacts row, return signed URL.

    `kind` must match the artifacts.kind CHECK constraint:
      eda_notebook | feature_eng_notebook | training_notebook | report | plot |
      model | xtrain_sample | csv_export | pdf_report | zip
    """
    if not local_path.exists():
        raise FileNotFoundError(f"Cannot upload non-existent file: {local_path}")

    artifact_id = str(uuid.uuid4())
    safe = _safe_stem(local_path.name)
    object_path = f"{user_id}/{artifact_id}__{safe}"
    mime = _mime_for(local_path)
    size = local_path.stat().st_size

    client = sb()
    with local_path.open("rb") as fh:
        client.storage.from_(bucket).upload(
            path=object_path,
            file=fh,
            file_options={"content-type": mime, "upsert": "false"},
        )

    row = {
        "id": artifact_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "job_id": job_id,
        "kind": kind,
        "bucket": bucket,
        "storage_path": object_path,
        "filename": local_path.name,
        "mime_type": mime,
        "size_bytes": size,
        "metadata": metadata or {},
    }
    client.table("artifacts").insert(row).execute()

    signed = create_signed_url(bucket, object_path)
    log.info("Artifact uploaded: kind=%s bucket=%s id=%s", kind, bucket, artifact_id)
    return ArtifactRecord(
        id=artifact_id, bucket=bucket, storage_path=object_path,
        filename=local_path.name, signed_url=signed,
    )


def upload_artifact_bytes(
    *,
    user_id: str,
    bucket: str,
    filename: str,
    data: bytes,
    kind: str,
    conversation_id: str | None = None,
    job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ArtifactRecord:
    """Upload from a bytes buffer (no local file needed). Writes to tmp first for upload()."""
    tmp = _scoped_tmp_dir(user_id) / f"upload_{int(time.time()*1000)}_{_safe_stem(filename)}"
    tmp.write_bytes(data)
    try:
        return upload_artifact(
            user_id=user_id, bucket=bucket, local_path=tmp, kind=kind,
            conversation_id=conversation_id, job_id=job_id, metadata=metadata,
        )
    finally:
        tmp.unlink(missing_ok=True)


def create_signed_url(bucket: str, object_path: str, ttl: int | None = None) -> str:
    """Generate a short-lived signed URL for a bucket object."""
    ttl = ttl or settings.SIGNED_URL_TTL
    resp = sb().storage.from_(bucket).create_signed_url(object_path, ttl)
    # supabase-py returns {"signedURL": "..."} or {"signedUrl": "..."} depending on version
    url = resp.get("signedURL") or resp.get("signedUrl") or resp.get("signed_url")
    if not url:
        raise RuntimeError(f"Failed to create signed URL: {resp}")
    return url


def signed_url_for_artifact(user_id: str, artifact_id: str) -> str:
    """Look up an artifact, verify ownership, return a fresh signed URL."""
    res = (
        sb().table("artifacts")
        .select("bucket,storage_path,user_id")
        .eq("id", artifact_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise FileNotFoundError(f"Artifact {artifact_id} not found")
    row = rows[0]
    if row["user_id"] != user_id:
        raise PermissionError(f"Artifact {artifact_id} does not belong to user")
    return create_signed_url(row["bucket"], row["storage_path"])


def download_artifact_to_tmp(user_id: str, artifact_id: str) -> Path:
    """Used when an MCP tool needs a previously-produced artifact (e.g. SHAP needs the joblib model)."""
    res = (
        sb().table("artifacts")
        .select("*")
        .eq("id", artifact_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise FileNotFoundError(f"Artifact {artifact_id} not found for user")
    row = rows[0]

    cache_dir = _scoped_tmp_dir(user_id)
    local = cache_dir / f"art_{artifact_id}__{_safe_stem(row['filename'])}"
    if local.exists() and local.stat().st_size == (row.get("size_bytes") or 0):
        return local

    blob = sb().storage.from_(row["bucket"]).download(row["storage_path"])
    local.write_bytes(blob)
    return local