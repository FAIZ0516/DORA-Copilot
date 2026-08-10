"""Privacy-safe in-memory audit trail for prototype observability."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from ..config import settings


class AuditLog:
    def __init__(self) -> None:
        self._records: deque[dict[str, Any]] = deque(
            maxlen=settings.agent_audit_max_records
        )
        self._lock = RLock()

    def add(self, record: dict[str, Any]) -> None:
        safe = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": record.get("request_id"),
            "session_id": str(record.get("session_id", ""))[:64],
            "intent": record.get("intent"),
            "query_ids": record.get("query_ids", []),
            "row_counts": record.get("row_counts", []),
            "planner": record.get("planner"),
            "validation_status": record.get("validation_status"),
            "repairs": record.get("repairs", 0),
            "answer_regenerations": record.get("answer_regenerations", 0),
            "duration_ms": record.get("duration_ms"),
            "evidence_sources": record.get("evidence_sources", []),
            "knowledge_sections": record.get("knowledge_sections", []),
        }
        with self._lock:
            self._records.append(safe)

    def recent(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(list(self._records)[-max(1, min(limit, 100)) :])


audit_log = AuditLog()
