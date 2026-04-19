"""
Cron-based Report Generator — Schema-Adaptive Edition.

Generates comprehensive analytical reports on a schedule and stores them in cache.
Granularities: hourly | daily | weekly | monthly

KEY FIX: Schema-adaptive mode — auto-discovers available tables/views in the DB
so reports generate even without sales_fact_view.
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


# ── Schema Discovery ──────────────────────────────────────────────────────────

async def _discover_tables() -> list[dict]:
    """
    Auto-discover all tables/views in the public schema with their columns.
    Returns a list of {table_name, columns: [col_name, ...], has_date_col: bool}.
    """
    tables = []
    async with get_db_session() as db:
        result = await db.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type IN ('BASE TABLE', 'VIEW')
              AND table_name NOT LIKE 'uqs_%'
            ORDER BY table_name
            LIMIT 20;
        """))
        table_names = [row[0] for row in result.fetchall()]

        for table_name in table_names:
            col_result = await db.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :tname
                ORDER BY ordinal_position
                LIMIT 30;
            """), {"tname": table_name})
            cols = col_result.fetchall()
            col_names = [c[0] for c in cols]
            date_cols = [c[0] for c in cols if any(dt in c[1].lower() for dt in ("date", "timestamp", "time"))]
            numeric_cols = [c[0] for c in cols if any(dt in c[1].lower() for dt in ("numeric", "integer", "bigint", "float", "double", "real", "decimal"))]
            tables.append({
                "table_name": table_name,
                "columns": col_names,
                "date_col": date_cols[0] if date_cols else None,
                "numeric_cols": numeric_cols,
            })

    return tables


async def _run_adaptive_queries(
    tables: list[dict],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """
    Build and run queries dynamically based on discovered schema.
    Returns raw_data dict and key_metrics list.
    """
    raw_data: dict[str, Any] = {}
    key_metrics: list[dict] = []

    async with get_db_session() as db:
        for table_info in tables[:5]:  # cap at 5 tables
            tname = table_info["table_name"]
            date_col = table_info["date_col"]
            numeric_cols = table_info["numeric_cols"]

            # Row count (always possible)
            try:
                if date_col:
                    count_result = await db.execute(
                        text(f'SELECT COUNT(*) as cnt FROM "{tname}" WHERE "{date_col}" BETWEEN :s AND :e'),
                        {"s": start_date, "e": end_date},
                    )
                else:
                    count_result = await db.execute(text(f'SELECT COUNT(*) as cnt FROM "{tname}"'))
                cnt_row = count_result.fetchone()
                row_count = cnt_row[0] if cnt_row else 0
                raw_data[f"{tname}_row_count"] = row_count
                key_metrics.append({"label": f"{tname} Records", "value": str(row_count)})
            except Exception:
                pass

            # Sum of numeric columns
            for col in numeric_cols[:3]:
                try:
                    if date_col:
                        sum_result = await db.execute(
                            text(f'SELECT COALESCE(SUM("{col}"), 0) as total FROM "{tname}" WHERE "{date_col}" BETWEEN :s AND :e'),
                            {"s": start_date, "e": end_date},
                        )
                    else:
                        sum_result = await db.execute(
                            text(f'SELECT COALESCE(SUM("{col}"), 0) as total FROM "{tname}"')
                        )
                    sum_row = sum_result.fetchone()
                    total = float(sum_row[0]) if sum_row else 0.0
                    raw_data[f"{tname}_{col}_sum"] = total
                    key_metrics.append({
                        "label": f"{tname}.{col} Total",
                        "value": f"{total:,.2f}",
                    })
                except Exception:
                    pass

    return raw_data, key_metrics


# ── Main Report Generator ─────────────────────────────────────────────────────

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
    Uses schema-adaptive queries that work with any database structure.
    """
    period_key, start_date, end_date, coverage = _period_label(granularity)
    system_logger.log(AuditEvent.CACHE_GENERATED, details={
        "granularity": granularity,
        "period": period_key,
        "start": start_date,
        "end": end_date,
    })

    raw_data: dict[str, Any] = {}
    key_metrics: list[dict] = []

    # Try the known schema first; fall back to adaptive discovery
    used_adaptive = False
    async with get_db_session() as db:
        for metric_name, query_sql in REPORT_QUERIES.items():
            try:
                result = await db.execute(text(query_sql), {"start_date": start_date, "end_date": end_date})
                rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
                raw_data[metric_name] = rows
                if rows and "value" in rows[0]:
                    key_metrics.append({
                        "label": metric_name.replace("_", " ").title(),
                        "value": str(rows[0]["value"]),
                    })
            except Exception:
                raw_data[metric_name] = []

    # If no data at all, use adaptive schema discovery
    if not any(raw_data.values()):
        used_adaptive = True
        try:
            tables = await _discover_tables()
            if tables:
                adaptive_data, adaptive_metrics = await _run_adaptive_queries(tables, start_date, end_date)
                raw_data.update(adaptive_data)
                key_metrics.extend(adaptive_metrics)
        except Exception as exc:
            system_logger.error(f"Adaptive query failed: {exc}")

    # If still no data, generate a structural report
    if not key_metrics:
        key_metrics = [{"label": "Report Generated", "value": "No live data yet — schema shows DB is connected"}]
        raw_data["note"] = ["Database connected but no data tables found in the queried period."]

    # ── LLM narrative generation ───────────────────────────────────────────
    metrics_str = json.dumps(
        {k: (v[:3] if isinstance(v, list) else v) for k, v in raw_data.items()},
        indent=2,
        default=str,
    )
    adaptive_note = " (schema-adaptive mode — using auto-discovered tables)" if used_adaptive else ""

    try:
        narrative_raw = await llm_json(
            system_prompt=(
                f"You are an expert BI analyst. Generate a professional {granularity} business intelligence "
                f"summary report in JSON format{adaptive_note}."
            ),
            user_message=f"""Period: {coverage}
Metrics data:
{metrics_str}

Generate a comprehensive business summary. Response format:
{{
  "summary_narrative": "2-3 paragraph executive summary with actionable insights...",
  "trend_analysis": {{"metric_name": {{"direction": "up|down|stable", "insight": "why this happened"}}}},
  "anomaly_flags": [{{"metric": "...", "description": "...", "severity": "high|medium|low"}}]
}}""",
            temperature=0.2,
        )
    except Exception:
        narrative_raw = {}

    report = CachedReport(
        granularity=granularity,
        period=period_key,
        generated_at=datetime.now(timezone.utc).isoformat(),
        coverage=coverage,
        metrics=list(raw_data.keys()),
        summary_narrative=narrative_raw.get(
            "summary_narrative",
            f"{granularity.capitalize()} intelligence report for {coverage}. "
            f"Data collected from {len(raw_data)} metric sources. "
            f"{'Schema-adaptive mode used — direct queries auto-generated from discovered tables.' if used_adaptive else 'Standard schema queries used.'}",
        ),
        key_metrics=key_metrics,
        trend_analysis=narrative_raw.get("trend_analysis", {}),
        anomaly_flags=narrative_raw.get("anomaly_flags", []),
        top_contributors={"data": list(raw_data.items())[:3]},
        raw_data=raw_data,
    )

    cache_manager.store_report(report)
    system_logger.log(AuditEvent.CACHE_GENERATED, details={
        "granularity": granularity,
        "period": period_key,
        "metrics_count": len(key_metrics),
        "adaptive": used_adaptive,
    })
    return report


# ── APScheduler Setup ─────────────────────────────────────────────────────────

def setup_cron_jobs(app) -> None:
    """Register APScheduler jobs on FastAPI app startup."""
    from backend.config import settings
    if not settings.cron_enabled:
        system_logger.info("Cron jobs disabled (CRON_ENABLED=false). Cache reports will only appear after manual generation.")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        system_logger.error("APScheduler not installed. Run: pip install apscheduler")
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(generate_report, "cron", args=["hourly"], minute=0)
    scheduler.add_job(generate_report, "cron", args=["daily"], hour=2, minute=0)
    scheduler.add_job(generate_report, "cron", args=["weekly"], day_of_week="sun", hour=3, minute=0)
    scheduler.add_job(generate_report, "cron", args=["monthly"], day=1, hour=4, minute=0)

    from backend.models.continual_learning import run_all_retraining
    scheduler.add_job(run_all_retraining, "cron", hour=5, minute=0)

    scheduler.start()
    app.state.scheduler = scheduler
    system_logger.log(AuditEvent.CACHE_GENERATED, details={"message": "Cron jobs scheduled (4 granularities + retraining)"})
