"""Report Studio endpoints.

Reports are persistent, user-scoped objects. Every handler resolves the report
through ``ReportRepository``, which filters on the caller's session id, so a
report is never reachable by guessing its identifier. Deterministic work
(templates, ordering, scope comparison, export layout) lives in
``backend/services/``; only narrative rewriting calls the model.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database.db import Report, get_db
from ..database.doradb import DoraDbConfigurationError, doradb_session
from ..llm import GenerativeAIClient
from ..report_repository import ReportNotFound, ReportRepository
from ..schemas import (
    ReportComposeRequest,
    ReportComposeResponse,
    ReportCreateRequest,
    ReportDuplicateRequest,
    ReportExportRequest,
    ReportListResponse,
    ReportReorderRequest,
    ReportResponse,
    ReportSectionCreateRequest,
    ReportSectionUpdateRequest,
    ReportSourceRequest,
    ReportSummaryResponse,
    ReportTemplateResponse,
    ReportUpdateRequest,
)
from ..services.report_composition import compose_sections
from ..services.report_generation import run_template_questions
from ..services.report_evidence import (
    detect_scope_conflicts,
    evidence_timestamp,
    scope_from_message,
    snapshot_from_message,
    spread_hours,
    staleness,
)
from ..services.report_export import render_csv, render_docx, render_pdf, safe_filename
from ..services.report_templates import (
    AUDIENCES,
    CLASSIFICATIONS,
    CONTENT_MODES,
    DETAIL_LEVELS,
    SECTION_TYPES,
    SELECTIONS,
    STATUSES,
    TEMPLATE_IDS,
    TONES,
    questions_for_template,
    template_catalogue,
)
from .dependencies import development_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])

EXPORT_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv; charset=utf-8",
}


def _repository(session: Session) -> ReportRepository:
    return ReportRepository(session)


def _resolve(session: Session, report_id: UUID, user_id: str) -> Report:
    try:
        return _repository(session).get(report_id, user_id=user_id)
    except ReportNotFound:
        # Same response whether it does not exist or belongs to someone else.
        raise HTTPException(status_code=404, detail="Report not found.") from None


def _source_label(evidence: dict[str, Any], index: int) -> str:
    question = (evidence.get("question") or "").strip()
    return question[:80] if question else f"Source {index}"


def _serialize_source(source: Any, index: int) -> dict[str, Any]:
    evidence = source.evidence or {}
    return {
        "id": source.id,
        "conversation_id": source.conversation_id,
        "message_id": source.message_id,
        "selection": source.selection,
        "label": _source_label(evidence, index),
        "question": evidence.get("question") or "",
        "scope": source.scope or {},
        "query_ids": evidence.get("query_ids") or [],
        "row_counts": evidence.get("row_counts") or [],
        "warnings": evidence.get("warnings") or [],
        "has_chart": bool(evidence.get("chart")),
        "has_table": bool(evidence.get("table")),
        "data_as_of": source.data_as_of,
    }


def _conflict_payload(report: Report) -> list[dict[str, Any]]:
    sources = [
        {"id": str(source.id), "label": _source_label(source.evidence or {}, index), "scope": source.scope or {}}
        for index, source in enumerate(report.sources, start=1)
    ]
    return detect_scope_conflicts(sources)


def _freshness(report: Report) -> dict[str, Any]:
    info = staleness(report.data_as_of)
    stamps = [source.data_as_of for source in report.sources if source.data_as_of]
    info["source_spread_hours"] = spread_hours(stamps)
    if info["source_spread_hours"] >= 24:
        info["reason"] = (
            f"{info['reason']} Sources were retrieved up to "
            f"{info['source_spread_hours']} hours apart."
        )
    return info


def _serialize(report: Report) -> dict[str, Any]:
    return {
        "id": report.id,
        "title": report.title,
        "template": report.template,
        "status": report.status,
        "audience": report.audience,
        "tone": report.tone,
        "detail_level": report.detail_level,
        "include_recommendations": report.include_recommendations,
        "scope": report.scope or {},
        "validation": report.validation or {},
        "version": report.version,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
        "data_as_of": report.data_as_of,
        "last_validated_at": report.last_validated_at,
        "last_exported_at": report.last_exported_at,
        "freshness": _freshness(report),
        "conflicts": _conflict_payload(report),
        "sections": [
            {
                "id": section.id,
                "type": section.type,
                "title": section.title,
                "content": section.content,
                "payload": section.payload,
                "position": section.position,
                "visible": section.visible,
                "content_mode": section.content_mode,
                "content_classification": section.content_classification,
                "manually_edited": section.manually_edited,
                "needs_review": section.needs_review,
                "source_ids": [str(sid) for sid in (section.source_ids or [])],
            }
            for section in sorted(report.sections, key=lambda s: s.position)
        ],
        "sources": [
            _serialize_source(source, index) for index, source in enumerate(report.sources, start=1)
        ],
    }


def _summary(report: Report) -> dict[str, Any]:
    return {
        "id": report.id,
        "title": report.title,
        "template": report.template,
        "status": report.status,
        "scope": report.scope or {},
        "version": report.version,
        "updated_at": report.updated_at,
        "data_as_of": report.data_as_of,
        "last_exported_at": report.last_exported_at,
        "section_count": len(report.sections),
        "source_count": len(report.sources),
        "freshness": _freshness(report),
    }


# --------------------------------------------------------------------------- #
# Catalogue                                                                   #
# --------------------------------------------------------------------------- #


@router.get("/templates", response_model=ReportTemplateResponse)
def list_templates() -> ReportTemplateResponse:
    return ReportTemplateResponse(
        templates=template_catalogue(),
        audiences=list(AUDIENCES),
        tones=list(TONES),
        detail_levels=list(DETAIL_LEVELS),
        section_types=list(SECTION_TYPES),
        content_modes=list(CONTENT_MODES),
        selections=list(SELECTIONS),
    )


# --------------------------------------------------------------------------- #
# Reports                                                                     #
# --------------------------------------------------------------------------- #


@router.post("", response_model=ReportResponse, status_code=201)
def create_report(
    request: ReportCreateRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    if request.template not in TEMPLATE_IDS:
        raise HTTPException(status_code=422, detail=f"Unknown report template: {request.template}")
    if request.audience not in AUDIENCES:
        raise HTTPException(status_code=422, detail=f"Unknown audience: {request.audience}")
    if request.tone not in TONES:
        raise HTTPException(status_code=422, detail=f"Unknown tone: {request.tone}")
    if request.detail_level not in DETAIL_LEVELS:
        raise HTTPException(status_code=422, detail=f"Unknown detail level: {request.detail_level}")
    report = _repository(session).create(
        user_id=user_id,
        template=request.template,
        title=request.title,
        audience=request.audience,
        tone=request.tone,
        detail_level=request.detail_level,
        include_recommendations=request.include_recommendations,
        scope=request.scope.model_dump(mode="json", exclude_none=True) if request.scope else {},
    )
    return ReportResponse.model_validate(_serialize(report))


@router.get("", response_model=ReportListResponse)
def list_reports(
    include_archived: bool = False,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportListResponse:
    reports = _repository(session).list(user_id=user_id, include_archived=include_archived)
    return ReportListResponse(
        reports=[ReportSummaryResponse.model_validate(_summary(report)) for report in reports]
    )


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    return ReportResponse.model_validate(_serialize(_resolve(session, report_id, user_id)))


@router.patch("/{report_id}", response_model=ReportResponse)
def update_report(
    report_id: UUID,
    request: ReportUpdateRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    report = _resolve(session, report_id, user_id)
    if request.status is not None and request.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown report status: {request.status}")
    if request.audience is not None and request.audience not in AUDIENCES:
        raise HTTPException(status_code=422, detail=f"Unknown audience: {request.audience}")
    if request.tone is not None and request.tone not in TONES:
        raise HTTPException(status_code=422, detail=f"Unknown tone: {request.tone}")
    fields = request.model_dump(exclude_none=True)
    if request.scope is not None:
        fields["scope"] = request.scope.model_dump(mode="json", exclude_none=True)
    _repository(session).update(report, **fields)
    return ReportResponse.model_validate(_serialize(report))


@router.delete("/{report_id}", status_code=204)
def archive_report(
    report_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> Response:
    _repository(session).archive(_resolve(session, report_id, user_id))
    return Response(status_code=204)


@router.post("/{report_id}/duplicate", response_model=ReportResponse, status_code=201)
def duplicate_report(
    report_id: UUID,
    request: ReportDuplicateRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    report = _resolve(session, report_id, user_id)
    copy = _repository(session).duplicate(report, title=request.title)
    return ReportResponse.model_validate(_serialize(copy))


# --------------------------------------------------------------------------- #
# Sections                                                                    #
# --------------------------------------------------------------------------- #


@router.post("/{report_id}/sections", response_model=ReportResponse, status_code=201)
def add_section(
    report_id: UUID,
    request: ReportSectionCreateRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    report = _resolve(session, report_id, user_id)
    if request.type not in SECTION_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown section type: {request.type}")
    _repository(session).add_section(
        report,
        type=request.type,
        title=request.title,
        content=request.content,
        payload=request.payload,
        position=request.position,
    )
    return ReportResponse.model_validate(_serialize(report))


@router.patch("/{report_id}/sections/{section_id}", response_model=ReportResponse)
def update_section(
    report_id: UUID,
    section_id: UUID,
    request: ReportSectionUpdateRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    report = _resolve(session, report_id, user_id)
    if (
        request.content_classification is not None
        and request.content_classification not in CLASSIFICATIONS
    ):
        raise HTTPException(
            status_code=422, detail=f"Unknown classification: {request.content_classification}"
        )
    if request.content_mode is not None and request.content_mode not in CONTENT_MODES:
        raise HTTPException(status_code=422, detail=f"Unknown content mode: {request.content_mode}")
    try:
        _repository(session).update_section(
            report, section_id, **request.model_dump(exclude_none=True)
        )
    except ReportNotFound:
        raise HTTPException(status_code=404, detail="Report section not found.") from None
    return ReportResponse.model_validate(_serialize(report))


@router.delete("/{report_id}/sections/{section_id}", response_model=ReportResponse)
def delete_section(
    report_id: UUID,
    section_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    report = _resolve(session, report_id, user_id)
    try:
        _repository(session).remove_section(report, section_id)
    except ReportNotFound:
        raise HTTPException(status_code=404, detail="Report section not found.") from None
    return ReportResponse.model_validate(_serialize(report))


@router.post("/{report_id}/sections/reorder", response_model=ReportResponse)
def reorder_sections(
    report_id: UUID,
    request: ReportReorderRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    report = _resolve(session, report_id, user_id)
    try:
        _repository(session).reorder_sections(report, request.section_ids)
    except ReportNotFound:
        raise HTTPException(
            status_code=422, detail="One of the sections does not belong to this report."
        ) from None
    return ReportResponse.model_validate(_serialize(report))


# --------------------------------------------------------------------------- #
# Sources                                                                     #
# --------------------------------------------------------------------------- #


@router.post("/{report_id}/sources", response_model=ReportResponse, status_code=201)
def add_source(
    report_id: UUID,
    request: ReportSourceRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    """Attach one assistant answer as evidence.

    The conversation is re-resolved against the caller's own id, so a message
    belonging to another user can never be pulled into a report even if its
    identifiers are known.
    """

    from ..conversation_repository import ConversationRepository

    report = _resolve(session, report_id, user_id)
    if request.selection not in SELECTIONS:
        raise HTTPException(status_code=422, detail=f"Unknown selection: {request.selection}")
    if request.content_mode not in CONTENT_MODES:
        raise HTTPException(status_code=422, detail=f"Unknown content mode: {request.content_mode}")

    conversation = ConversationRepository(session).get(
        request.conversation_id, user_id=user_id, include_messages=True
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    message = next((m for m in conversation.messages if m.id == request.message_id), None)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found in that conversation.")
    if message.role != "assistant":
        raise HTTPException(
            status_code=422,
            detail="Only an assistant answer can be used as report evidence.",
        )

    ordered = sorted(conversation.messages, key=lambda m: m.created_at)
    question = ""
    for index, item in enumerate(ordered):
        if item.id == message.id:
            for earlier in reversed(ordered[:index]):
                if earlier.role == "user":
                    question = earlier.content
                    break
            break

    evidence = snapshot_from_message(
        question=question,
        answer=message.content,
        structured_content=message.structured_content,
        selection=request.selection,
    )
    scope = scope_from_message(message.structured_content)
    source = _repository(session).add_source(
        report,
        conversation_id=conversation.id,
        message_id=message.id,
        selection=request.selection,
        evidence=evidence,
        scope=scope,
        data_as_of=evidence_timestamp(message.structured_content) or message.created_at,
    )

    # Chart and table selections become their own structured blocks so exports
    # can lay them out, rather than being flattened into prose.
    repository = _repository(session)
    if request.selection in {"full", "chart"} and evidence.get("chart"):
        repository.place_visual(
            report,
            type="chart",
            title=(evidence["chart"] or {}).get("title") or "Chart",
            payload=evidence["chart"],
            source_ids=[str(source.id)],
        )
    if request.selection in {"full", "table"} and evidence.get("table"):
        repository.place_visual(
            report,
            type="data_table",
            title=(evidence["table"] or {}).get("title") or "Supporting data",
            payload=evidence["table"],
            source_ids=[str(source.id)],
        )
    if request.selection in {"full", "narrative", "recommendations", "warnings"}:
        # The block is always seeded with the answer, whatever the mode. Leaving
        # it empty until composition ran meant a user who added an answer landed
        # on a blank section and had to press another button before the report
        # said anything -- the data they asked for should already be there, with
        # rewriting as a refinement rather than a prerequisite.
        content = evidence.get("answer") or ""
        if request.selection == "warnings":
            warnings = evidence.get("warnings") or []
            content = "\n".join(warnings) or "No data-quality warnings were recorded."
        repository.add_section(
            report,
            type="key_finding" if request.selection != "warnings" else "data_quality",
            title=_source_label(evidence, len(report.sources)),
            content=content or "",
            content_classification="observed_fact",
            content_mode=request.content_mode,
            source_ids=[str(source.id)],
        )

    session.refresh(report)
    return ReportResponse.model_validate(_serialize(report))


@router.delete("/{report_id}/sources/{source_id}", response_model=ReportResponse)
def remove_source(
    report_id: UUID,
    source_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    report = _resolve(session, report_id, user_id)
    try:
        _repository(session).remove_source(report, source_id)
    except ReportNotFound:
        raise HTTPException(status_code=404, detail="Report source not found.") from None
    return ReportResponse.model_validate(_serialize(report))


# --------------------------------------------------------------------------- #
# Compose / validate / export                                                 #
# --------------------------------------------------------------------------- #


@router.post("/{report_id}/compose", response_model=ReportComposeResponse)
def compose_report(
    report_id: UUID,
    request: ReportComposeRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportComposeResponse:
    report = _resolve(session, report_id, user_id)
    repository = _repository(session)
    wanted = {str(sid) for sid in request.section_ids}
    sections = [
        {
            "id": str(section.id),
            "type": section.type,
            "title": section.title,
            "content_mode": section.content_mode,
            "content_classification": section.content_classification,
            "manually_edited": section.manually_edited,
            "visible": section.visible,
        }
        for section in sorted(report.sections, key=lambda s: s.position)
        if not wanted or str(section.id) in wanted
    ]
    sources = [
        {"id": str(source.id), "label": _source_label(source.evidence or {}, index),
         "evidence": source.evidence or {}, "scope": source.scope or {}}
        for index, source in enumerate(report.sources, start=1)
    ]

    try:
        result = compose_sections(
            llm=GenerativeAIClient(settings),
            sections=sections,
            sources=sources,
            audience=report.audience,
            tone=report.tone,
            detail_level=report.detail_level,
        )
    except Exception:  # noqa: BLE001 - never surface provider internals
        logger.exception("Report composition failed for report %s", report_id)
        raise HTTPException(
            status_code=502,
            detail="The report could not be composed because the AI provider failed. "
            "Your report and its evidence are unchanged.",
        ) from None

    updated: list[UUID] = []
    for section_id, content in result["sections"].items():
        section = repository.get_section(report, UUID(section_id))
        section.content = content
        # Composition is not a manual edit, so the section stays
        # evidence-backed rather than being flagged for review.
        section.manually_edited = False
        updated.append(section.id)
    report.validation = {
        "state": "composed" if updated else "unchanged",
        "warnings": result["warnings"],
        "conflicts": result["conflicts"],
    }
    report.last_validated_at = datetime.now(timezone.utc)
    if updated:
        report.version += 1
    session.commit()
    session.refresh(report)

    return ReportComposeResponse(
        report=ReportResponse.model_validate(_serialize(report)),
        updated_sections=updated,
        warnings=result["warnings"],
        conflicts=result["conflicts"],
    )



@router.post("/{report_id}/generate", response_model=ReportComposeResponse)
def generate_report(
    report_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportComposeResponse:
    """Fill a template by answering its standard questions from live data.

    This is what makes a template useful on its own: the questions are fixed,
    so running the same report next week asks the same things and reports
    whatever the data says then. Answers come from the existing governed agent,
    so each one arrives with its approved query ids, row counts, warnings and
    validation attached -- the report is evidence-backed, not model prose.
    """

    from ..doradb_agent import DoraDbAgent

    report = _resolve(session, report_id, user_id)
    questions = questions_for_template(report.template)
    if not questions:
        raise HTTPException(
            status_code=422,
            detail="This template has no standard questions. Add answers from a "
            "conversation instead, or write the sections yourself.",
        )
    if not settings.doradb_configured:
        raise HTTPException(
            status_code=503,
            detail="The database is not configured, so a report cannot be generated from live data.",
        )

    repository = _repository(session)
    try:
        with doradb_session() as doradb:
            answers = run_template_questions(
                agent_factory=lambda: DoraDbAgent(doradb),
                questions=questions,
                scope=report.scope or {},
                session_id=f"report-{report.id}",
            )
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:  # noqa: BLE001 - never surface provider or driver internals
        logger.exception("Report generation failed for report %s", report_id)
        raise HTTPException(
            status_code=502,
            detail="The report could not be generated. Your report is unchanged.",
        ) from None

    warnings = [f"{item['question']}: {item['error']}" for item in answers if item.get("error")]
    produced = [item for item in answers if not item.get("error")]
    if not produced:
        raise HTTPException(
            status_code=502,
            detail="None of the template questions could be answered from the current data.",
        )

    for item in produced:
        evidence = snapshot_from_message(
            question=item["question"],
            answer=item["answer"],
            structured_content=item["structured_content"],
            selection="full",
        )
        source = repository.add_source(
            report,
            conversation_id=None,
            message_id=None,
            selection="full",
            evidence=evidence,
            scope=scope_from_message(item["structured_content"]),
            data_as_of=evidence_timestamp(item["structured_content"]) or datetime.now(timezone.utc),
        )
        # Charts and tables become their own blocks so exports lay them out.
        # Placed next to the analysis they illustrate, not appended in a block
        # of unexplained diagrams at the end.
        if evidence.get("chart"):
            repository.place_visual(
                report, type="chart",
                title=(evidence["chart"] or {}).get("title") or "Chart",
                payload=evidence["chart"], source_ids=[str(source.id)],
            )
        if evidence.get("table"):
            repository.place_visual(
                report, type="data_table",
                title=(evidence["table"] or {}).get("title") or "Supporting data",
                payload=evidence["table"], source_ids=[str(source.id)],
            )

    session.refresh(report)
    composed = compose_report(report_id, ReportComposeRequest(), user_id=user_id, session=session)
    if warnings:
        composed.warnings = [*warnings, *composed.warnings]
    return composed


@router.post("/{report_id}/validate", response_model=ReportResponse)
def validate_report(
    report_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ReportResponse:
    """Deterministic readiness check. No model call."""

    report = _resolve(session, report_id, user_id)
    conflicts = _conflict_payload(report)
    freshness = _freshness(report)
    issues: list[str] = [conflict["message"] for conflict in conflicts]

    visible = [section for section in report.sections if section.visible]
    empty = [
        section.title or section.type
        for section in visible
        if section.type in {"executive_summary", "key_finding", "rich_text"}
        and not (section.content or "").strip()
    ]
    if empty:
        issues.append("These sections have no content yet: " + ", ".join(empty) + ".")
    if any(section.needs_review for section in visible):
        issues.append(
            "One or more sections were edited by hand after validation and are no "
            "longer evidence-verified."
        )
    if not report.sources:
        issues.append("No evidence sources are attached, so nothing in this report is verifiable.")
    if freshness.get("stale"):
        issues.append(freshness.get("reason", "The evidence may be out of date."))

    report.validation = {
        "state": "passed" if not issues else "attention",
        "issues": issues,
        "conflicts": conflicts,
        "checked_sections": len(visible),
    }
    report.last_validated_at = datetime.now(timezone.utc)
    if issues and report.status == "ready":
        report.status = "needs_review"
    elif not issues and report.status == "draft":
        report.status = "ready"
    if freshness.get("stale") and report.status not in {"needs_review"}:
        report.status = "stale"
    session.commit()
    session.refresh(report)
    return ReportResponse.model_validate(_serialize(report))


@router.post("/{report_id}/export")
def export_report(
    report_id: UUID,
    request: ReportExportRequest,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> Response:
    """Stream the export back directly.

    Nothing is written to a served directory, so there is no public URL to
    guess and no file left readable after the request.
    """

    report = _resolve(session, report_id, user_id)
    payload = _serialize(report)
    payload["sources"] = [
        {"evidence": source.evidence or {}} for source in report.sources
    ]

    try:
        if request.format == "csv":
            if request.section_id is None:
                raise HTTPException(
                    status_code=422, detail="Choose a table or chart section to export as CSV."
                )
            try:
                section = _repository(session).get_section(report, request.section_id)
            except ReportNotFound:
                raise HTTPException(status_code=404, detail="Report section not found.") from None
            if section.type not in {"data_table", "chart", "kpi_group"}:
                raise HTTPException(
                    status_code=422,
                    detail="Only a table, chart or KPI section can be exported as CSV.",
                )
            body: bytes = render_csv(section.payload or {}).encode("utf-8-sig")
            filename = safe_filename(f"{report.title}-{section.title or section.type}", "csv")
        elif request.format == "docx":
            body = render_docx(payload)
            filename = safe_filename(report.title, "docx")
        else:
            body = render_pdf(payload)
            filename = safe_filename(report.title, "pdf")
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - never leak renderer internals
        logger.exception("Report export failed for report %s", report_id)
        raise HTTPException(
            status_code=500,
            detail="The report could not be exported. Your report is unchanged.",
        ) from None

    report.last_exported_at = datetime.now(timezone.utc)
    if report.status in {"draft", "ready"}:
        report.status = "exported"
    session.commit()

    return Response(
        content=body,
        media_type=EXPORT_MEDIA_TYPES[request.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
