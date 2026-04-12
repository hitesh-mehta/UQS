"""
Role-Based Access Control (RBAC) — DB View Mapping.

Each user role maps to a set of read-only PostgreSQL views.
The LLM is ONLY given the schema for the views the current role can access.
This ensures the LLM never reasons over unauthorized data.

Security contract:
  - All views are defined at DB init time by a technical admin
  - All views are read-only (no INSERT/UPDATE/DELETE granted)
  - LLM context always uses role-scoped schema, never full schema
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text

from backend.core.database import get_db_session

# ── Role → View Mapping ───────────────────────────────────────────────────────
# format: role_name → list of view/table names accessible to that role
# "*" means all tables (admin only)

ROLE_SCHEMA_MAP: dict[str, list[str]] = {
    "admin": ["*"],                  # Full schema access
    "analyst": [                     # Aggregated views only
        "analyst_sales_view",
        "analyst_kpi_view",
        "analyst_customer_metrics_view",
    ],
    "regional_manager": [            # Region-filtered, no PII
        "rm_sales_view",
        "rm_customer_view",
        "rm_performance_view",
    ],
    "auditor": [                     # Audit trail only
        "audit_trail_view",
        "audit_access_log_view",
    ],
    "viewer": [                      # Summary dashboards only
        "dashboard_summary_view",
        "public_kpi_view",
    ],
}

# ── Schema cache (loaded from DB once per session) ────────────────────────────
_schema_cache: dict[str, list[dict]] = {}


async def get_role_views(role: str) -> list[str]:
    """Return the list of view names accessible to a given role."""
    if role not in ROLE_SCHEMA_MAP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown role: '{role}'. Contact your administrator.",
        )
    return ROLE_SCHEMA_MAP[role]


async def get_role_schema(role: str) -> list[dict]:
    """
    Load the schema (columns, types) for all views accessible to the given role.
    Returns a list of {view_name, columns: [{name, type, nullable}]} dicts.
    Results are cached in memory for the lifetime of the process.
    """
    if role in _schema_cache:
        return _schema_cache[role]

    views = await get_role_views(role)
    schema_data: list[dict] = []

    async with get_db_session() as session:
        if "*" in views:
            # Admin: load all user-defined tables and views
            result = await session.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type IN ('BASE TABLE', 'VIEW')
                ORDER BY table_name;
            """))
            views = [row[0] for row in result.fetchall()]

        for view_name in views:
            result = await session.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :view_name
                ORDER BY ordinal_position;
            """), {"view_name": view_name})
            columns = [
                {"name": row[0], "type": row[1], "nullable": row[2] == "YES"}
                for row in result.fetchall()
            ]
            if columns:  # Only include views that actually exist in DB
                schema_data.append({"view_name": view_name, "columns": columns})

    _schema_cache[role] = schema_data
    return schema_data


def format_schema_for_llm(schema: list[dict]) -> str:
    """
    Format the role-scoped schema into a compact string for LLM context injection.
    Example output:
        TABLE sales_fact_view:
          - id: integer
          - region: varchar
          - revenue: numeric
    """
    lines = []
    for table in schema:
        lines.append(f"TABLE {table['view_name']}:")
        for col in table["columns"]:
            nullable = " (nullable)" if col["nullable"] else ""
            lines.append(f"  - {col['name']}: {col['type']}{nullable}")
    return "\n".join(lines)


def invalidate_schema_cache(role: Optional[str] = None) -> None:
    """Invalidate the schema cache. Pass role to flush only that role."""
    if role:
        _schema_cache.pop(role, None)
    else:
        _schema_cache.clear()
