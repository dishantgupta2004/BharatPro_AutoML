from pathlib import Path

from core.config import settings


class FileNotInUploadDirError(Exception):
    pass


def resolve_upload_file(file_path: str) -> Path:
    if not file_path:
        raise FileNotInUploadDirError("file_path must be a non-empty string")

    raw = Path(file_path)
    candidate = raw if raw.is_absolute() else (settings.upload_path / raw.name)
    candidate = candidate.resolve()

    upload_root = settings.upload_path.resolve()
    try:
        candidate.relative_to(upload_root)
    except ValueError as exc:
        raise FileNotInUploadDirError(
            f"Refusing to access path outside upload dir: {candidate}"
        ) from exc

    if not candidate.exists():
        raise FileNotFoundError(f"File not found: {candidate}")
    if not candidate.is_file():
        raise FileNotInUploadDirError(f"Not a regular file: {candidate}")

    return candidate


def output_file_path(filename: str) -> Path:
    safe = Path(filename).name
    return settings.output_path / safe
