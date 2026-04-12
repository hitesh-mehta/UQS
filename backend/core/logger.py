"""
Structured audit trail logger for UQS.
Every query, LLM call, cache hit/miss, and SQL execution is logged.
Logs are written to both stdout (structured JSON) and an audit table in Supabase.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel

# ── Event Types ───────────────────────────────────────────────────────────────

class AuditEvent(str, Enum):
    QUERY_RECEIVED = "query.received"
    QUERY_CLASSIFIED = "query.classified"
    CACHE_HIT = "cache.hit"
    CACHE_MISS = "cache.miss"
    SQL_GENERATED = "sql.generated"
    SQL_EXECUTED = "sql.executed"
    SQL_CORRECTED = "sql.corrected"
    SQL_BLOCKED = "sql.blocked"           # Blocked dangerous SQL
    LLM_CALL = "llm.call"
    LLM_RESPONSE = "llm.response"
    ENGINE_ROUTED = "engine.routed"
    ENGINE_RESPONSE = "engine.response"
    RAG_INGESTION = "rag.ingestion"
    RAG_RETRIEVAL = "rag.retrieval"
    MODEL_TRAINED = "model.trained"
    MODEL_PROMOTED = "model.promoted"
    MODEL_ROLLBACK = "model.rollback"
    CACHE_GENERATED = "cache.generated"
    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    ERROR = "error"


# ── Log Entry Model ───────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    log_id: str
    timestamp: str
    event: AuditEvent
    user_id: Optional[str] = None
    role: Optional[str] = None
    session_id: Optional[str] = None
    details: dict[str, Any] = {}
    latency_ms: Optional[float] = None
    success: bool = True


# ── Logger Setup ──────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON for log aggregators."""
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if hasattr(record, "audit_entry"):
            log_data["audit"] = record.audit_entry
        return json.dumps(log_data)


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("uqs")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    return logger


_logger = _setup_logger()


# ── Audit Logger Class ────────────────────────────────────────────────────────

class AuditLogger:
    """
    Central audit logger. Use this throughout the codebase.

    Usage:
        audit = AuditLogger(user_id="u123", role="analyst", session_id="s456")
        audit.log(AuditEvent.QUERY_RECEIVED, details={"query": "..."})
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.user_id = user_id
        self.role = role
        self.session_id = session_id

    def log(
        self,
        event: AuditEvent,
        details: dict[str, Any] | None = None,
        latency_ms: float | None = None,
        success: bool = True,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            log_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            event=event,
            user_id=self.user_id,
            role=self.role,
            session_id=self.session_id,
            details=details or {},
            latency_ms=latency_ms,
            success=success,
        )
        record = logging.LogRecord(
            name="uqs.audit",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=f"[{event.value}] user={self.user_id} role={self.role}",
            args=(),
            exc_info=None,
        )
        record.audit_entry = entry.model_dump()
        _logger.handle(record)
        return entry

    def error(self, message: str, exc: Exception | None = None) -> None:
        details: dict[str, Any] = {"message": message}
        if exc:
            details["exception_type"] = type(exc).__name__
            details["exception_msg"] = str(exc)
        self.log(AuditEvent.ERROR, details=details, success=False)


# ── Module-level convenience logger ───────────────────────────────────────────
# For system-level events (not tied to a specific user)
system_logger = AuditLogger(user_id="system", role="system", session_id="system")
