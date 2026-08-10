"""FastAPI entry point for the DoraDB-only conversational AI application."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .agent_system.audit import audit_log
from .agent_system.control import public_policy
from .agent_system.memory import memory_store
from .config import settings
from .conversation_context import persistent_context, recent_history, update_persistent_state
from .conversation_repository import ConversationRepository, serialize_conversation, serialize_message
from .db import ZaraWorkflow, get_db, init_db
from .dashboard_registry import ATTENTION_THRESHOLDS, UNSUPPORTED_METRICS, public_metric_registry
from .dashboard_service import (
    ISSUE_SORT_FIELDS,
    UnknownSquadError,
    get_dashboard_filter_options,
    get_dashboard_issues,
    get_dashboard_squads,
    get_jira_dashboard,
    get_portfolio_dashboard,
    get_squad_dashboard,
)
from .doradb import (
    DoraDbConfigurationError,
    DoraDbQueryRejected,
    check_doradb,
    doradb_session,
)
from .doradb_agent import DoraDbAgent
from .doradb_catalog import METRIC_DEFINITIONS, QUERY_CATALOGUE
from .llm import GenerativeAIClient
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationSummaryResponse,
    HealthResponse,
    JiraDashboardResponse,
    SessionResetRequest,
    TTSRequest,
)
from .tts import (
    TTSNotConfiguredError,
    TTSProviderError,
    TTSQuotaExceededError,
    create_audio_stream,
)
from .zara_workspace import (
    VisualizationQueryRequest,
    VisualizationRecommendRequest,
    WorkflowDefinition,
    WorkflowRunRequest,
    ZaraWorkspaceError,
    get_dataset_schema,
    get_dataset_values,
    list_datasets,
    query_visualization,
    recommend_visualizations,
    run_workflow,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize the writable runtime store; analytical DoraDB remains read-only.
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "Configured-LLM conversational DORA intelligence over the real, "
        "read-only PostgreSQL DoraDB dataset."
    ),
    version="0.4.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "X-Development-Session"],
)


def development_session(
    value: str = Header(default="local-development", alias="X-Development-Session"),
) -> str:
    """Temporary browser identity for development; replace with authenticated user IDs."""

    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,120}", cleaned):
        raise HTTPException(status_code=400, detail="Invalid development session identifier.")
    return cleaned


def _zara_read(operation: Callable[[Session], Any]) -> Any:
    """Run one Zara operation against the governed read-only DoraDB session."""

    try:
        with doradb_session() as real_session:
            return operation(real_session)
    except ZaraWorkspaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.warning("Zara DoraDB operation failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="DoraDB could not complete the workspace request."
        ) from exc


@app.get("/api/datasets")
def zara_datasets() -> list[dict[str, Any]]:
    return _zara_read(list_datasets)


@app.get("/api/datasets/{dataset_id}/schema")
def zara_dataset_schema(dataset_id: str) -> dict[str, Any]:
    return _zara_read(lambda session: get_dataset_schema(session, dataset_id))


@app.get("/api/datasets/{dataset_id}/values/{column_name}")
def zara_dataset_values(dataset_id: str, column_name: str) -> dict[str, list[Any]]:
    return _zara_read(
        lambda session: get_dataset_values(session, dataset_id, column_name)
    )


@app.post("/api/workflows/run")
def zara_run_workflow(request: WorkflowRunRequest) -> dict[str, Any]:
    return _zara_read(lambda session: run_workflow(session, request))


@app.post("/api/visualizations/query")
def zara_query_visualization(request: VisualizationQueryRequest) -> dict[str, Any]:
    return _zara_read(lambda session: query_visualization(session, request))


@app.post("/api/visualizations/recommend")
def zara_recommend_visualizations(
    request: VisualizationRecommendRequest,
) -> dict[str, list[dict[str, Any]]]:
    return _zara_read(lambda session: recommend_visualizations(session, request))


@app.post("/api/workflows")
def zara_save_workflow(
    workflow: WorkflowDefinition,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    saved = ZaraWorkflow(user_id=user_id, name=workflow.name, definition={})
    session.add(saved)
    session.flush()
    definition = workflow.model_dump(mode="json")
    definition["id"] = str(saved.id)
    saved.definition = definition
    session.commit()
    return definition


@app.put("/api/workflows/{workflow_id}")
def zara_update_workflow(
    workflow_id: UUID,
    workflow: WorkflowDefinition,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    if workflow.id is not None and workflow.id != workflow_id:
        raise HTTPException(status_code=400, detail="Workflow ID does not match the URL.")
    saved = session.get(ZaraWorkflow, workflow_id)
    if saved is None or saved.user_id != user_id:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    definition = workflow.model_dump(mode="json")
    definition["id"] = str(workflow_id)
    saved.name = workflow.name
    saved.definition = definition
    session.commit()
    return definition


@app.post("/api/conversations", response_model=ConversationSummaryResponse)
def create_conversation(
    request: ConversationCreate,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationSummaryResponse:
    conversation = ConversationRepository(session).create(
        user_id=user_id,
        workspace=request.workspace,
        project_scope=request.project_scope,
        first_question=request.first_question,
        title=request.title,
    )
    return ConversationSummaryResponse.model_validate(serialize_conversation(conversation))


@app.get("/api/conversations", response_model=ConversationListResponse)
def list_conversations(
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationListResponse:
    conversations = ConversationRepository(session).list_recent(user_id=user_id)
    return ConversationListResponse.model_validate(
        {"conversations": [serialize_conversation(item) for item in conversations]}
    )


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationDetailResponse:
    conversation = ConversationRepository(session).get(
        conversation_id, user_id=user_id, include_messages=True
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationDetailResponse.model_validate(
        serialize_conversation(conversation, include_messages=True)
    )


@app.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=ConversationMessageResponse,
)
def add_conversation_message(
    conversation_id: UUID,
    request: ConversationMessageCreate,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationMessageResponse:
    repository = ConversationRepository(session)
    conversation = repository.get(conversation_id, user_id=user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    message = repository.add_message(
        conversation,
        role=request.role,
        content=request.content,
        structured_content=request.structured_content,
    )
    return ConversationMessageResponse.model_validate(serialize_message(message))


@app.delete("/api/conversations/{conversation_id}")
def archive_conversation(
    conversation_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> dict[str, str]:
    repository = ConversationRepository(session)
    conversation = repository.get(conversation_id, user_id=user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    repository.archive(conversation)
    memory_store.reset(str(conversation_id))
    return {"status": "archived", "conversation_id": str(conversation_id)}


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database_connected = False
    database = f"postgresql:{settings.doradb_name}"
    status = "ok"
    detail: str | None = None

    if not settings.doradb_configured:
        status = "degraded"
        database = "DoraDB credentials required"
        detail = "Configure DORADB_USER and DORADB_PASSWORD to enable dataset analysis."
    else:
        try:
            with doradb_session() as real_session:
                check_doradb(real_session)
            database_connected = True
        except (DoraDbConfigurationError, SQLAlchemyError) as exc:
            logger.warning("DoraDB health check failed: %s", exc)
            status = "degraded"
            detail = "DoraDB is configured but not reachable."

    llm = GenerativeAIClient(settings)
    try:
        llm_status = llm.check_availability()
    finally:
        llm.close()
    if not llm_status.available:
        status = "degraded"
        if llm_status.detail:
            detail = f"{detail} {llm_status.detail}" if detail else llm_status.detail

    return HealthResponse(
        status=status,
        database=database,
        data_source="doradb",
        database_connected=database_connected,
        llm_provider=settings.llm_source,
        llm_model=settings.llm_model,
        llm_configured=llm_status.configured,
        llm_available=llm_status.available,
        tts_configured=bool(settings.elevenlabs_api_key),
        detail=detail,
    )


@app.get("/api/projects")
def projects() -> dict[str, list[dict[str, Any]]]:
    """Return the single configured real DoraDB project scope."""

    return {
        "projects": [
            {
                "key": settings.doradb_project_key,
                "name": f"{settings.doradb_project_key} · DoraDB",
                "issue_count": None,
            }
        ]
    }


@app.get("/api/jira-dashboard", response_model=JiraDashboardResponse)
def jira_dashboard(
    project_key: str | None = None,
    refresh: bool = False,
) -> JiraDashboardResponse:
    """Return bounded Jira snapshot aggregates; manual refresh bypasses cache."""

    active_project = (project_key or settings.doradb_project_key).strip().upper()
    try:
        with doradb_session() as real_session:
            payload = get_jira_dashboard(
                real_session,
                project_key=active_project,
                refresh=refresh,
            )
        logger.info(
            "jira_dashboard project=%s cached=%s",
            active_project,
            payload["cached"],
        )
        return JiraDashboardResponse.model_validate(payload)
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DoraDbQueryRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Jira dashboard query failed for project=%s", active_project)
        raise HTTPException(
            status_code=503,
            detail="The Jira dashboard data is temporarily unavailable.",
        ) from exc


def _check_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to.")


@app.get("/api/dashboard/metrics")
def dashboard_metrics() -> dict[str, Any]:
    return {
        "metrics": public_metric_registry(),
        "unsupported_metrics": UNSUPPORTED_METRICS,
        "attention_thresholds": ATTENTION_THRESHOLDS,
    }


@app.get("/api/dashboard/squads")
def dashboard_squads(project: str | None = None) -> dict[str, Any]:
    active_project = (project or settings.doradb_project_key).strip().upper()
    try:
        with doradb_session() as real_session:
            return get_dashboard_squads(real_session, project=active_project)
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Dashboard squad lookup failed project=%s", active_project)
        raise HTTPException(status_code=503, detail="Squad data is temporarily unavailable.") from exc


@app.get("/api/dashboard/filters")
def dashboard_filters(
    project: str | None = None,
    squad: str | None = Query(default=None, max_length=80),
) -> dict[str, Any]:
    active_project = (project or settings.doradb_project_key).strip().upper()
    try:
        with doradb_session() as real_session:
            return get_dashboard_filter_options(
                real_session, project=active_project, squad=squad
            )
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Dashboard filter lookup failed project=%s squad=%s", active_project, squad)
        raise HTTPException(status_code=503, detail="Dashboard filters are temporarily unavailable.") from exc


@app.get("/api/dashboard/portfolio")
def dashboard_portfolio(
    project: str | None = None,
    release: str | None = Query(default=None, max_length=120),
    sprint: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    _check_date_range(date_from, date_to)
    active_project = (project or settings.doradb_project_key).strip().upper()
    try:
        with doradb_session() as real_session:
            payload = get_portfolio_dashboard(
                real_session, project=active_project, release=release, sprint=sprint,
                date_from=date_from, date_to=date_to,
            )
        logger.info("dashboard_portfolio project=%s filters=%s", active_project, payload["applied_filters"])
        return payload
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Portfolio dashboard query failed project=%s", active_project)
        raise HTTPException(status_code=503, detail="Portfolio dashboard data is temporarily unavailable.") from exc


@app.get("/api/dashboard/squad/{squad_name}")
def dashboard_squad_detail(
    squad_name: str,
    project: str | None = None,
    release: str | None = Query(default=None, max_length=120),
    sprint: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    _check_date_range(date_from, date_to)
    active_project = (project or settings.doradb_project_key).strip().upper()
    try:
        with doradb_session() as real_session:
            payload = get_squad_dashboard(
                real_session, project=active_project, squad=squad_name,
                release=release, sprint=sprint, date_from=date_from, date_to=date_to,
            )
        logger.info("dashboard_squad project=%s squad=%s", active_project, payload["squad"])
        return payload
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnknownSquadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Squad dashboard query failed project=%s squad=%s", active_project, squad_name)
        raise HTTPException(status_code=503, detail="Squad dashboard data is temporarily unavailable.") from exc


@app.get("/api/dashboard/issues")
def dashboard_issues(
    squad: str = Query(min_length=1, max_length=80),
    project: str | None = None,
    release: str | None = Query(default=None, max_length=120),
    sprint: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    issue_type: str | None = Query(default=None, max_length=80),
    status: str | None = Query(default=None, max_length=80),
    priority: str | None = Query(default=None, max_length=80),
    assignee: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1, le=100_000),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="updated"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    _check_date_range(date_from, date_to)
    if sort_by not in ISSUE_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {', '.join(sorted(ISSUE_SORT_FIELDS))}.",
        )
    active_project = (project or settings.doradb_project_key).strip().upper()
    try:
        with doradb_session() as real_session:
            return get_dashboard_issues(
                real_session, project=active_project, squad=squad,
                release=release, sprint=sprint, date_from=date_from, date_to=date_to,
                issue_type=issue_type, status=status, priority=priority, assignee=assignee,
                page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order,
            )
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnknownSquadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Dashboard issue lookup failed project=%s squad=%s", active_project, squad)
        raise HTTPException(status_code=503, detail="Issue details are temporarily unavailable.") from exc


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user_id: str = Depends(development_session),
    runtime_session: Session = Depends(get_db),
) -> ChatResponse:
    """Run configured-LLM planning and real DoraDB tools when data is required."""

    repository = ConversationRepository(runtime_session)
    conversation = (
        repository.get(request.conversation_id, user_id=user_id, include_messages=True)
        if request.conversation_id
        else None
    )
    if request.conversation_id and conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    dashboard_context = (
        request.dashboard_context.model_dump(mode="json", exclude_none=True)
        if request.dashboard_context else {}
    )
    active_project = (
        dashboard_context.get("project")
        or request.project_key
        or settings.doradb_project_key
    )
    project_scope: dict[str, Any] = {
        "project_key": str(active_project).strip().upper()
    }
    if dashboard_context:
        project_scope["dashboard_context"] = dashboard_context
    if conversation is None:
        conversation = repository.create(
            user_id=user_id,
            workspace=request.workspace,
            project_scope=project_scope,
            first_question=request.message,
        )
        persisted_history: list[dict[str, str]] = []
    else:
        persisted_history = recent_history(conversation.messages)
    history = persisted_history or [item.model_dump() for item in request.history]
    repository.add_message(
        conversation,
        role="user",
        content=request.message,
        structured_content={"metadata": {"dashboard_context": dashboard_context}},
    )
    agent_context = persistent_context(conversation.state or {})
    agent_context["dashboard_context"] = dashboard_context
    if dashboard_context:
        last_context = dict(agent_context.get("last_context", {}))
        filters = dict(last_context.get("filters", {}))
        if dashboard_context.get("squad"):
            filters["dcpsquad"] = dashboard_context["squad"]
        if dashboard_context.get("release"):
            filters["fixversion"] = dashboard_context["release"]
        filters["project_key"] = project_scope["project_key"]
        last_context["filters"] = filters
        if dashboard_context.get("selected_metric"):
            last_context["metric"] = dashboard_context["selected_metric"]
        last_context["dashboard_context"] = dashboard_context
        agent_context["last_context"] = last_context
    try:
        if settings.doradb_configured:
            with doradb_session() as real_session:
                result = DoraDbAgent(real_session).chat(
                    request.message,
                    session_id=str(conversation.id),
                    history=history,
                    persistent_context=agent_context,
                    project_scope=project_scope,
                )
        else:
            # Safe conversation can still run through the configured LLM. Any plan that
            # requires dataset evidence is rejected before query execution.
            result = DoraDbAgent(None).chat(
                request.message,
                session_id=str(conversation.id),
                history=history,
                persistent_context=agent_context,
                project_scope=project_scope,
            )
        agent_persistence = result.pop("_persistence", {})
        result.setdefault("metadata", {})["conversation_id"] = str(conversation.id)
        result["metadata"]["workspace"] = request.workspace
        result["metadata"]["project_scope"] = project_scope
        result["metadata"]["dashboard_context"] = dashboard_context
        repository.add_message(
            conversation,
            role="assistant",
            content=result["answer"],
            structured_content={
                "chart": result.get("chart"),
                "table": result.get("table"),
                "warnings": result.get("warnings", []),
                "validation": result.get("validation", {}),
                "metadata": result.get("metadata", {}),
                "detected_intent": result.get("intent"),
                "source_type": result.get("metadata", {}).get("answer_source"),
                "query_identifiers": result.get("metadata", {}).get("query_ids", []),
                "row_counts": result.get("metadata", {}).get("row_counts", []),
                "knowledge_sections": result.get("metadata", {}).get("knowledge_sections", []),
            },
        )
        repository.update_state(
            conversation,
            update_persistent_state(
                conversation.state or {},
                workspace=request.workspace,
                project_scope=project_scope,
                question=request.message,
                answer=result["answer"],
                agent_persistence=agent_persistence,
                dashboard_context=dashboard_context,
            ),
        )
        return ChatResponse.model_validate(result)
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DoraDbQueryRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("DoraDB query failed")
        raise HTTPException(
            status_code=503,
            detail="The DoraDB database is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Agent workflow failed")
        raise HTTPException(
            status_code=500,
            detail="The AI assistant could not process that request.",
        ) from exc


@app.post("/api/reset-session")
def reset_session(request: SessionResetRequest) -> dict[str, Any]:
    removed = memory_store.reset(request.session_id)
    return {"status": "ok", "session_id": request.session_id, "memory_removed": removed}


@app.get("/api/metrics")
def metrics() -> dict[str, Any]:
    return {
        "project": settings.doradb_project_key,
        "metrics": [
            {"id": key, "definition": value}
            for key, value in METRIC_DEFINITIONS.items()
        ],
    }


@app.get("/api/query-catalogue")
def query_catalogue() -> dict[str, Any]:
    return {
        "queries": [
            {
                "id": query_id,
                "purpose": definition["purpose"],
                "allowed_filters": definition["allowed_filters"],
                "default_limit": definition["default_limit"],
            }
            for query_id, definition in QUERY_CATALOGUE.items()
        ],
        "control": public_policy(),
    }


@app.get("/api/audit/recent")
def recent_audit(limit: int = 25) -> dict[str, Any]:
    return {"records": audit_log.recent(limit), "memory": memory_store.stats()}


@app.post(
    "/api/tts",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"audio/mpeg": {}}},
        413: {"description": "Text exceeds the per-request voice limit"},
        429: {"description": "Monthly character allowance exhausted"},
        503: {"description": "ElevenLabs is not configured"},
    },
)
async def text_to_speech(
    request: TTSRequest,
    session: Session = Depends(get_db),
) -> StreamingResponse:
    if len(request.text) > settings.elevenlabs_max_chars_per_request:
        raise HTTPException(
            status_code=413,
            detail=(
                "Voice text is too long. "
                f"Maximum: {settings.elevenlabs_max_chars_per_request:,} characters."
            ),
        )
    try:
        audio = await create_audio_stream(request.text, session)
    except TTSNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TTSQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TTSProviderError as exc:
        logger.warning("ElevenLabs generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    headers = {
        "Cache-Control": "private, max-age=3600",
        "X-TTS-Characters-Used": str(audio.usage.used),
        "X-TTS-Characters-Remaining": str(audio.usage.remaining),
    }
    if audio.request_id:
        headers["X-ElevenLabs-Request-ID"] = audio.request_id
    return StreamingResponse(audio.chunks, media_type="audio/mpeg", headers=headers)
