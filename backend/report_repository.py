"""Persistence for reports, sections and evidence sources.

Mirrors ``conversation_repository`` deliberately: the API layer never touches
the ORM directly, and **every** lookup is filtered by ``user_id`` so a report
cannot be reached by guessing its identifier.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database.db import Report, ReportSection, ReportSource
from .services.report_templates import (
    SECTION_TYPES,
    STATUSES,
    default_title,
    sections_for_template,
)


def _as_utc(value: datetime | None) -> datetime | None:
    """Treat a stored naive timestamp as UTC so comparisons are well-defined."""

    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class ReportNotFound(LookupError):
    """The report does not exist, or does not belong to this user.

    Deliberately one error for both cases: telling an unauthorised caller that
    a report exists but is not theirs is itself a disclosure.
    """


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Reports                                                            #
    # ------------------------------------------------------------------ #

    def create(
        self,
        *,
        user_id: str,
        template: str = "blank",
        title: str | None = None,
        audience: str = "delivery_manager",
        tone: str = "professional",
        detail_level: str = "standard",
        include_recommendations: bool = True,
        scope: dict[str, Any] | None = None,
    ) -> Report:
        report = Report(
            user_id=user_id,
            title=(title or default_title(template))[:200],
            template=template,
            status="draft",
            audience=audience,
            tone=tone,
            detail_level=detail_level,
            include_recommendations=include_recommendations,
            scope=scope or {},
            validation={},
        )
        self.session.add(report)
        self.session.flush()
        for section in sections_for_template(template):
            self.session.add(ReportSection(report_id=report.id, **section))
        self.session.commit()
        self.session.refresh(report)
        return report

    def get(self, report_id: UUID, *, user_id: str) -> Report:
        report = self.session.scalar(
            select(Report).where(Report.id == report_id, Report.user_id == user_id)
        )
        if report is None:
            raise ReportNotFound(str(report_id))
        return report

    def list(self, *, user_id: str, include_archived: bool = False, limit: int = 50) -> list[Report]:
        statement = select(Report).where(Report.user_id == user_id)
        if not include_archived:
            statement = statement.where(Report.archived_at.is_(None))
        statement = statement.order_by(Report.updated_at.desc()).limit(limit)
        return list(self.session.scalars(statement))

    def update(self, report: Report, **fields: Any) -> Report:
        for key, value in fields.items():
            if value is not None and hasattr(report, key):
                setattr(report, key, value)
        self.session.commit()
        self.session.refresh(report)
        return report

    def apply_template(self, report: Report, *, template: str) -> Report:
        """Replace the report layout with a selected fixed template.

        Applying a template is an explicit editor action. Existing generated
        evidence is removed so a subsequent refresh cannot mix two template
        runs; independently attached chat evidence remains available as
        supporting provenance.
        """

        generated_source_ids = {
            str(source.id)
            for source in report.sources
            if (source.evidence or {}).get("generated_by") == "report_template"
        }
        for section in list(report.sections):
            self.session.delete(section)
        for source in list(report.sources):
            if str(source.id) in generated_source_ids:
                self.session.delete(source)

        report.template = template
        report.status = "draft"
        report.validation = {}
        report.last_validated_at = None
        report.data_as_of = min(
            (
                _as_utc(source.data_as_of)
                for source in report.sources
                if str(source.id) not in generated_source_ids and source.data_as_of
            ),
            default=None,
        )
        report.version += 1
        self.session.flush()
        for section in sections_for_template(template):
            self.session.add(ReportSection(report_id=report.id, **section))
        self.session.commit()
        self.session.refresh(report)
        return report

    def set_status(self, report: Report, status: str) -> Report:
        if status not in STATUSES:
            raise ValueError(f"Unknown report status: {status}")
        report.status = status
        self.session.commit()
        return report

    def archive(self, report: Report) -> None:
        report.archived_at = datetime.now(timezone.utc)
        self.session.commit()

    def duplicate(self, report: Report, *, title: str | None = None) -> Report:
        """Copy a report with its sections and evidence snapshots.

        The copy keeps the original snapshots, so "duplicate last week's report,
        refresh it, compare" starts from a known-good baseline rather than an
        empty shell.
        """

        copy = Report(
            user_id=report.user_id,
            title=(title or f"{report.title} (copy)")[:200],
            template=report.template,
            status="draft",
            audience=report.audience,
            tone=report.tone,
            detail_level=report.detail_level,
            include_recommendations=report.include_recommendations,
            scope=dict(report.scope or {}),
            validation={},
            data_as_of=report.data_as_of,
        )
        self.session.add(copy)
        self.session.flush()

        source_map: dict[str, str] = {}
        for source in report.sources:
            new_source = ReportSource(
                report_id=copy.id,
                conversation_id=source.conversation_id,
                message_id=source.message_id,
                selection=source.selection,
                evidence=dict(source.evidence or {}),
                scope=dict(source.scope or {}),
                data_as_of=source.data_as_of,
            )
            self.session.add(new_source)
            self.session.flush()
            source_map[str(source.id)] = str(new_source.id)

        for section in report.sections:
            self.session.add(
                ReportSection(
                    report_id=copy.id,
                    type=section.type,
                    title=section.title,
                    content=section.content,
                    payload=dict(section.payload) if isinstance(section.payload, dict) else section.payload,
                    position=section.position,
                    visible=section.visible,
                    content_mode=section.content_mode,
                    content_classification=section.content_classification,
                    manually_edited=section.manually_edited,
                    needs_review=section.needs_review,
                    # Re-point at the copied snapshots, not the original's.
                    source_ids=[
                        source_map[str(sid)] for sid in (section.source_ids or []) if str(sid) in source_map
                    ],
                )
            )
        self.session.commit()
        self.session.refresh(copy)
        return copy

    # ------------------------------------------------------------------ #
    # Sections                                                           #
    # ------------------------------------------------------------------ #

    def add_section(
        self,
        report: Report,
        *,
        type: str,
        title: str = "",
        content: str = "",
        payload: dict[str, Any] | None = None,
        position: int | None = None,
        content_classification: str = "user_authored",
        content_mode: str = "original",
        source_ids: list[str] | None = None,
    ) -> ReportSection:
        if type not in SECTION_TYPES:
            raise ValueError(f"Unknown section type: {type}")
        end = max((s.position for s in report.sections), default=0) + 1
        target = end if position is None else max(1, min(position, end))
        if position is not None:
            for existing in report.sections:
                if existing.position >= target:
                    existing.position += 1
        section = ReportSection(
            report_id=report.id,
            type=type,
            title=title[:200],
            content=content,
            payload=payload,
            position=target,
            content_classification=content_classification,
            content_mode=content_mode,
            source_ids=source_ids or [],
        )
        self.session.add(section)
        report.version += 1
        self.session.commit()
        self.session.refresh(report)
        return section

    # Blocks that close a report. A chart belongs with the analysis it
    # illustrates, so it is placed before these rather than after them.
    TRAILING_TYPES = frozenset(
        {"data_quality", "scope_limitation", "methodology", "page_break"}
    )

    def place_visual(
        self,
        report: Report,
        *,
        type: str,
        title: str,
        payload: dict[str, Any],
        source_ids: list[str],
        after: int | None = None,
    ) -> ReportSection:
        """Put a chart or table where it explains something.

        Appending every visual to the end left a report of prose followed by a
        block of unexplained diagrams. Preference order:

        1. Fill an empty placeholder the template already reserved for this kind
           of block -- that is where the template author wanted it.
        2. Otherwise sit directly after the narrative section it belongs to.
        3. Otherwise land before the closing data-quality and methodology
           blocks, never after them.
        """

        placeholder = next(
            (
                section
                for section in sorted(report.sections, key=lambda s: s.position)
                if section.type == type and not section.payload
            ),
            None,
        )
        if placeholder is not None:
            placeholder.payload = payload
            if title:
                placeholder.title = title
            placeholder.source_ids = list({*(placeholder.source_ids or []), *source_ids})
            self.session.commit()
            self.session.refresh(report)
            return placeholder

        if after is None:
            trailing = [
                section.position
                for section in report.sections
                if section.type in self.TRAILING_TYPES
            ]
            after = (min(trailing) - 1) if trailing else None

        return self.add_section(
            report,
            type=type,
            title=title,
            payload=payload,
            position=(after + 1) if after is not None else None,
            content_classification="observed_fact",
            content_mode="rewrite",
            source_ids=source_ids,
        )

    def get_section(self, report: Report, section_id: UUID) -> ReportSection:
        for section in report.sections:
            if section.id == section_id:
                return section
        raise ReportNotFound(str(section_id))

    def update_section(self, report: Report, section_id: UUID, **fields: Any) -> ReportSection:
        section = self.get_section(report, section_id)
        edits_content = "content" in fields and fields["content"] is not None
        for key, value in fields.items():
            if value is not None and hasattr(section, key):
                setattr(section, key, value)
        if edits_content and not fields.get("manually_edited") is False:
            section.manually_edited = True
            # Hand-edited evidence-backed narrative requires review: wording
            # changes can alter the meaning even when no number was touched.
            if section.source_ids:
                section.needs_review = True
                report.status = "needs_review"
        report.version += 1
        self.session.commit()
        self.session.refresh(section)
        return section

    def remove_section(self, report: Report, section_id: UUID) -> None:
        section = self.get_section(report, section_id)
        self.session.delete(section)
        self.session.flush()
        self.session.refresh(report)
        self._renumber(report)
        report.version += 1
        self.session.commit()

    def reorder_sections(self, report: Report, ordered_ids: list[UUID]) -> Report:
        """Apply an explicit order; any section left out keeps its relative place."""

        known = {section.id: section for section in report.sections}
        unknown = [sid for sid in ordered_ids if sid not in known]
        if unknown:
            raise ReportNotFound(str(unknown[0]))
        position = 1
        for section_id in ordered_ids:
            known[section_id].position = position
            position += 1
        for section in sorted(report.sections, key=lambda s: s.position):
            if section.id not in set(ordered_ids):
                section.position = position
                position += 1
        report.version += 1
        self.session.commit()
        self.session.refresh(report)
        return report

    def _renumber(self, report: Report) -> None:
        for index, section in enumerate(sorted(report.sections, key=lambda s: s.position), start=1):
            section.position = index

    # ------------------------------------------------------------------ #
    # Sources                                                            #
    # ------------------------------------------------------------------ #

    def add_source(
        self,
        report: Report,
        *,
        conversation_id: UUID | None,
        message_id: UUID | None,
        selection: str,
        evidence: dict[str, Any],
        scope: dict[str, Any],
        data_as_of: datetime | None,
    ) -> ReportSource:
        source = ReportSource(
            report_id=report.id,
            conversation_id=conversation_id,
            message_id=message_id,
            selection=selection,
            evidence=evidence,
            scope=scope,
            data_as_of=data_as_of,
        )
        self.session.add(source)
        self.session.flush()
        # A report is only as fresh as its oldest evidence.
        #
        # Timestamps are normalised to aware UTC before comparison: SQLite
        # returns naive datetimes even for a timezone-aware column, so a stored
        # value and a freshly supplied one are otherwise not comparable.
        stamps = [
            _as_utc(s.data_as_of) for s in report.sources if s.data_as_of
        ] + ([_as_utc(data_as_of)] if data_as_of else [])
        if stamps:
            report.data_as_of = min(stamps)
        self.session.commit()
        self.session.refresh(report)
        return source

    def remove_source(self, report: Report, source_id: UUID) -> None:
        for source in report.sources:
            if source.id == source_id:
                self.session.delete(source)
                for section in report.sections:
                    section.source_ids = [
                        sid for sid in (section.source_ids or []) if str(sid) != str(source_id)
                    ]
                self.session.commit()
                self.session.refresh(report)
                return
        raise ReportNotFound(str(source_id))

    def replace_generated_content(self, report: Report) -> None:
        """Remove the previous template run while preserving user/chat evidence."""

        generated = {
            str(source.id)
            for source in report.sources
            if (source.evidence or {}).get("generated_by") == "report_template"
        }
        if not generated:
            return
        template_visual_counts: dict[str, int] = {}
        for item in sections_for_template(report.template):
            if item["type"] in {"chart", "data_table"}:
                template_visual_counts[item["type"]] = template_visual_counts.get(item["type"], 0) + 1
        kept_visuals: dict[str, int] = {}
        for section in sorted(list(report.sections), key=lambda item: item.position):
            linked = {str(value) for value in (section.source_ids or [])}
            generated_links = linked & generated
            if not generated_links:
                continue
            remaining = linked - generated
            if section.type in {"chart", "data_table"} and not remaining:
                # Keep template placeholders, remove extra visuals created by
                # the prior run. A placeholder has always existed since v1.
                kept = kept_visuals.get(section.type, 0)
                if kept < template_visual_counts.get(section.type, 0):
                    section.payload = None
                    section.source_ids = []
                    kept_visuals[section.type] = kept + 1
                else:
                    self.session.delete(section)
                continue
            section.source_ids = sorted(remaining)
            if not section.manually_edited:
                section.content = ""
                if section.type == "feature_status":
                    section.payload = None
            section.needs_review = bool(section.manually_edited and remaining)
        for source in list(report.sources):
            if str(source.id) in generated:
                self.session.delete(source)
        report.data_as_of = min(
            (_as_utc(source.data_as_of) for source in report.sources
             if str(source.id) not in generated and source.data_as_of),
            default=None,
        )
        self.session.flush()
        self._renumber(report)
        self.session.commit()
        self.session.refresh(report)


__all__ = ["ReportNotFound", "ReportRepository"]
