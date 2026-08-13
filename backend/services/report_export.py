"""Render a report to PDF, DOCX or CSV.

PDF is produced server-side with ReportLab rather than browser print, so the
output is identical regardless of who exports it and page furniture (numbers,
version, repeated table headers) is under our control. ReportLab is a pure
Python wheel -- WeasyPrint would drag GTK/Cairo system libraries in, which is a
poor trade on the Windows dev environment this project targets.

Layout is deterministic here. Nothing in this module calls a model.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from .report_charts import describe, draw_chart, truncation_note
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# Brand palette, aligned with the app's chart tokens so an exported report and
# the on-screen dashboard read as one product.
INK = colors.HexColor("#1f2d3d")
MUTED = colors.HexColor("#5b6b80")
ACCENT = colors.HexColor("#4f46e5")
RULE = colors.HexColor("#dbe3ee")
SURFACE = colors.HexColor("#f6f8fc")
RISK = colors.HexColor("#b4532a")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm

# Labels shown against a block so a reader can tell measurement from advice.
CLASSIFICATION_LABEL = {
    "observed_fact": "Observed fact",
    "interpretation": "Interpretation",
    "recommendation": "Recommendation",
    "user_authored": "Author's note",
}


def safe_filename(title: str, extension: str) -> str:
    """A predictable, filesystem-safe download name."""

    cleaned = re.sub(r"[^\w\s-]", "", title or "report").strip()
    cleaned = re.sub(r"[\s_]+", "-", cleaned).strip("-").lower() or "report"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{cleaned[:60]}-{stamp}.{extension}"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=27, leading=32, textColor=INK, spaceAfter=6,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=16, textColor=MUTED,
        ),
        "heading": ParagraphStyle(
            "heading", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, leading=17, textColor=INK, spaceBefore=14, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5,
            leading=14.5, textColor=INK, alignment=TA_LEFT, spaceAfter=6,
        ),
        "label": ParagraphStyle(
            "label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.5,
            leading=9, textColor=MUTED, spaceAfter=3,
        ),
        "note": ParagraphStyle(
            "note", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=8,
            leading=12, textColor=MUTED, spaceAfter=4,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"], fontName="Helvetica", fontSize=7.6, leading=10,
            textColor=INK,
        ),
        "chart_caption": ParagraphStyle(
            "chart_caption", parent=base["Normal"], fontName="Helvetica", fontSize=8.2,
            leading=12.5, textColor=MUTED, spaceBefore=4, spaceAfter=6,
        ),
        "cell_head": ParagraphStyle(
            "cell_head", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.6,
            leading=10, textColor=colors.white,
        ),
    }


def _escape(text: Any) -> str:
    """Escape for ReportLab's mini-HTML so user text cannot break layout."""

    return (
        str(text if text is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _scope_line(scope: dict[str, Any]) -> str:
    parts = [
        f"Project {scope.get('project')}" if scope.get("project") else None,
        f"Squad {scope.get('squad')}" if scope.get("squad") else "All squads",
        f"Sprint {scope.get('sprint')}" if scope.get("sprint") else None,
        f"Release {scope.get('release')}" if scope.get("release") else None,
    ]
    period = None
    if scope.get("date_from") or scope.get("date_to"):
        period = f"{scope.get('date_from') or 'start'} to {scope.get('date_to') or 'today'}"
    parts.append(f"Period {period}" if period else "All available dates")
    return " · ".join(part for part in parts if part)


def _fmt_time(value: Any) -> str:
    if not value:
        return "Not recorded"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y %H:%M UTC")
    return str(value)


class _ReportDoc(BaseDocTemplate):
    """Adds the running footer: page numbers, version and scope."""

    def __init__(self, buffer: io.BytesIO, *, report: dict[str, Any]) -> None:
        super().__init__(
            buffer, pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN + 8 * mm,
            title=report.get("title") or "Report", author="DORA Copilot",
        )
        self._report = report
        frame = Frame(MARGIN, MARGIN + 8 * mm, PAGE_WIDTH - 2 * MARGIN,
                      PAGE_HEIGHT - 2 * MARGIN - 8 * mm, id="body")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[frame]),
            PageTemplate(id="body", frames=[frame], onPage=self._footer),
        ])

    def _footer(self, canvas, doc) -> None:  # noqa: ANN001 - ReportLab signature
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, MARGIN + 6 * mm, PAGE_WIDTH - MARGIN, MARGIN + 6 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        left = f"{self._report.get('title') or 'Report'} · v{self._report.get('version', 1)}"
        canvas.drawString(MARGIN, MARGIN + 2 * mm, left[:110])
        canvas.drawRightString(PAGE_WIDTH - MARGIN, MARGIN + 2 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()


def _kpi_table(payload: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table | None:
    items = [item for item in (payload.get("items") or []) if isinstance(item, dict)]
    if not items:
        return None
    cells = [
        [
            Paragraph(_escape(item.get("label", "")), styles["label"]),
            Paragraph(f"<b>{_escape(item.get('value', ''))}</b>", styles["body"]),
        ]
        for item in items[:8]
    ]
    # Two KPIs per row keeps values large enough to scan.
    rows = [sum(cells[i : i + 2], []) for i in range(0, len(cells), 2)]
    width = (PAGE_WIDTH - 2 * MARGIN) / 4
    table = Table(rows, colWidths=[width] * 4, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _data_table(payload: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    columns = payload.get("columns") or []
    rows = payload.get("rows") or []
    if not columns or not rows:
        return [Paragraph("No rows were available for this table.", styles["note"])]
    keys = [column.get("key") for column in columns if isinstance(column, dict)]
    headers = [
        Paragraph(_escape(column.get("label") or column.get("key")), styles["cell_head"])
        for column in columns
        if isinstance(column, dict)
    ]
    # Cap rows so one table cannot produce a hundred-page appendix.
    limit = 60
    body = [
        [Paragraph(_escape(row.get(key)), styles["cell"]) for key in keys]
        for row in rows[:limit]
    ]
    width = (PAGE_WIDTH - 2 * MARGIN) / max(len(keys), 1)
    # repeatRows=1 reprints the header on every page the table spills onto.
    table = Table([headers, *body], colWidths=[width] * len(keys), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE]),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow: list[Any] = [table]
    if len(rows) > limit:
        flow.append(Paragraph(
            f"Showing the first {limit} of {len(rows)} rows. Export the table as CSV "
            f"for the complete set.", styles["note"],
        ))
    return flow


def _chart_block(payload: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    """A real vector chart, with a factual reading of it underneath.

    Charts used to export as a table of values. Accurate, but a management
    report is read at a glance, so the numbers are now drawn. Vector output
    stays sharp in print and needs no headless browser on the server. The
    caption states only what the data already says, so it cannot drift from
    the plot beside it.
    """

    flow: list[Any] = []
    drawing = draw_chart(payload, PAGE_WIDTH - 2 * MARGIN)
    if drawing is None:
        return [Paragraph("No chart data was available for this section.", styles["note"])]

    flow.append(drawing)
    note = truncation_note(payload)
    if note:
        flow.append(Paragraph(_escape(note), styles["note"]))
    reading = describe(payload)
    if reading:
        flow.append(Paragraph(_escape(reading), styles["chart_caption"]))
    return flow


def _cover(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    scope = report.get("scope") or {}
    rows = [
        ("Project", scope.get("project") or "All projects"),
        ("Squad", scope.get("squad") or "All squads"),
        ("Reporting period", _scope_line(scope).split("Period ")[-1] if "Period" in _scope_line(scope) else "All available dates"),
        ("Generated", _fmt_time(datetime.now(timezone.utc))),
        ("Data as of", _fmt_time(report.get("data_as_of"))),
        ("Report version", f"v{report.get('version', 1)}"),
    ]
    meta = Table(
        [[Paragraph(_escape(k), styles["label"]), Paragraph(_escape(v), styles["cover_meta"])] for k, v in rows],
        colWidths=[38 * mm, PAGE_WIDTH - 2 * MARGIN - 38 * mm], hAlign="LEFT",
    )
    meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]))
    return [
        Spacer(1, 34 * mm),
        Paragraph("DORA COPILOT · ZARA", styles["label"]),
        Paragraph(_escape(report.get("title") or "Report"), styles["cover_title"]),
        Paragraph(_escape(_scope_line(scope)), styles["cover_meta"]),
        Spacer(1, 16 * mm),
        meta,
        NextPageTemplate("body"),
        PageBreak(),
    ]


def _methodology(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    sources = report.get("sources") or []
    query_ids: list[str] = []
    for source in sources:
        query_ids.extend((source.get("evidence") or {}).get("query_ids") or [])
    rows = [
        ("Scope", _scope_line(report.get("scope") or {})),
        ("Evidence sources", str(len(sources))),
        ("Approved queries used", ", ".join(sorted(set(query_ids))) or "None recorded"),
        ("Data retrieved", _fmt_time(report.get("data_as_of"))),
        ("Last validated", _fmt_time(report.get("last_validated_at"))),
        ("Validation state", str((report.get("validation") or {}).get("state", "not run"))),
        ("Report version", f"v{report.get('version', 1)}"),
    ]
    table = Table(
        [[Paragraph(_escape(k), styles["label"]), Paragraph(_escape(v), styles["cell"])] for k, v in rows],
        colWidths=[42 * mm, PAGE_WIDTH - 2 * MARGIN - 42 * mm], hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]))
    return [table]


def render_pdf(report: dict[str, Any]) -> bytes:
    """Render the whole report. Returns PDF bytes; never writes to disk."""

    styles = _styles()
    buffer = io.BytesIO()
    doc = _ReportDoc(buffer, report=report)
    flow: list[Any] = _cover(report, styles)

    for section in sorted(report.get("sections") or [], key=lambda s: s.get("position", 0)):
        if not section.get("visible", True):
            continue
        type_ = section.get("type")
        if type_ == "cover":
            continue
        if type_ == "page_break":
            flow.append(PageBreak())
            continue

        block: list[Any] = []
        if section.get("title"):
            block.append(Paragraph(_escape(section["title"]), styles["heading"]))

        classification = section.get("content_classification", "observed_fact")
        # Recommendations and interpretations are labelled so a reader never
        # mistakes advice for measurement.
        if classification in {"recommendation", "interpretation", "user_authored"}:
            block.append(Paragraph(CLASSIFICATION_LABEL[classification].upper(), styles["label"]))
        if section.get("needs_review"):
            block.append(Paragraph(
                "Manually edited after validation — figures in this section have not been "
                "re-verified against the source evidence.", styles["note"],
            ))

        payload = section.get("payload") or {}
        if type_ == "kpi_group":
            table = _kpi_table(payload, styles)
            if table is not None:
                block.append(table)
        elif type_ == "data_table":
            block.extend(_data_table(payload, styles))
        elif type_ == "chart":
            block.extend(_chart_block(payload, styles))
        elif type_ == "methodology":
            block.extend(_methodology(report, styles))

        content = (section.get("content") or "").strip()
        if content:
            for paragraph in [p for p in content.split("\n") if p.strip()]:
                block.append(Paragraph(_escape(paragraph), styles["body"]))
        elif type_ in {"executive_summary", "rich_text", "key_finding"} and not payload:
            block.append(Paragraph("This section has not been written yet.", styles["note"]))

        block.append(Spacer(1, 3 * mm))
        # Keep a heading with at least the start of its content.
        flow.append(KeepTogether(block[:2]) if len(block) > 2 else KeepTogether(block))
        flow.extend(block[2:] if len(block) > 2 else [])

    doc.build(flow)
    return buffer.getvalue()


def render_docx(report: dict[str, Any]) -> bytes:
    """Editable Word version, mirroring the PDF's structure."""

    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.core_properties.title = report.get("title") or "Report"
    document.add_heading(report.get("title") or "Report", level=0)
    document.add_paragraph(_scope_line(report.get("scope") or {}))
    meta = document.add_paragraph()
    meta.add_run(
        f"Generated {_fmt_time(datetime.now(timezone.utc))} · "
        f"Data as of {_fmt_time(report.get('data_as_of'))} · "
        f"Version v{report.get('version', 1)}"
    ).font.size = Pt(8)

    for section in sorted(report.get("sections") or [], key=lambda s: s.get("position", 0)):
        if not section.get("visible", True) or section.get("type") == "cover":
            continue
        if section.get("type") == "page_break":
            document.add_page_break()
            continue
        if section.get("title"):
            document.add_heading(section["title"], level=1)
        classification = section.get("content_classification", "observed_fact")
        if classification in {"recommendation", "interpretation", "user_authored"}:
            run = document.add_paragraph().add_run(CLASSIFICATION_LABEL[classification].upper())
            run.bold = True
            run.font.size = Pt(7)

        payload = section.get("payload") or {}
        if section.get("type") == "kpi_group":
            items = [i for i in (payload.get("items") or []) if isinstance(i, dict)]
            if items:
                table = document.add_table(rows=1, cols=2)
                table.style = "Light Grid Accent 1"
                table.rows[0].cells[0].text = "Measure"
                table.rows[0].cells[1].text = "Value"
                for item in items:
                    cells = table.add_row().cells
                    cells[0].text = str(item.get("label", ""))
                    cells[1].text = str(item.get("value", ""))
        elif section.get("type") in {"data_table", "chart"}:
            columns, rows = _tabular(payload)
            if columns:
                table = document.add_table(rows=1, cols=len(columns))
                table.style = "Light Grid Accent 1"
                for index, name in enumerate(columns):
                    table.rows[0].cells[index].text = str(name)
                for row in rows[:60]:
                    cells = table.add_row().cells
                    for index, value in enumerate(row):
                        cells[index].text = "" if value is None else str(value)

        for paragraph in [p for p in (section.get("content") or "").split("\n") if p.strip()]:
            document.add_paragraph(paragraph)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _tabular(payload: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    """Flatten a table or chart payload into header + rows for CSV/DOCX."""

    if payload.get("columns"):
        columns = [c for c in payload["columns"] if isinstance(c, dict)]
        keys = [c.get("key") for c in columns]
        headers = [c.get("label") or c.get("key") for c in columns]
        return headers, [[row.get(key) for key in keys] for row in payload.get("rows") or []]
    series = [s for s in (payload.get("series") or []) if isinstance(s, dict)]
    if series:
        x_key = payload.get("x_key") or "label"
        headers = [payload.get("x_label") or x_key] + [s.get("label") for s in series]
        rows = [
            [row.get(x_key)] + [row.get(s.get("key")) for s in series]
            for row in payload.get("data") or []
        ]
        return headers, rows
    return [], []


def render_csv(payload: dict[str, Any]) -> str:
    """One table block as CSV. Full rows, no display cap."""

    headers, rows = _tabular(payload or {})
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    if headers:
        writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return buffer.getvalue()


__all__ = ["CLASSIFICATION_LABEL", "render_csv", "render_docx", "render_pdf", "safe_filename"]
