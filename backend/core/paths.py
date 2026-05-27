"""Path resolver — now Supabase-backed. Kept module name for backwards compat."""
from __future__ import annotations

from pathlib import Path

from core.storage import download_dataset_to_tmp


class FileNotInUploadDirError(Exception):
    """Kept for backwards compatibility with mcp_*.py error handling."""


def resolve_dataset_for_user(user_id: str, file_path: str) -> Path:
    """Resolve a 'file_path' (dataset id or filename) for the given user.

    The MCP tools accept either the dataset UUID or its original filename.
    Returns a local /tmp path that pandas/joblib can open directly.
    """
    if not file_path:
        raise FileNotInUploadDirError("file_path must be a non-empty string")
    try:
        return download_dataset_to_tmp(user_id, file_path)
    except FileNotFoundError as exc:
        raise FileNotInUploadDirError(str(exc)) from exc