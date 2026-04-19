"""
Database initialisation script for UQS.

Creates RBAC tables, seeds roles (including manager), and creates the
uqs_tenants table for multi-tenancy support.

Run once at setup:
    python -m scripts.init_db

Safe to re-run — uses CREATE TABLE IF NOT EXISTS and INSERT ... ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import text

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
    view_name   TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (role_name, view_name)
);
"""

CREATE_TENANTS_TABLE = """
CREATE TABLE IF NOT EXISTS uqs_tenants (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    supabase_url  TEXT NOT NULL,
    anon_key      TEXT NOT NULL,
    service_key   TEXT NOT NULL,
    db_url        TEXT NOT NULL,
    contact_email TEXT,
    active        BOOLEAN DEFAULT true,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
"""

# Default roles — manager is now a first-class role (= admin-level access)
SEED_ROLES = [
    ("admin",            "Full schema access — all tables and columns"),
    ("manager",          "Full schema access + team management — equivalent to admin"),
    ("analyst",          "Aggregated views only, no PII, no row-level data"),
    ("regional_manager", "Region-filtered aggregated views, no PII"),
    ("auditor",          "Audit trail tables only"),
    ("viewer",           "Summary dashboard views only"),
]

SEED_PERMISSIONS = [
    # admin + manager both get wildcard — full public schema
    ("admin",            "*"),
    ("manager",          "*"),
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


async def run():
    log.info("Connecting to Supabase PostgreSQL...")
    async with get_db_session() as session:
        log.info("Creating uqs_roles table...")
        await session.execute(text(CREATE_ROLES_TABLE))

        log.info("Creating uqs_role_permissions table...")
        await session.execute(text(CREATE_PERMISSIONS_TABLE))

        log.info("Creating uqs_tenants table...")
        await session.execute(text(CREATE_TENANTS_TABLE))

        log.info("Seeding default roles (including manager)...")
        for name, description in SEED_ROLES:
            await session.execute(
                text("""
                    INSERT INTO uqs_roles (name, description)
                    VALUES (:name, :description)
                    ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description;
                """),
                {"name": name, "description": description},
            )

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

        await session.commit()
        log.info("✅ Tables and seeds committed.")

        # Demo views (best-effort)
        log.info("Creating demo skeleton views...")
        demo_views = [
            """
            CREATE OR REPLACE VIEW daily_sales_view AS
            SELECT
                'North'::text        AS region,
                'Electronics'::text  AS product_category,
                CURRENT_DATE         AS sale_date,
                0::numeric           AS revenue,
                0::integer           AS transaction_count
            LIMIT 0;
            """,
            """
            CREATE OR REPLACE VIEW monthly_revenue_view AS
            SELECT
                'North'::text                          AS region,
                DATE_TRUNC('month', CURRENT_DATE)     AS month,
                0::numeric                             AS total_revenue
            LIMIT 0;
            """,
        ]
        for sql in demo_views:
            try:
                await session.execute(text(sql))
            except Exception as e:
                log.warning("Demo view skipped (may already exist or conflict): %s", e)
        await session.commit()

    log.info("")
    log.info("✅ Database initialisation complete!")
    log.info("   • uqs_roles             — seeded with admin, manager, analyst, regional_manager, auditor, viewer")
    log.info("   • uqs_role_permissions  — admin + manager have full wildcard access")
    log.info("   • uqs_tenants           — multi-tenancy table created")
    log.info("")
    log.info("Next steps:")
    log.info("   1. In Supabase dashboard: set user's app_metadata = {\"role\": \"manager\"}")
    log.info("   2. Start the backend: uvicorn backend.main:app --reload")
    log.info("   3. Login with manager credentials — you will have full admin access")


if __name__ == "__main__":
    asyncio.run(run())
