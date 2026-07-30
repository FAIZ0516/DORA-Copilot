"""Typed application configuration loaded from the repository-level .env file."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings with safe local-prototype defaults."""

    app_name: str = "DORA Copilot"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = f"sqlite:///{(ROOT_DIR / 'backend' / 'dora_runtime.db').as_posix()}"
    result_limit: int = Field(default=1000, ge=1, le=5000)

    doradb_host: str = "127.0.0.1"
    doradb_port: int = Field(default=5432, ge=1, le=65535)
    doradb_name: str = "doradb"
    doradb_user: str = ""
    doradb_password: str = ""
    doradb_project_key: str = "DCPM"
    doradb_query_timeout_seconds: int = Field(default=10, ge=1, le=120)
    doradb_detail_limit: int = Field(default=50, ge=1, le=200)

    agent_max_tool_calls: int = Field(default=2, ge=1, le=5)
    agent_max_retries: int = Field(default=1, ge=0, le=2)
    agent_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    agent_workflow_timeout_seconds: int = Field(default=90, ge=10, le=300)
    agent_memory_max_sessions: int = Field(default=250, ge=10, le=5000)
    agent_memory_max_turns: int = Field(default=12, ge=2, le=30)
    agent_audit_max_records: int = Field(default=500, ge=10, le=10000)

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    gemini_planner_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    gemini_response_temperature: float = Field(default=0.3, ge=0.0, le=1.0)

    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    elevenlabs_output_format: str = "mp3_22050_32"
    elevenlabs_timeout_seconds: float = Field(default=45.0, ge=1.0, le=120.0)
    elevenlabs_max_chars_per_request: int = Field(default=2000, ge=1, le=5000)
    elevenlabs_monthly_char_limit: int = Field(default=10_000, ge=1, le=1_000_000)

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ROOT_DIR / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def doradb_configured(self) -> bool:
        """Credentials are required before the real database mode can start."""

        return bool(self.doradb_user and self.doradb_password)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def doradb_url(self) -> URL:
        """Build a URL without requiring callers to interpolate credentials."""

        return URL.create(
            "postgresql+psycopg2",
            username=self.doradb_user,
            password=self.doradb_password,
            host=self.doradb_host,
            port=self.doradb_port,
            database=self.doradb_name,
        )


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object for the process."""

    return Settings()


settings = get_settings()
