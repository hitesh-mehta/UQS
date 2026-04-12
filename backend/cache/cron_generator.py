"""
Cron-based Report Generator.
Generates comprehensive analytical reports on a schedule and stores them in the cache.
Runs at: hourly, daily, weekly, monthly granularities.

Each report generation:
  1. Runs SQL queries to aggregate all key metrics for the period
  2. Computes trends and anomaly flags
  3. Uses LLM to generate a summary narrative
  4. Stores in cache with FIFO eviction

Uses APScheduler for scheduling (no Celery dependency for hackathon simplicity).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

from backend.cache.cache_manager import CachedReport, Granularity, cache_manager
from backend.core.database import get_db_session
from backend.core.logger import AuditEvent, system_logger
from backend.llm.client import llm_json
from sqlalchemy import text


# ── Period Helpers ────────────────────────────────────────────────────────────

def _period_label(granularity: Granularity) -> tuple[str, str, str, str]:
    """Returns (period_key, start_date, end_date, coverage_description)."""
    now = datetime.now(timezone.utc)
    if granularity == "hourly":
        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        end = start + timedelta(hours=1)
        return (
            start.strftime("%Y-%m-%dT%H:00"),
            start.strftime("%Y-%m-%d %H:%M"),
            end.strftime("%Y-%m-%d %H:%M"),
            f"Hour ending {end.strftime('%H:%M')} on {end.strftime('%Y-%m-%d')}",
        )
    elif granularity == "daily":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return (
            start.strftime("%Y-%m-%d"),
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            f"Day: {start.strftime('%B %d, %Y')}",
        )
    elif granularity == "weekly":
        # ISO week
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return (
            start.strftime("%Y-W%W"),
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            f"Week {start.strftime('%W')}, {start.strftime('%B %d')} – {end.strftime('%B %d, %Y')}",
        )
    else:  # monthly
        first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_end = first_of_month - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        return (
            prev_month_start.strftime("%Y-%m"),
            prev_month_start.strftime("%Y-%m-%d"),
            first_of_month.strftime("%Y-%m-%d"),
            f"Month: {prev_month_start.strftime('%B %Y')}",
        )


# ── Report Generation ─────────────────────────────────────────────────────────

# Override these queries with your actual schema in production
REPORT_QUERIES: dict[str, str] = {
    "total_revenue": """
        SELECT COALESCE(SUM(revenue), 0) as value
        FROM sales_fact_view
        WHERE sale_date BETWEEN :start_date AND :end_date
    """,
    "transaction_count": """
        SELECT COUNT(*) as value
        FROM sales_fact_view
        WHERE sale_date BETWEEN :start_date AND :end_date
    """,
    "top_regions": """
        SELECT region, SUM(revenue) as revenue
        FROM sales_fact_view
        WHERE sale_date BETWEEN :start_date AND :end_date
        GROUP BY region
        ORDER BY revenue DESC
        LIMIT 5
    """,
    "average_order_value": """
        SELECT COALESCE(AVG(revenue), 0) as value
        FROM sales_fact_view
        WHERE sale_date BETWEEN :start_date AND :end_date
    """,
}


async def generate_report(granularity: Granularity) -> CachedReport:
    """
    Generate a comprehensive cached report for the given granularity period.
    Queries the DB, computes metrics, gets LLM narrative, stores in cache.
    """
    period_key, start_date, end_date, coverage = _period_label(granularity)
    system_logger.log(AuditEvent.CACHE_GENERATED, details={
        "granularity": granularity,
        "period": period_key,
        "start": start_date,
        "end": end_date,
    })

    # ── Run all metric queries ─────────────────────────────────────────────
    raw_data: dict[str, Any] = {}
    key_metrics: list[dict] = []

    async with get_db_session() as db:
        for metric_name, query_sql in REPORT_QUERIES.items():
            try:
                result = await db.execute(text(query_sql), {"start_date": start_date, "end_date": end_date})
                rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
                raw_data[metric_name] = rows
                if rows and "value" in rows[0]:
                    key_metrics.append({"label": metric_name.replace("_", " ").title(), "value": str(rows[0]["value"])})
            except Exception:
                raw_data[metric_name] = []

    # ── LLM narrative generation ───────────────────────────────────────────
    metrics_str = json.dumps({k: v[:5] for k, v in raw_data.items()}, indent=2, default=str)
    narrative_raw = await llm_json(
        system_prompt=f"You are a BI analyst. Generate a professional {granularity} summary report in JSON format.",
        user_message=f"""Period: {coverage}
Metrics data:
{metrics_str}

Generate a comprehensive summary. Response format:
{{
  "summary_narrative": "2-3 paragraph executive summary...",
  "trend_analysis": {{"metric": {{"direction": "up|down|stable", "insight": "..."}}}},
  "anomaly_flags": [{{"metric": "...", "description": "...", "severity": "high|medium|low"}}]
}}""",
        temperature=0.2,
    )

    report = CachedReport(
        granularity=granularity,
        period=period_key,
        generated_at=datetime.now(timezone.utc).isoformat(),
        coverage=coverage,
        metrics=list(REPORT_QUERIES.keys()),
        summary_narrative=narrative_raw.get("summary_narrative", f"{granularity.capitalize()} report for {period_key}"),
        key_metrics=key_metrics,
        trend_analysis=narrative_raw.get("trend_analysis", {}),
        anomaly_flags=narrative_raw.get("anomaly_flags", []),
        top_contributors={"revenue": raw_data.get("top_regions", [])},
        raw_data=raw_data,
    )

    cache_manager.store_report(report)
    return report


# ── APScheduler Setup ─────────────────────────────────────────────────────────

def setup_cron_jobs(app) -> None:
    """
    Register APScheduler jobs on FastAPI app startup.
    Call this in main.py if CRON_ENABLED=true.
    """
    from backend.config import settings
    if not settings.cron_enabled:
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        system_logger.error("APScheduler not installed. Run: pip install apscheduler")
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: generate_report("hourly"), "cron", minute=0)
    scheduler.add_job(lambda: generate_report("daily"), "cron", hour=2, minute=0)
    scheduler.add_job(lambda: generate_report("weekly"), "cron", day_of_week="sun", hour=3, minute=0)
    scheduler.add_job(lambda: generate_report("monthly"), "cron", day=1, hour=4, minute=0)

    # Continual learning retraining
    from backend.models.continual_learning import run_all_retraining
    scheduler.add_job(run_all_retraining, "cron", hour=5, minute=0)

    scheduler.start()
    system_logger.log(AuditEvent.CACHE_GENERATED, details={"message": "Cron jobs scheduled"})
