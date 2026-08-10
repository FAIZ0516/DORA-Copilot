"""Shared FastAPI dependencies for the API layer."""

from __future__ import annotations

import re

from fastapi import Header, HTTPException


def development_session(
    value: str = Header(default="local-development", alias="X-Development-Session"),
) -> str:
    """Temporary browser identity for development; replace with authenticated user IDs."""

    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,120}", cleaned):
        raise HTTPException(status_code=400, detail="Invalid development session identifier.")
    return cleaned


__all__ = ["development_session"]
