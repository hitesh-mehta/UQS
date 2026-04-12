"""
SQL Engine — SOTA NL→SQL pipeline.
Implements patterns from DIN-SQL, DAIL-SQL, and C3.

Pipeline:
  1. Schema Injection (role-scoped)
  2. Schema Linking (LLM identifies relevant tables/columns)
  3. SQL Generation (LLM with few-shot examples)
  4. Safety Validation (block DML/DDL)
  5. SQL Execution on DB view
  6. Self-Correction Loop (retry once on failure)
  7. Result Formatting (LLM narrative + table)
"""
from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy import text

from backend.core.database import get_db_session
from backend.core.logger import AuditEvent, AuditLogger
from backend.llm.client import llm_json
from backend.llm.context_manager import UserSession
from backend.llm.prompts.all_prompts import build_formatter_prompt, build_sql_prompt
from pydantic import BaseModel


# ── Result Models ─────────────────────────────────────────────────────────────

class SQLResult(BaseModel):
    sql: str
    rows: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    explanation: str
    sources: list[str]
    latency_ms: float
    from_cache: bool = False
    corrected: bool = False   # True if self-correction was triggered


# ── Safety Validation ─────────────────────────────────────────────────────────

_BLOCKED_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

def _is_safe_sql(sql: str) -> tuple[bool, str]:
    """Returns (is_safe, reason). Blocks any DML or DDL."""
    match = _BLOCKED_PATTERNS.search(sql)
    if match:
        return False, f"Blocked dangerous SQL keyword: {match.group(0).upper()}"
    if not sql.strip().upper().startswith("SELECT"):
        return False, "Only SELECT statements are allowed."
    return True, ""


# ── SQL Engine ────────────────────────────────────────────────────────────────

class SQLEngine:
    """
    Converts natural language to SQL and executes it against the role-scoped DB view.
    Implements a self-correction loop: if execution fails, the error is fed back
    to the LLM for one retry attempt.
    """

    # Domain-specific few-shot examples (seeded at startup by admin)
    _few_shot_examples: list[dict] = []

    @classmethod
    def add_few_shot_example(cls, question: str, sql: str) -> None:
        cls._few_shot_examples.append({"question": question, "sql": sql})

    async def run(
        self,
        session: UserSession,
        query: str,
        audit: AuditLogger | None = None,
    ) -> SQLResult:
        start = time.perf_counter()

        # ── Step 1 & 2: Schema Injection + SQL Generation ──────────────────
        sql, explanation, relevant_tables = await self._generate_sql(
            session=session,
            query=query,
            error_feedback="",
            audit=audit,
        )

        # ── Step 3: Safety Check ───────────────────────────────────────────
        is_safe, reason = _is_safe_sql(sql)
        if not is_safe:
            if audit:
                audit.log(AuditEvent.SQL_BLOCKED, details={"sql": sql, "reason": reason}, success=False)
            raise ValueError(f"SQL safety check failed: {reason}")

        # ── Step 4: Execute ────────────────────────────────────────────────
        corrected = False
        try:
            rows, columns = await self._execute_sql(sql)
        except Exception as exec_err:
            # ── Step 5: Self-Correction Loop ───────────────────────────────
            if audit:
                audit.log(AuditEvent.SQL_CORRECTED, details={"error": str(exec_err), "original_sql": sql})
            corrected = True
            sql, explanation, relevant_tables = await self._generate_sql(
                session=session,
                query=query,
                error_feedback=str(exec_err),
                audit=audit,
            )
            is_safe, reason = _is_safe_sql(sql)
            if not is_safe:
                raise ValueError(f"Corrected SQL is still unsafe: {reason}")
            rows, columns = await self._execute_sql(sql)   # Raise if still fails

        latency_ms = (time.perf_counter() - start) * 1000

        if audit:
            audit.log(
                AuditEvent.SQL_EXECUTED,
                details={"sql": sql, "row_count": len(rows), "corrected": corrected},
                latency_ms=latency_ms,
            )

        return SQLResult(
            sql=sql,
            rows=rows,
            columns=columns,
            row_count=len(rows),
            explanation=explanation,
            sources=relevant_tables,
            latency_ms=latency_ms,
            corrected=corrected,
        )

    async def _generate_sql(
        self,
        session: UserSession,
        query: str,
        error_feedback: str,
        audit: AuditLogger | None,
    ) -> tuple[str, str, list[str]]:
        system_prompt, user_message = build_sql_prompt(
            schema_str=session.schema_str,
            user_query=query,
            use_case_context=session.use_case_context,
            error_feedback=error_feedback,
            few_shot_examples=self._few_shot_examples,
        )
        raw = await llm_json(system_prompt=system_prompt, user_message=user_message, temperature=0.0)

        sql: str = raw.get("sql", "").strip()
        explanation: str = raw.get("explanation", "")
        relevant_tables: list[str] = raw.get("relevant_tables", [])

        if audit:
            audit.log(AuditEvent.SQL_GENERATED, details={"sql": sql, "tables": relevant_tables})

        return sql, explanation, relevant_tables

    async def _execute_sql(self, sql: str) -> tuple[list[dict], list[str]]:
        """Execute a SELECT query and return rows + column names."""
        async with get_db_session() as session:
            result = await session.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return rows, columns
