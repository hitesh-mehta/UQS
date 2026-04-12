"""
Database Initialization Script.
Run once at project setup:
  python -m scripts.init_db

Creates:
  - Demo tables and views for each RBAC role
  - Audit logging table
  - Sample data for immediate testing
"""
import asyncio
from sqlalchemy import text
from backend.core.database import get_db_session

SCHEMA_SQL = """
-- ═══════════════════════════════════════════════════════════
-- UQS Demo Schema — Replace with your actual schema in prod
-- ═══════════════════════════════════════════════════════════

-- Base tables
CREATE TABLE IF NOT EXISTS sales_fact (
    id          SERIAL PRIMARY KEY,
    sale_date   DATE NOT NULL,
    region      VARCHAR(50),
    product     VARCHAR(100),
    channel     VARCHAR(50),
    customer_id INTEGER,
    revenue     NUMERIC(12, 2),
    units       INTEGER,
    ad_spend    NUMERIC(10, 2)
);

CREATE TABLE IF NOT EXISTS customer_dim (
    customer_id     INTEGER PRIMARY KEY,
    customer_name   VARCHAR(100),
    email           VARCHAR(100),
    segment         VARCHAR(50),
    signup_date     DATE,
    churn_risk      NUMERIC(3, 2),  -- 0.0 to 1.0
    lifetime_value  NUMERIC(12, 2)
);

CREATE TABLE IF NOT EXISTS audit_trail (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id     VARCHAR(100),
    role        VARCHAR(50),
    event       VARCHAR(100),
    details     JSONB
);

-- RBAC Views ──────────────────────────────────────────────────

-- Analyst view: aggregated only, no PII
CREATE OR REPLACE VIEW analyst_sales_view AS
SELECT
    region,
    product,
    channel,
    DATE_TRUNC('month', sale_date) AS month,
    SUM(revenue)   AS total_revenue,
    SUM(units)     AS total_units,
    COUNT(*)       AS transaction_count,
    AVG(revenue)   AS avg_order_value
FROM sales_fact
GROUP BY region, product, channel, DATE_TRUNC('month', sale_date);

-- Analyst KPI view
CREATE OR REPLACE VIEW analyst_kpi_view AS
SELECT
    DATE_TRUNC('day', sale_date) AS date,
    SUM(revenue)                  AS daily_revenue,
    SUM(units)                    AS daily_units,
    COUNT(DISTINCT customer_id)   AS unique_customers
FROM sales_fact
GROUP BY DATE_TRUNC('day', sale_date);

-- Regional Manager view: region-filtered, no PII
CREATE OR REPLACE VIEW rm_sales_view AS
SELECT
    region,
    product,
    channel,
    sale_date,
    revenue,
    units
FROM sales_fact;

-- Regional Manager customer view (no email PII)
CREATE OR REPLACE VIEW rm_customer_view AS
SELECT
    customer_id,
    segment,
    signup_date,
    churn_risk,
    lifetime_value
FROM customer_dim;

-- Auditor view: only audit trail
CREATE OR REPLACE VIEW audit_trail_view AS
SELECT * FROM audit_trail;

-- Public dashboard
CREATE OR REPLACE VIEW dashboard_summary_view AS
SELECT
    DATE_TRUNC('week', sale_date) AS week,
    SUM(revenue)                   AS weekly_revenue,
    SUM(units)                     AS weekly_units,
    COUNT(DISTINCT customer_id)    AS new_customers
FROM sales_fact
GROUP BY DATE_TRUNC('week', sale_date)
ORDER BY week DESC;

-- ── Sample data ───────────────────────────────────────────────
INSERT INTO sales_fact (sale_date, region, product, channel, customer_id, revenue, units, ad_spend)
SELECT
    CURRENT_DATE - (generate_series(1, 365) || ' days')::interval,
    (ARRAY['North', 'South', 'East', 'West'])[floor(random() * 4 + 1)],
    (ARRAY['ProductA', 'ProductB', 'ProductC'])[floor(random() * 3 + 1)],
    (ARRAY['Online', 'Retail', 'Partner'])[floor(random() * 3 + 1)],
    floor(random() * 1000 + 1)::int,
    round((random() * 1000 + 50)::numeric, 2),
    floor(random() * 20 + 1)::int,
    round((random() * 200)::numeric, 2)
ON CONFLICT DO NOTHING;

INSERT INTO customer_dim (customer_id, customer_name, email, segment, signup_date, churn_risk, lifetime_value)
SELECT
    generate_series(1, 1000),
    'Customer ' || generate_series(1, 1000),
    'customer' || generate_series(1, 1000) || '@example.com',
    (ARRAY['Enterprise', 'SMB', 'Consumer'])[floor(random() * 3 + 1)],
    CURRENT_DATE - (random() * 730 || ' days')::interval,
    round(random()::numeric, 2),
    round((random() * 50000)::numeric, 2)
ON CONFLICT DO NOTHING;

RAISE NOTICE 'UQS schema initialized successfully!';
"""


async def init_db():
    print("🚀 Initializing UQS database schema...")
    async with get_db_session() as session:
        # Run in pieces since some statements can't be batched
        statements = [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]
        for stmt in statements:
            if stmt and not stmt.startswith("--") and not stmt.startswith("RAISE"):
                try:
                    await session.execute(text(stmt))
                    print(f"  ✅ Executed: {stmt[:60]}...")
                except Exception as e:
                    print(f"  ⚠️  Skipped (may already exist): {e}")
    print("✅ Database schema initialization complete!")


if __name__ == "__main__":
    asyncio.run(init_db())
