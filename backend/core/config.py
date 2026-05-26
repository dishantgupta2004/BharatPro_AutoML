from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False,
    )

    GROQ_API_KEY: str = GROQ_API_KEY or ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    UPLOAD_DIR: str = "./uploads"
    OUTPUT_DIR: str = "./outputs"
    MAX_TOOL_ITERATIONS: int = 8
    MAX_UPLOAD_MB: int = 200
    CORS_ORIGINS: str = "http://localhost:3000"

    # Microservice registry — all on local loopback
    MCP_DATA_URL: str = "http://127.0.0.1:8001/mcp"
    MCP_EDA_URL: str = "http://127.0.0.1:8002/mcp"
    MCP_MODELING_URL: str = "http://127.0.0.1:8003/mcp"
    MCP_EXPLAIN_URL: str = "http://127.0.0.1:8004/mcp"
    MCP_EXPORT_URL: str = "http://127.0.0.1:8005/mcp"

    @property
    def upload_path(self) -> Path:
        p = Path(self.UPLOAD_DIR).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def output_path(self) -> Path:
        p = Path(self.OUTPUT_DIR).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_path(self) -> Path:
        p = self.output_path / "reports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def plots_path(self) -> Path:
        p = self.output_path / "plots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def models_path(self) -> Path:
        p = self.output_path / "models"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def microservice_map(self) -> dict[str, str]:
        """Service id -> base URL (used by the multi-client pool)."""
        return {
            "mcp-data": self.MCP_DATA_URL,
            "mcp-eda": self.MCP_EDA_URL,
            "mcp-modeling": self.MCP_MODELING_URL,
            "mcp-explain": self.MCP_EXPLAIN_URL,
            "mcp-export": self.MCP_EXPORT_URL,
        }


settings = Settings()