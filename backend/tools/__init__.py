"""Tools: narrow, typed capabilities the agent is permitted to call.

There is exactly one tool in this application: executing an approved,
parameterized DoraDB query by ID. It validates nothing itself -- it is a
thin adapter that delegates to the database layer (``backend/database/``),
which does the real allowlisting/validation. Business/domain logic (metric
selection, comparisons, trends, chart specs, entity grounding, filter
extraction, intent classification) lives in ``backend/services/`` instead,
since those are reused by multiple callers and don't call the database
themselves.
"""

from .query_execution import execute_approved_query

__all__ = ["execute_approved_query"]
