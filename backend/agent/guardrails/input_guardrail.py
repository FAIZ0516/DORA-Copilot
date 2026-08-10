"""Input guardrail: a pre-planning safety check on the raw user message.

Blocks unsafe/write/destructive requests before any planning or tool
selection happens (guide Section 17.1). This deliberately does not
re-implement unsafe-pattern detection: ``services.intent_matching`` already
has the one authoritative classifier (including the out-of-scope/unsafe
regex), so this module only turns that classification into an explicit,
traceable guardrail verdict -- previously that verdict existed only as a
side effect of planning, with no separate checkpoint to log or test.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...services.intent_matching import classify_intent


@dataclass(frozen=True)
class InputGuardrailResult:
    allowed: bool
    reason: str


def check_input(message: str) -> InputGuardrailResult:
    """Return a verdict for the raw message, before any planning occurs."""

    intent = classify_intent(message)
    if intent["name"] == "out_of_scope":
        return InputGuardrailResult(
            allowed=False,
            reason="Message matched an unsafe/write/destructive request pattern.",
        )
    return InputGuardrailResult(allowed=True, reason="")


__all__ = ["InputGuardrailResult", "check_input"]
