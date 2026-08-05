"""Typed application configuration loaded from the repository-level .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    assistant_database_schema: str = "ai_assistant"
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
    conversation_recent_message_limit: int = Field(default=12, ge=4, le=30)
    conversation_summary_trigger_messages: int = Field(default=12, ge=4, le=100)
    conversation_summary_max_chars: int = Field(default=3000, ge=500, le=10_000)
    query_result_cache_ttl_seconds: int = Field(default=300, ge=30, le=86_400)
    query_result_cache_max_entries: int = Field(default=6, ge=1, le=20)
    query_result_cache_max_rows: int = Field(default=100, ge=1, le=500)
    query_result_cache_max_chars: int = Field(default=30_000, ge=1000, le=200_000)
    jira_dashboard_cache_ttl_seconds: int = Field(default=60, ge=5, le=3600)

    llm_provider: Literal["google-ai-studio", "deepseek", "ollama"] = (
        "google-ai-studio"
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    deepseek_planner_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    deepseek_response_temperature: float = Field(default=0.3, ge=0.0, le=1.0)
    deepseek_thinking_enabled: bool = True
    deepseek_planner_max_tokens: int = Field(default=1600, ge=256, le=8192)
    deepseek_response_max_tokens: int = Field(default=3000, ge=256, le=8192)

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    deepseek_planner_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    deepseek_response_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    deepseek_thinking_enabled: bool = True
    deepseek_planner_max_tokens: int = Field(default=1600, ge=1, le=384_000)
    deepseek_response_max_tokens: int = Field(default=3000, ge=1, le=384_000)

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = Field(default=90.0, ge=1.0, le=300.0)
    ollama_planner_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    ollama_response_temperature: float = Field(default=0.3, ge=0.0, le=1.0)

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
    def deepseek_configured(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def ollama_configured(self) -> bool:
        return bool(self.ollama_base_url.strip() and self.ollama_model.strip())

    @property
    def deepseek_configured(self) -> bool:
        return bool(
            self.deepseek_api_key
            and self.deepseek_base_url.strip()
            and self.deepseek_model.strip()
        )

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "ollama":
            return self.ollama_configured
        if self.llm_provider == "deepseek":
            return self.deepseek_configured
        return self.gemini_configured

    @property
    def llm_model(self) -> str:
        if self.llm_provider == "ollama":
            return self.ollama_model
        if self.llm_provider == "deepseek":
            return self.deepseek_model
        return self.gemini_model

    @property
    def llm_source(self) -> str:
        return f"{self.llm_provider}:{self.llm_model}"

    @property
    def llm_planner_temperature(self) -> float:
        if self.llm_provider == "ollama":
            return self.ollama_planner_temperature
        if self.llm_provider == "deepseek":
            return self.deepseek_planner_temperature
        return self.gemini_planner_temperature

    @property
    def llm_response_temperature(self) -> float:
        if self.llm_provider == "ollama":
            return self.ollama_response_temperature
        if self.llm_provider == "deepseek":
            return self.deepseek_response_temperature
        return self.gemini_response_temperature

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
