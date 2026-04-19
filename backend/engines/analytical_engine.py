"""
Analytical Engine — Algorithm Brain for complex insight queries.
Sits on top of the SQL Engine and handles:
  - Trend Analysis
  - Causal / Diagnostic (Why did X happen?)
  - Comparative (A vs B)
  - What-If / Scenario
  - Time-Series decomposition
  - Metric Decomposition

The LLM acts as a reasoning brain:
  1. Deconstructs the query into atomic SQL sub-problems
  2. Selects the appropriate statistical algorithm
  3. Orchestrates parallel SQL calls
  4. Synthesizes results into a coherent narrative
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import numpy as np
from pydantic import BaseModel

from backend.core.logger import AuditEvent, AuditLogger
from backend.engines.sql_engine import SQLEngine, SQLResult
from backend.llm.client import llm_json
from backend.llm.context_manager import UserSession
from backend.llm.prompts.all_prompts import build_analytical_prompt, build_formatter_prompt


# ── Result Model ──────────────────────────────────────────────────────────────

class AnalyticalResult(BaseModel):
    analysis_type: str
    narrative: str
    headline: str
    key_metrics: list[dict[str, Any]] = []
    chart_data: dict[str, Any] | None = None
    chart_type: str = "bar"
    sources: list[str] = []
    sql_queries_run: list[str] = []
    latency_ms: float = 0


# ── Statistical Helpers ───────────────────────────────────────────────────────

def _compute_trend(values: list[float]) -> dict[str, Any]:
    """Simple linear regression to determine trend direction and slope."""
    if len(values) < 2:
        return {"slope": 0, "direction": "stable", "r_squared": 0}
    x = np.arange(len(values), dtype=float)
    y = np.array(values, dtype=float)
    coeffs = np.polyfit(x, y, 1)
    slope = float(coeffs[0])
    residuals = y - np.polyval(coeffs, x)
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    direction = "increasing" if slope > 0 else ("decreasing" if slope < 0 else "stable")
    return {"slope": round(slope, 4), "direction": direction, "r_squared": round(r_squared, 4)}


def _period_over_period_change(current: float, previous: float) -> dict[str, Any]:
    """Calculate period-over-period change and percentage."""
    if previous == 0:
        return {"absolute": current, "percent": None, "direction": "new"}
    delta = current - previous
    pct = (delta / abs(previous)) * 100
    return {
        "absolute": round(delta, 2),
        "percent": round(pct, 2),
        "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
    }


def _top_contributors(rows: list[dict], label_key: str, value_key: str, n: int = 5) -> list[dict]:
    """Find top N contributors to a metric."""
    sorted_rows = sorted(rows, key=lambda r: float(r.get(value_key, 0) or 0), reverse=True)
    total = sum(float(r.get(value_key, 0) or 0) for r in sorted_rows)
    result = []
    for row in sorted_rows[:n]:
        val = float(row.get(value_key, 0) or 0)
        result.append({
            "label": row.get(label_key, "Unknown"),
            "value": val,
            "share_pct": round((val / total * 100) if total > 0 else 0, 1),
        })
    return result


# ── Analytical Engine ─────────────────────────────────────────────────────────

class AnalyticalEngine:
    def __init__(self):
        self._sql_engine = SQLEngine()

    async def run(
        self,
        session: UserSession,
        query: str,
        sub_type: str = "",
        audit: AuditLogger | None = None,
    ) -> AnalyticalResult:
        start = time.perf_counter()

        # ── Step 1: LLM plans the analytical approach ──────────────────────
        system_prompt, user_message = build_analytical_prompt(
            schema_str=session.schema_str,
            user_query=query,
            use_case_context=session.use_case_context,
            sub_type=sub_type,
        )
        plan = await llm_json(system_prompt, user_message, temperature=0.1)

        analysis_type = plan.get("analysis_type", "decomposition")
        sql_sub_queries: list[dict] = plan.get("sql_sub_queries", [])
        statistical_method = plan.get("statistical_method", "")
        viz_type = plan.get("visualization_type", "bar")
        response_template = plan.get("response_template", "")

        if audit:
            audit.log(AuditEvent.ENGINE_ROUTED, details={
                "engine": "analytical",
                "analysis_type": analysis_type,
                "num_sub_queries": len(sql_sub_queries),
            })

        # ── Step 2: Execute SQL sub-queries in parallel ────────────────────
        tasks = [
            self._run_sub_query(session, sq, audit)
            for sq in sql_sub_queries
        ]
        sub_results: list[tuple[str, list[dict], list[str]]] = await asyncio.gather(*tasks, return_exceptions=False)

        # ── Step 3: Statistical processing ────────────────────────────────
        chart_data, key_metrics = self._process_results(sub_results, analysis_type, query)

        # ── Step 4: LLM synthesizes narrative ─────────────────────────────
        all_sources = [table for _, _, tables in sub_results for table in tables]
        combined_data_str = self._serialize_results(sub_results)

        formatter_system, formatter_user = build_formatter_prompt(
            user_query=query,
            raw_results=combined_data_str,
            engine_type="analytical",
            sources=list(set(all_sources)),
        )
        formatted = await llm_json(formatter_system, formatter_user, temperature=0.2)

        latency_ms = (time.perf_counter() - start) * 1000

        if audit:
            audit.log(AuditEvent.ENGINE_RESPONSE, details={
                "engine": "analytical",
                "analysis_type": analysis_type,
            }, latency_ms=latency_ms)

        return AnalyticalResult(
            analysis_type=analysis_type,
            narrative=formatted.get("answer", response_template),
            headline=formatted.get("headline", ""),
            key_metrics=formatted.get("key_metrics", key_metrics),
            chart_data=chart_data,
            chart_type=viz_type,
            sources=list(set(all_sources)),
            sql_queries_run=[sq.get("sql", "") for sq in sql_sub_queries],
            latency_ms=latency_ms,
        )

    async def _run_sub_query(
        self,
        session: UserSession,
        sub_query: dict,
        audit: AuditLogger | None,
    ) -> tuple[str, list[dict], list[str]]:
        """Execute one SQL sub-query and return (purpose, rows, sources)."""
        from sqlalchemy import text
        from backend.core.database import get_db_session
        sql = sub_query.get("sql", "").strip()
        purpose = sub_query.get("purpose", "")
        if not sql:
            return purpose, [], []
        try:
            from decimal import Decimal
            from datetime import date, datetime, time as dt_time, timedelta

            def _json_safe(val):
                if isinstance(val, Decimal):
                    return float(val)
                if isinstance(val, (datetime, date, dt_time)):
                    return val.isoformat()
                if isinstance(val, timedelta):
                    return str(val)
                return val

            async with get_db_session() as db:
                result = await db.execute(text(sql))
                columns = list(result.keys())
                rows = [
                    {col: _json_safe(val) for col, val in zip(columns, row)}
                    for row in result.fetchall()
                ]
            # Extract table names from SQL (simple heuristic)
            import re
            tables = re.findall(r'\bFROM\s+(\w+)|\bJOIN\s+(\w+)', sql, re.IGNORECASE)
            sources = list({t for pair in tables for t in pair if t})
            return purpose, rows, sources
        except Exception as e:
            return purpose, [], []

    def _process_results(
        self,
        sub_results: list[tuple[str, list[dict], list[str]]],
        analysis_type: str,
        query: str,
    ) -> tuple[dict | None, list[dict]]:
        """Apply statistical processing to sub-query results."""
        if not sub_results:
            return None, []

        _, first_rows, _ = sub_results[0]
        if not first_rows:
            return None, []

        chart_data: dict | None = None
        key_metrics: list[dict] = []

        cols = list(first_rows[0].keys()) if first_rows else []
        numeric_cols = [c for c in cols if all(
            isinstance(r.get(c), (int, float)) for r in first_rows if r.get(c) is not None
        )]
        label_col = next((c for c in cols if c not in numeric_cols), None)
        value_col = numeric_cols[0] if numeric_cols else None

        if value_col and label_col:
            labels = [str(r.get(label_col, "")) for r in first_rows]
            values = [float(r.get(value_col, 0) or 0) for r in first_rows]
            chart_data = {"labels": labels, "datasets": [{"label": value_col, "data": values}]}

            if analysis_type == "trend_analysis" and len(values) >= 2:
                trend = _compute_trend(values)
                key_metrics.append({
                    "label": "Trend",
                    "value": trend["direction"].capitalize(),
                    "change": f"slope={trend['slope']}",
                })

            if analysis_type in ("causal_diagnostic", "decomposition") and value_col:
                top = _top_contributors(first_rows, label_col, value_col)
                for item in top:
                    key_metrics.append({
                        "label": str(item["label"]),
                        "value": str(item["value"]),
                        "change": f"{item['share_pct']}% share",
                    })

        return chart_data, key_metrics

    def _serialize_results(self, sub_results: list[tuple[str, list[dict], list[str]]]) -> str:
        parts = []
        for purpose, rows, _ in sub_results:
            parts.append(f"[{purpose}]")
            if rows:
                headers = list(rows[0].keys())
                parts.append(" | ".join(headers))
                for row in rows[:20]:
                    parts.append(" | ".join(str(row.get(h, "")) for h in headers))
            else:
                parts.append("(no data)")
        return "\n".join(parts)
