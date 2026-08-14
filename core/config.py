"""Application settings — local, no cloud."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        extra="ignore", case_sensitive=False,
    )

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    MAX_TOOL_ITERATIONS: int = 8
    MAX_UPLOAD_MB: int = 200

    DATA_DIR: str = str(REPO_ROOT / "data")

    @property
    def data_path(self) -> Path:
        p = Path(self.DATA_DIR).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def uploads_path(self) -> Path:
        p = self.data_path / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def artifacts_path(self) -> Path:
        p = self.data_path / "artifacts"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def tmp_path(self) -> Path:
        p = self.data_path / "tmp"
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
