"""Pydantic request and response contracts."""

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ChatHistoryItem(BaseModel):
    """One bounded conversation turn supplied by the browser."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=3000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(
        default_factory=lambda: str(uuid4()), min_length=8, max_length=80
    )
    project_key: str | None = Field(default=None, min_length=2, max_length=16)
    days: int | None = Field(default=None, ge=1, le=365)
    history: list[ChatHistoryItem] = Field(default_factory=list, max_length=12)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message cannot be blank")
        return cleaned

    @field_validator("project_key")
    @classmethod
    def normalize_project(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class ChartSeries(BaseModel):
    key: str
    label: str
    unit: str = ""


class ChartData(BaseModel):
    type: Literal[
        "bar",
        "horizontal_bar",
        "stacked_bar",
        "line",
        "area",
        "pie",
        "donut",
        "scatter",
        "radar",
        "polar_area",
        "table",
        "metric_card",
    ]
    title: str
    x_key: str | None = None
    x_label: str | None = None
    point_label_key: str | None = None
    series: list[ChartSeries] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    unit: str = ""


class DataTable(BaseModel):
    title: str
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    truncated: bool = False


class ChatResponse(BaseModel):
    answer: str
    intent: str
    metric: str | None = None
    chart: ChartData | None = None
    table: DataTable | None = None
    warnings: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class SessionResetRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=80)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Text cannot be blank")
        return cleaned


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: str
    data_source: Literal["doradb"]
    database_connected: bool
    llm_provider: str
    llm_configured: bool
    tts_configured: bool
    detail: str | None = None
