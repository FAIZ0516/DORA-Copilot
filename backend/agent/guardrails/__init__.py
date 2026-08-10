"""Guardrails: checking, blocking, rejecting, or constraining unsafe/invalid
behavior. Kept conceptually separate from response style (``controls/``).

- ``input_guardrail.py`` -- pre-planning check on the raw message.
- ``tool_guardrail.py`` -- validates/blocks a proposed tool call before
  execution (the former ``control.py::enforce_plan``).
- ``output_guardrail.py`` -- restricted-field stripping + a code-level check
  on the generated answer text.
"""

from .input_guardrail import InputGuardrailResult, check_input
from .output_guardrail import RESTRICTED_FIELDS, check_output_safety, strip_sensitive_fields
from .tool_guardrail import ToolGuardrailViolation, enforce_plan

__all__ = [
    "InputGuardrailResult",
    "RESTRICTED_FIELDS",
    "ToolGuardrailViolation",
    "check_input",
    "check_output_safety",
    "enforce_plan",
    "strip_sensitive_fields",
]
