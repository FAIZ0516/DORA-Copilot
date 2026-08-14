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


class ReportScope(BaseModel):
    """The slice of data a report describes."""

    project: str | None = Field(default=None, max_length=20)
    squad: str | None = Field(default=None, max_length=80)
    sprint: str | None = Field(default=None, max_length=200)
    release: str | None = Field(default=None, max_length=120)
    date_from: date | None = None
    date_to: date | None = None
    feature: str | None = Field(default=None, max_length=120)
    issue_type: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, max_length=80)
    priority: str | None = Field(default=None, max_length=80)

    @field_validator(
        "project", "squad", "sprint", "release", "feature",
        "issue_type", "status", "priority", mode="before",
    )
    @classmethod
    def normalize_scope_label(cls, value: Any) -> Any:
        if value is None:
            return None
        cleaned = str(value).strip()
        if cleaned.casefold() in {
            "all projects", "all squads", "all sprints", "all releases",
            "all visible features", "all features", "all tickets",
            "all ticket types", "all statuses", "all priorities",
        }:
            return None
        return cleaned or None

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def normalize_all_dates(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().casefold() == "all available dates":
            return None
        return value or None

    @field_validator("project")
    @classmethod
    def normalize_report_project(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class ReportCreateRequest(BaseModel):
    template: str = Field(default="blank", max_length=60)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    audience: str = Field(default="delivery_manager", max_length=40)
    tone: str = Field(default="professional", max_length=40)
    detail_level: str = Field(default="standard", max_length=20)
    include_recommendations: bool = True
    scope: ReportScope | None = None


class ReportRefineRequest(BaseModel):
    section_id: UUID
    instruction: str = Field(min_length=1, max_length=500)

    @field_validator("instruction")
    @classmethod
    def clean_instruction(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Instruction cannot be blank")
        return cleaned


class ReportUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    audience: str | None = Field(default=None, max_length=40)
    tone: str | None = Field(default=None, max_length=40)
    detail_level: str | None = Field(default=None, max_length=20)
    include_recommendations: bool | None = None
    status: str | None = Field(default=None, max_length=20)
    scope: ReportScope | None = None


class ReportApplyTemplateRequest(BaseModel):
    template: str = Field(max_length=60)


class ReportSectionCreateRequest(BaseModel):
    type: str = Field(max_length=40)
    title: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=20_000)
    payload: dict[str, Any] | None = None
    position: int | None = Field(default=None, ge=1, le=200)


class ReportSectionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=20_000)
    payload: dict[str, Any] | None = None
    visible: bool | None = None
    content_mode: str | None = Field(default=None, max_length=20)
    content_classification: str | None = Field(default=None, max_length=30)


class ReportReorderRequest(BaseModel):
    section_ids: list[UUID] = Field(min_length=1, max_length=200)


class ReportSourceRequest(BaseModel):
    conversation_id: UUID
    message_id: UUID
    selection: str = Field(default="full", max_length=20)
    content_mode: str = Field(default="rewrite", max_length=20)


class ReportComposeRequest(BaseModel):
    section_ids: list[UUID] = Field(default_factory=list, max_length=100)


class ReportDuplicateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class ReportExportRequest(BaseModel):
    format: Literal["pdf", "docx", "csv"] = "pdf"
    section_id: UUID | None = None
    preview: bool = False


class ReportSectionResponse(BaseModel):
    id: UUID
    type: str
    title: str
    content: str
    payload: dict[str, Any] | None = None
    position: int
    visible: bool
    content_mode: str
    content_classification: str
    manually_edited: bool
    needs_review: bool
    state: Literal["ready", "needs_input", "needs_review"] = "needs_input"
    state_reason: str = ""
    source_ids: list[str] = Field(default_factory=list)


class ReportSourceResponse(BaseModel):
    id: UUID
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    selection: str
    label: str = ""
    question: str = ""
    scope: dict[str, Any] = Field(default_factory=dict)
    query_ids: list[str] = Field(default_factory=list)
    row_counts: list[Any] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    has_chart: bool = False
    has_table: bool = False
    data_as_of: datetime | None = None


class ReportResponse(BaseModel):
    id: UUID
    title: str
    template: str
    status: str
    audience: str
    tone: str
    detail_level: str
    include_recommendations: bool
    scope: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    version: int
    created_at: datetime
    updated_at: datetime
    data_as_of: datetime | None = None
    last_validated_at: datetime | None = None
    last_exported_at: datetime | None = None
    freshness: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[ReportSectionResponse] = Field(default_factory=list)
    sources: list[ReportSourceResponse] = Field(default_factory=list)


class ReportSummaryResponse(BaseModel):
    id: UUID
    title: str
    template: str
    status: str
    scope: dict[str, Any] = Field(default_factory=dict)
    version: int
    updated_at: datetime
    data_as_of: datetime | None = None
    last_exported_at: datetime | None = None
    section_count: int = 0
    source_count: int = 0
    freshness: dict[str, Any] = Field(default_factory=dict)


class ReportListResponse(BaseModel):
    reports: list[ReportSummaryResponse] = Field(default_factory=list)


class ReportTemplateResponse(BaseModel):
    templates: list[dict[str, Any]] = Field(default_factory=list)
    audiences: list[str] = Field(default_factory=list)
    tones: list[str] = Field(default_factory=list)
    detail_levels: list[str] = Field(default_factory=list)
    section_types: list[str] = Field(default_factory=list)
    content_modes: list[str] = Field(default_factory=list)
    selections: list[str] = Field(default_factory=list)


class ReportComposeResponse(BaseModel):
    report: ReportResponse
    updated_sections: list[UUID] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
