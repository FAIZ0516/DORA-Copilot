"""The exported PDF carries the corporate page template."""

from __future__ import annotations

import io

import pytest
from reportlab.lib.pagesizes import A4

from backend.services.report_branding import (
    FOOTER_COVER_BOTTOM,
    FOOTER_COVER_HEIGHT,
    FOOTER_COVER_WIDTH,
    FOOTER_NUMBER_BASELINE,
    TEMPLATE_MARGIN_BOTTOM,
    TEMPLATE_MARGIN_LEFT,
    TEMPLATE_MARGIN_RIGHT,
    TEMPLATE_MARGIN_TOP,
    apply_template,
    template_available,
)
from backend.services.report_export import render_pdf

# Position of the template's own static page number, measured from the file.
TEMPLATE_NUMBER_X = (514.2, 530.0)
TEMPLATE_NUMBER_Y = 27.5

REPORT = {
    "title": "Sprint Performance Report",
    "version": 2,
    "scope": {"project": "DCPM", "squad": "MBK"},
    "validation": {"state": "passed"},
    "sources": [{"evidence": {"query_ids": ["jira_dashboard_kpis"]}}],
    "sections": [
        {
            "type": "executive_summary", "title": "Summary", "position": 1, "visible": True,
            "content": "MBK completed 812 of 1,876 tickets.",
            "content_classification": "interpretation",
        },
        {"type": "page_break", "title": "", "position": 2, "visible": True},
        {
            "type": "key_finding", "title": "Analysis", "position": 3, "visible": True,
            "content": "Release cadence slowed.", "content_classification": "interpretation",
        },
    ],
}


def test_the_template_ships_with_the_backend() -> None:
    assert template_available(), "the corporate page template is missing from backend/assets"


def test_every_exported_page_carries_the_branding() -> None:
    pdf = render_pdf(REPORT)
    reader = pytest.importorskip("pypdf").PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 2, "needed a multi-page report to test repetition"
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        # The masthead comes from the template, so its presence proves the merge.
        assert "R E P O R T" in text, f"page {index} is unbranded"
        # The logo and watermark are images on the template page.
        assert len(page.images) >= 1, f"page {index} lost the template artwork"


def test_pages_are_numbered_individually_not_all_page_one() -> None:
    pdf = render_pdf(REPORT)
    reader = pytest.importorskip("pypdf").PdfReader(io.BytesIO(pdf))
    for index, page in enumerate(reader.pages, start=1):
        assert f"Page {index}" in (page.extract_text() or "")


def test_the_static_template_number_is_covered_by_the_real_one() -> None:
    """The template's "1" is a fixed Word field; it must not repeat."""

    left = A4[0] - TEMPLATE_MARGIN_RIGHT - FOOTER_COVER_WIDTH
    right = A4[0] - TEMPLATE_MARGIN_RIGHT
    assert left <= TEMPLATE_NUMBER_X[0] and right >= TEMPLATE_NUMBER_X[1]
    assert FOOTER_COVER_BOTTOM <= TEMPLATE_NUMBER_Y <= FOOTER_COVER_BOTTOM + FOOTER_COVER_HEIGHT
    # The real number sits on the template's own baseline, keeping its alignment.
    assert FOOTER_COVER_BOTTOM <= FOOTER_NUMBER_BASELINE <= FOOTER_COVER_BOTTOM + FOOTER_COVER_HEIGHT


def test_content_is_laid_out_inside_the_template_frame() -> None:
    # Body text must clear the masthead above and the footer rule below.
    assert TEMPLATE_MARGIN_TOP > 88, "content would run under the masthead rule"
    assert TEMPLATE_MARGIN_BOTTOM > 60, "content would cross the footer rule"
    assert TEMPLATE_MARGIN_LEFT >= 60, "content would sit left of the template rule"
    usable = A4[0] - TEMPLATE_MARGIN_LEFT - TEMPLATE_MARGIN_RIGHT
    assert usable > 300, "the frame is too narrow to hold a table"


def test_the_page_size_is_unchanged_by_stamping() -> None:
    pdf = render_pdf(REPORT)
    reader = pytest.importorskip("pypdf").PdfReader(io.BytesIO(pdf))
    for page in reader.pages:
        assert round(float(page.mediabox.width)) == round(A4[0])
        assert round(float(page.mediabox.height)) == round(A4[1])


def test_a_broken_template_never_breaks_the_export() -> None:
    # An unbranded report is worth delivering; a failed export is not.
    assert apply_template(b"not a pdf at all") == b"not a pdf at all"
