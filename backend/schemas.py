"""Pydantic request and response contracts."""

from typing import Any, Literal
from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

# ChartData/DataTable are the agent response layer's own output contract
# (backend/agent/response/response_models.py); re-exported here so the API
# layer's ChatResponse can reference them without a second definition.
from .agent.response.response_models import ChartData, ChartSeries, DataTable


class ChatHistoryItem(BaseModel):
    """One bounded conversation turn supplied by the browser."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=3000)


class DashboardContext(BaseModel):
    """Structured dashboard scope supplied independently from the user message."""

    active_view: Literal["portfolio", "squad_detail", "chat"] | None = None
    project: str | None = Field(default=None, min_length=1, max_length=20)
    squad: str | None = Field(default=None, min_length=1, max_length=80)
    release: str | None = Field(default=None, min_length=1, max_length=120)
    sprint: str | None = Field(default=None, min_length=1, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    selected_metric: str | None = Field(default=None, min_length=1, max_length=80)
    selected_squad_row: dict[str, Any] | None = None
    current_metric_value: int | float | str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(
        default_factory=lambda: str(uuid4()), min_length=8, max_length=80
    )
    project_key: str | None = Field(default=None, min_length=2, max_length=16)
    conversation_id: UUID | None = None
    workspace: Literal["business", "technical"] = "technical"
    days: int | None = Field(default=None, ge=1, le=365)
    history: list[ChatHistoryItem] = Field(default_factory=list, max_length=12)
    dashboard_context: DashboardContext | None = None

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


class ChatResponse(BaseModel):
    answer: str
    intent: str
    metric: str | None = None
    chart: ChartData | None = None
    table: DataTable | None = None
    warnings: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class FollowUpQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=10_000)
    dashboard_context: DashboardContext | None = None


class FollowUpQuestionResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list, max_length=3)


class ConversationCreate(BaseModel):
    workspace: Literal["business", "technical"] = "technical"
    project_scope: dict[str, Any] = Field(default_factory=dict)
    first_question: str = Field(default="", max_length=2000)
    title: str | None = Field(default=None, min_length=1, max_length=160)


class ConversationMessageCreate(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=10_000)
    structured_content: dict[str, Any] = Field(default_factory=dict)


class ConversationMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    structured_content: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationSummaryResponse(BaseModel):
    id: str
    title: str
    workspace: Literal["business", "technical"]
    project_scope: dict[str, Any] = Field(default_factory=dict)
    dashboard_context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationSummaryResponse):
    messages: list[ConversationMessageResponse] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummaryResponse] = Field(default_factory=list)


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
    llm_model: str
    llm_configured: bool
    llm_available: bool
    tts_configured: bool
    detail: str | None = None


class JiraDashboardResponse(BaseModel):
    project_scope: dict[str, str]
    refreshed_at: datetime
    cached: bool
    empty: bool
    kpis: dict[str, int | float | None]
    status_categories: list[dict[str, str | int]]
    issue_types: list[dict[str, str | int]]
    open_ageing: list[dict[str, str | int]]
    data_quality: dict[str, int]
    notes: list[str]
