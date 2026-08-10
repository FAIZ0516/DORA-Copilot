"""Loads the runtime instruction content sent to the model on each turn.

Nothing here is cached: ``INSTRUCTIONS.md`` and every ``SKILL.md`` are
re-read on every call so edits take effect on the very next chat request.
See AGENTS.md Section 5 for why this must never be confused with the root
``AGENTS.md`` (IDE/development guidance), which is never read here.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .skill_registry import SKILLS_DIR, load_skill_playbooks, skill_catalogue

logger = logging.getLogger(__name__)

RUNTIME_INSTRUCTIONS_PATH = Path(__file__).resolve().parent / "INSTRUCTIONS.md"
# Re-exported for backward compatibility; skill_registry.SKILLS_DIR is the
# single source of truth for this path.
RUNTIME_SKILLS_DIR = SKILLS_DIR


def strip_markdown_fence(text: str) -> str:
    return re.sub(
        r"\A```(?:markdown|md)?\s*\n?(.*?)\n?```\s*\Z",
        r"\1",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()


def load_response_protocol_phrase() -> str:
    """Extract the response phrase from the runtime instructions at request time.

    Reads the RESPONSE PROTOCOL section, extracts ONLY the phrase inside the
    ``` code block (e.g. "YES ,IM ZARA."), and returns it. Reading on every
    call means edits to INSTRUCTIONS.md take effect immediately.
    """
    try:
        full = RUNTIME_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Runtime instructions not found at %s.", RUNTIME_INSTRUCTIONS_PATH)
        return ""

    m = re.search(
        r"##\s*⚠️\s*RESPONSE\s+PROTOCOL.*?\n(?=\n*(?:---|##\s))",
        full,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        logger.warning("RESPONSE PROTOCOL section not found in runtime instructions.")
        return ""

    section = m.group(0)
    phrase_match = re.search(r"```\s*\n(.+?)\n```", section, re.DOTALL)
    if not phrase_match:
        logger.warning("No code block found in RESPONSE PROTOCOL section.")
        return ""

    phrase = phrase_match.group(1).strip()
    logger.info("Loaded runtime response phrase: %s", phrase)
    return phrase


def load_system_instructions(message: str = "") -> str:
    """Load the runtime instructions, the skill catalogue, and any matched skill.

    Returns the runtime instruction content, a compact name+description
    catalogue of every available skill (so the model always knows what
    exists), and -- when ``message`` deterministically matches one or more
    skills (see :mod:`skill_registry`) -- the full body of those skill(s),
    so the model actually receives the matched playbook's query IDs,
    interpretation rules, response template, and common mistakes, not only
    its one-line description.
    """
    try:
        core = RUNTIME_INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Runtime instructions not found at %s.", RUNTIME_INSTRUCTIONS_PATH)
        core = ""

    return core + skill_catalogue() + (load_skill_playbooks(message) if message else "")


__all__ = [
    "RUNTIME_INSTRUCTIONS_PATH",
    "RUNTIME_SKILLS_DIR",
    "load_response_protocol_phrase",
    "load_system_instructions",
    "strip_markdown_fence",
]
