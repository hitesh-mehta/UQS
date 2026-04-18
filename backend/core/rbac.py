"""
Dynamic Role-Based Access Control (RBAC) for UQS.

DESIGN PRINCIPLE — Defence in Depth:
  Layer 1: JWT token carries the user's role
  Layer 2: This module fetches ONLY that role's permitted views from the DB
  Layer 3: Only those views' schemas are injected into the LLM system prompt
  Layer 4: SQL safety check blocks DML/DDL regardless of LLM output

DYNAMIC RBAC:
  Roles and their view permissions are stored in two Supabase tables:
    - uqs_roles            (id, name, description)
    - uqs_role_permissions (role_name, view_name)

  This means admins can add new roles or grant/revoke view access directly
  from the Supabase dashboard — NO code changes or redeployment needed.

  "*" as view_name = full schema access (admin only).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text

from backend.core.database import get_db_session

log = logging.getLogger("uqs.rbac")

# Caching has been completely removed as requested.
# The system now fetches 100% dynamically from Supabase on every request.
_role_views_cache: dict[str, list[str]] = {}
_schema_cache: dict[str, list[dict]] = {}


# ── Dynamic role → views lookup ───────────────────────────────────────────────

async def get_role_views(role: str) -> list[str]:
    """
    Fetch the list of view names permitted for this role from uqs_role_permissions.
    Results are fetched dynamically every time.

    Falls back to a safe default (empty list → schema injection blocked)
    if the role is not found in the DB.
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(
                text("""
                    SELECT view_name
                    FROM uqs_role_permissions
                    WHERE role_name = :role
                    ORDER BY view_name;
                """),
                {"role": role},
            )
            rows = result.fetchall()

        if not rows:
            log.warning(f"No permissions found in DB for role '{role}'. Returning empty schema.")
            # Don't raise — just return empty list so LLM gets no schema
            _role_views_cache[role] = []
            return []

        views = [row[0] for row in rows]
        log.info(f"Loaded {len(views)} views for role '{role}' from DB")
        return views

    except Exception as exc:
        log.error(f"Failed to fetch views for role '{role}' from DB: {exc}")
        # Safe fallback — never expose data on DB errors
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load role permissions. Please try again shortly.",
        )


async def get_all_roles() -> list[dict]:
    """
    Returns all roles defined in uqs_roles table.
    Used by the frontend auth modal to show available roles dynamically.
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(
                text("SELECT name, description FROM uqs_roles ORDER BY name;")
            )
            rows = result.fetchall()
        return [{"name": row[0], "description": row[1] or ""} for row in rows]
    except Exception as exc:
        log.error(f"Failed to fetch roles from DB: {exc}")
        # Return sensible defaults so the UI doesn't break
        return [
            {"name": "admin",            "description": "Full schema access"},
            {"name": "analyst",          "description": "Aggregated views only"},
            {"name": "regional_manager", "description": "Region-filtered views"},
            {"name": "auditor",          "description": "Audit trail only"},
            {"name": "viewer",           "description": "Summary dashboards"},
        ]


# ── Schema loader ─────────────────────────────────────────────────────────────

async def get_role_schema(role: str) -> list[dict]:
    """
    Load the schema (columns, types) for all views accessible to the given role.
    Queries information_schema.columns for each permitted view.
    Fetched dynamically on every query.
    """
    views = await get_role_views(role)
    if not views:
        return []

    schema_data: list[dict] = []

    async with get_db_session() as session:
        # Admin with "*" wildcard — load full public schema
        if "*" in views:
            result = await session.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type IN ('BASE TABLE', 'VIEW')
                  AND table_name NOT LIKE 'uqs_%'
                ORDER BY table_name;
            """))
            views = [row[0] for row in result.fetchall()]

        for view_name in views:
            result = await session.execute(
                text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :view_name
                    ORDER BY ordinal_position;
                """),
                {"view_name": view_name},
            )
            columns = [
                {"name": row[0], "type": row[1], "nullable": row[2] == "YES"}
                for row in result.fetchall()
            ]
            if columns:
                schema_data.append({"view_name": view_name, "columns": columns})

    log.info(f"Schema loaded completely dynamically for role '{role}': {len(schema_data)} views")
    return schema_data


# ── LLM Formatter ─────────────────────────────────────────────────────────────

def format_schema_for_llm(schema: list[dict]) -> str:
    """
    Serialize role-scoped schema into a compact string for LLM prompt injection.

    Example output:
        TABLE analyst_sales_view:
          - region: character varying
          - total_revenue: numeric
          - month: timestamp without time zone (nullable)
    """
    if not schema:
        return "(No tables available for this role)"
    lines = []
    for table in schema:
        lines.append(f"TABLE {table['view_name']}:")
        for col in table["columns"]:
            nullable = " (nullable)" if col["nullable"] else ""
            lines.append(f"  - {col['name']}: {col['type']}{nullable}")
    return "\n".join(lines)


# ── Cache Invalidation ────────────────────────────────────────────────────────

def invalidate_schema_cache(role: Optional[str] = None) -> None:
    """
    Flush the in-memory RBAC + schema cache.
    Call this after adding/removing role permissions in the DB.
    """
    global _role_views_cache, _schema_cache
    if role:
        _role_views_cache.pop(role, None)
        _schema_cache.pop(role, None)
        log.info(f"RBAC cache invalidated for role: {role}")
    else:
        _role_views_cache.clear()
        _schema_cache.clear()
        log.info("RBAC cache fully invalidated")
