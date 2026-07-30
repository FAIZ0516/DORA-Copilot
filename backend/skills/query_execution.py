"""Bounded adapter around the static, parameterized DoraDB query tools."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..doradb import query_doradb


def execute_approved_query(
    session: Session,
    *,
    query_id: str,
    filters: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    return query_doradb(
        session,
        query_id=query_id,
        filters=filters,
        limit=limit,
    )
