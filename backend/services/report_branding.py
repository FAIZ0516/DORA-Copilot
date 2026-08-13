"""Stamp the exported PDF onto the corporate page template.

The template is a real one-page A4 PDF supplied by the business (RHB report
page: masthead, header rule, faded watermark, footer rule and diamond). It is
merged underneath every generated page rather than being redrawn in code, so
the logo, watermark and spacing stay pixel-exact and a new template version is
a file swap, not a code change.

Content is laid out inside the template's frame -- see the margin constants
below -- so nothing collides with the masthead or the footer rule.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from reportlab.lib.units import mm

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "report_page_template.pdf"

# Measured from the template so body text sits inside its frame:
# the masthead rule sits ~88pt from the top and the footer rule ~60pt from the
# bottom, and the rules span roughly 65pt..536pt across an A4 page.
TEMPLATE_MARGIN_LEFT = 22 * mm
TEMPLATE_MARGIN_RIGHT = 22 * mm
TEMPLATE_MARGIN_TOP = 38 * mm
TEMPLATE_MARGIN_BOTTOM = 28 * mm

# The template's own page number is static ("1" on every page, because it was a
# Word field). Measured from the template itself, the diamond and numeral sit
# at x 514-530, baseline y 27.5. The box below covers that, and the real number
# is drawn on the same baseline so the footer keeps the template's alignment.
FOOTER_NUMBER_BASELINE = 27.5
FOOTER_COVER_WIDTH = 44.0
FOOTER_COVER_BOTTOM = 20.0
FOOTER_COVER_HEIGHT = 16.0


def template_available() -> bool:
    return TEMPLATE_PATH.is_file()


def apply_template(pdf_bytes: bytes) -> bytes:
    """Merge every page of a generated PDF onto the corporate template.

    Returns the original bytes unchanged if the template is missing or cannot
    be read: an unbranded report is worth delivering, a failed export is not.
    """

    if not template_available():
        return pdf_bytes

    try:
        from pypdf import PdfReader, PdfWriter

        content = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        for page in content.pages:
            # Re-read per page: merging mutates the base, so every page needs
            # its own clean copy of the template. The base is attached to the
            # writer before merging -- pypdf deprecated merging detached pages
            # and warns that it is unreliable.
            base = writer.add_page(PdfReader(str(TEMPLATE_PATH)).pages[0])
            base.merge_page(page)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
    except Exception:  # noqa: BLE001 - branding must never break an export
        logger.exception("Could not apply the report page template; exporting unbranded.")
        return pdf_bytes


__all__ = [
    "FOOTER_COVER_BOTTOM",
    "FOOTER_COVER_HEIGHT",
    "FOOTER_COVER_WIDTH",
    "FOOTER_NUMBER_BASELINE",
    "TEMPLATE_MARGIN_BOTTOM",
    "TEMPLATE_MARGIN_LEFT",
    "TEMPLATE_MARGIN_RIGHT",
    "TEMPLATE_MARGIN_TOP",
    "TEMPLATE_PATH",
    "apply_template",
    "template_available",
]
