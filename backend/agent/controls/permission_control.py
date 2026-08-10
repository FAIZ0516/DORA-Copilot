"""Permission control: the static allowlist of what may be queried at all.

This is a coarse-grained, stateless "is this capability permitted to exist"
check -- independent of any specific proposed call's shape. It answers:

- Is this query ID one of the approved tools?
- Is this filter key permitted for that query at all?
- What is the maximum row count this query is ever permitted to return?

Whether a *specific* proposed call also satisfies per-query completeness
requirements (e.g. ``dora_metrics_by_squad`` needs a ``dcpsquad`` value) is a
guardrail decision -- see ``backend/agent/guardrails/tool_guardrail.py``,
which calls into this module for the allowlist itself.
"""

from __future__ import annotations

from ...config import settings
from ...database.doradb_catalog import APPROVED_QUERY_IDS, LARGE_QUERY_IDS, QUERY_CATALOGUE


def query_id_is_permitted(query_id: str) -> bool:
    return query_id in APPROVED_QUERY_IDS


def filter_is_permitted(query_id: str, filter_key: str) -> bool:
    if query_id not in QUERY_CATALOGUE:
        return False
    return filter_key in QUERY_CATALOGUE[query_id]["allowed_filters"]


def permitted_result_limit(query_id: str) -> int:
    """The hard ceiling this query may ever return, regardless of request."""

    return 200 if query_id in LARGE_QUERY_IDS else settings.result_limit


__all__ = ["filter_is_permitted", "permitted_result_limit", "query_id_is_permitted"]
