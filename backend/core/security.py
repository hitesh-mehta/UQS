"""
Security middleware for UQS:
  - Rate limiting (slowapi): 30 req/min per user IP on query endpoints
  - Input sanitization: length cap, null-byte strip, prompt-injection hints
  - SQL blocklist expansion
  - Timeout enforcement helpers
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import settings

# ── Rate Limiter singleton ────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# ── Prompt injection patterns (heuristic) ────────────────────────────────────
_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+previous|disregard\s+(all|prior|above)|you\s+are\s+now|"
    r"act\s+as|system\s*:\s*|<\s*system\s*>|jailbreak|pretend\s+you|"
    r"forget\s+your\s+instructions|override\s+(your|the)\s+(instructions|rules))",
    re.IGNORECASE,
)

# ── Expanded SQL safety blocklist ─────────────────────────────────────────────
SQL_DANGEROUS_KEYWORDS = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
    "EXEC", "EXECUTE", "CALL", "COPY", "LOAD", "IMPORT", "GRANT", "REVOKE",
    "ATTACH", "DETACH", "PRAGMA", "REPLACE", "MERGE", "UPSERT",
    "--", "/*", "*/", "xp_", "sp_",
})


def sanitize_query(query: str) -> tuple[str, Optional[str]]:
    """
    Sanitize a user query.
    Returns (cleaned_query, error_message).
    If error_message is not None, the request should be rejected.
    """
    if not query or not query.strip():
        return "", "Query cannot be empty."

    # Strip null bytes and control chars
    query = query.replace("\x00", "").strip()
    query = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", query)

    # Length cap
    max_len = settings.query_max_length
    if len(query) > max_len:
        return "", f"Query too long ({len(query)} chars). Maximum is {max_len} characters."

    # Prompt injection heuristic
    if _INJECTION_PATTERNS.search(query):
        return "", "Query contains patterns that appear to be attempting prompt injection."

    return query, None


def is_safe_sql(sql: str) -> tuple[bool, str]:
    """
    Validate a generated SQL string against the expanded blocklist.
    Returns (is_safe, reason).
    Used by the SQL engine as a defence-in-depth check.
    """
    sql_upper = sql.upper()
    for keyword in SQL_DANGEROUS_KEYWORDS:
        # Word-boundary check for keywords, exact match for symbols
        if keyword.isalpha() or keyword.startswith("xp_") or keyword.startswith("sp_"):
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, sql_upper):
                return False, f"Blocked keyword detected: {keyword}"
        elif keyword in sql:
            return False, f"Blocked token detected: {keyword}"
    return True, ""


def get_rate_limit_string() -> str:
    """Return the slowapi rate limit string from config."""
    return f"{settings.rate_limit_per_minute}/minute"
