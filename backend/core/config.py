"""Pydantic settings — Supabase-first, no local-fs assumptions."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        extra="ignore", case_sensitive=False,
    )

    # LLM
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    MAX_TOOL_ITERATIONS: int = 8
    MAX_UPLOAD_MB: int = 200

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    # Optional: set this for fast local JWT verification (HS256).
    # Without it, auth falls back to Supabase Auth API validation (slower but always works).
    # Find it at: Supabase Dashboard → Settings → API → JWT Secret
    SUPABASE_JWT_SECRET: str = ""

    # Buckets
    BUCKET_DATASETS: str = "datasets"
    BUCKET_REPORTS: str = "reports"
    BUCKET_PLOTS: str = "plots"
    BUCKET_MODELS: str = "models"
    BUCKET_EXPORTS: str = "exports"

    # Signed URLs
    SIGNED_URL_TTL: int = 3600  # 1h

    # Tmp workspace (ephemeral, per-process). On Render this is fine — used for
    # download → process → upload cycles, no persistence expected.
    TMP_DIR: str = "/tmp/bharatpro"

    @property
    def tmp_path(self) -> Path:
        p = Path(self.TMP_DIR).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()