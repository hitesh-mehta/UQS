"""
Database initialisation script for UQS.

Creates the two dynamic RBAC tables in Supabase and seeds default roles:
  - uqs_roles            — role registry (name, description)
  - uqs_role_permissions — role → view mapping (role_name, view_name)

Run once at setup:
    python -m scripts.init_db

Safe to re-run — uses CREATE TABLE IF NOT EXISTS and INSERT ... ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import text

# Allow running as `python -m scripts.init_db` from project root
sys.path.insert(0, ".")

from backend.core.database import get_db_session

log = logging.getLogger("uqs.init_db")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


# ── SQL Statements ────────────────────────────────────────────────────────────

CREATE_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS uqs_roles (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
"""

CREATE_PERMISSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS uqs_role_permissions (
    id          SERIAL PRIMARY KEY,
    role_name   TEXT NOT NULL,
    view_name   TEXT NOT NULL,               -- '*' means full access (admin only)
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (role_name, view_name)
);
"""

# Default roles — add more via Supabase dashboard or SQL
SEED_ROLES = [
    ("admin",            "Full schema access — all tables and columns"),
    ("analyst",          "Aggregated views only, no PII, no row-level data"),
    ("regional_manager", "Region-filtered aggregated views, no PII"),
    ("auditor",          "Audit trail tables only"),
    ("viewer",           "Summary dashboard views only"),
]

# Default view permissions per role
# These map to the REAL views/tables in the Supabase database.
# Extend via Supabase dashboard or SQL after deployment.
SEED_PERMISSIONS = [
    # admin gets wildcard — full public schema
    ("admin",            "*"),
    # analyst — all analytical views
    ("analyst",          "daily_sales_view"),
    ("analyst",          "monthly_revenue_view"),
    ("analyst",          "top_products_view"),
    ("analyst",          "low_inventory_view"),
    ("analyst",          "employee_performance_view"),
    # regional manager — sales and inventory
    ("regional_manager", "daily_sales_view"),
    ("regional_manager", "monthly_revenue_view"),
    ("regional_manager", "low_inventory_view"),
    # auditor — sales and employee performance
    ("auditor",          "daily_sales_view"),
    ("auditor",          "employee_performance_view"),
    # viewer — summary views only
    ("viewer",           "daily_sales_view"),
    ("viewer",           "monthly_revenue_view"),
    ("viewer",           "top_products_view"),
]

# Demo views — created if they don't exist (for hackathon without real data)
CREATE_DEMO_VIEWS = """
-- Demo view: analyst sees aggregated sales
CREATE OR REPLACE VIEW analyst_sales_view AS
SELECT
    'North'::text              AS region,
    'Electronics'::text        AS product_category,
    DATE_TRUNC('month', NOW()) AS month,
    142500.00::numeric         AS total_revenue,
    320::integer               AS transaction_count
LIMIT 0;  -- Empty skeleton — replace with real data query

-- Demo view: dashboard summary
CREATE OR REPLACE VIEW dashboard_summary_view AS
SELECT
    'All'::text  AS region,
    0::numeric   AS total_revenue,
    0::integer   AS active_customers
LIMIT 0;
"""


async def run():
    log.info("Connecting to Supabase PostgreSQL...")
    async with get_db_session() as session:
        # Create tables
        log.info("Creating uqs_roles table...")
        await session.execute(text(CREATE_ROLES_TABLE))

        log.info("Creating uqs_role_permissions table...")
        await session.execute(text(CREATE_PERMISSIONS_TABLE))

        # Seed roles
        log.info("Seeding default roles...")
        for name, description in SEED_ROLES:
            await session.execute(
                text("""
                    INSERT INTO uqs_roles (name, description)
                    VALUES (:name, :description)
                    ON CONFLICT (name) DO NOTHING;
                """),
                {"name": name, "description": description},
            )

        # Seed permissions
        log.info("Seeding default view permissions...")
        for role_name, view_name in SEED_PERMISSIONS:
            await session.execute(
                text("""
                    INSERT INTO uqs_role_permissions (role_name, view_name)
                    VALUES (:role_name, :view_name)
                    ON CONFLICT (role_name, view_name) DO NOTHING;
                """),
                {"role_name": role_name, "view_name": view_name},
            )

        # Commit tables and seeds FIRST to ensure they are saved!
        await session.commit()

        # Create demo views
        log.info("Creating demo views (skeletons)...")
        try:
            await session.execute(text(CREATE_DEMO_VIEWS))
        except Exception as e:
            log.warning(f"Demo views skipped (may already exist): {e}")

        await session.commit()

    log.info("✅ Database initialisation complete.")
    log.info("   uqs_roles and uqs_role_permissions tables are ready.")
    log.info("   Add your real views in Supabase and register them in uqs_role_permissions.")


if __name__ == "__main__":
    asyncio.run(run())
