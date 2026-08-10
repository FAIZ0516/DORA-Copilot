"""Output guardrail: keeps restricted fields out of anything the user sees.

Two layers (guide Section 17.3):

- ``strip_sensitive_fields`` -- structural stripping of restricted keys
  (``summary``, ``reporter``, ``assignee``, ``root_cause``, ``how_to_fix``,
  ``labels``) from any dict/list before it is cached or persisted. This was
  previously private to ``memory/result_cache.py``; it is the single
  authoritative implementation now, reused wherever row-shaped data is
  stored.
- ``check_output_safety`` -- a code-level check on the *final free-text
  answer* the model generated, flagging if a restricted field name leaked
  into prose. ``INSTRUCTIONS.md`` already tells the model never to reveal
  these fields (G4/V7), but a sentence in a prompt is not equivalent to a
  code-level check (guide Section 17, "Important principle") -- until this
  module existed, nothing actually re-checked the generated text.
"""

from __future__ import annotations

import re
from typing import Any

RESTRICTED_FIELDS = frozenset(
    {"summary", "reporter", "assignee", "root_cause", "how_to_fix", "labels"}
)

_RESTRICTED_MENTION = re.compile(
    r"\b(?:" + "|".join(re.escape(field) for field in RESTRICTED_FIELDS) + r")\s*[:=]",
    re.I,
)


def strip_sensitive_fields(value: Any) -> Any:
    """Recursively remove restricted keys from a dict/list structure."""

    if isinstance(value, dict):
        return {
            key: strip_sensitive_fields(item)
            for key, item in value.items()
            if key not in RESTRICTED_FIELDS
        }
    if isinstance(value, list):
        return [strip_sensitive_fields(item) for item in value]
    if isinstance(value, str):
        return value[:500]
    return value


def check_output_safety(answer: str) -> list[str]:
    """Flag likely restricted-field leakage in the final answer text.

    A plain mention of the word "summary" in normal prose is fine; this only
    flags the ``field_name:`` / ``field_name=`` shape that indicates a raw
    row value was echoed, which INSTRUCTIONS.md explicitly prohibits (G4).
    """

    return [
        f"Possible restricted field leak in the answer: {match.group(0)!r}"
        for match in _RESTRICTED_MENTION.finditer(answer)
    ]


__all__ = ["RESTRICTED_FIELDS", "check_output_safety", "strip_sensitive_fields"]
