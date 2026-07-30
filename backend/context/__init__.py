"""Versioned steering context for the governed DoraDB agent."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CONTEXT_DIR = Path(__file__).resolve().parent


@lru_cache
def load_context(name: str) -> dict[str, Any]:
    """Load JSON-compatible YAML without adding a runtime YAML dependency."""

    safe_name = Path(name).name
    path = CONTEXT_DIR / safe_name
    if path.suffix != ".yaml" or not path.is_file():
        raise ValueError(f"Unknown context file: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["load_context"]
