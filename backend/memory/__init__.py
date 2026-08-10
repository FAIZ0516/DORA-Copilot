"""Conversation state / memory: bounded, structured, and privacy-safe.

``memory.py`` is process-local, volatile, per-session short-term memory
(deliberately excludes raw database result sets). ``result_cache.py`` is the
per-conversation, TTL-bounded reuse policy for validated query results (what
makes a follow-up like "make it a table" answerable without a new query).
Both deliberately never become a substitute for the source database -- see
AGENTS.md Section 4.
"""

from .memory import memory_store

__all__ = ["memory_store"]
