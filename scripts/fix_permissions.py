"""
Fix RBAC permissions to point to REAL views that exist in the database.

The init_db.py seeded permissions pointing to skeleton views that didn't exist.
This script updates them to the REAL views/tables in the Supabase DB.
"""
import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()


# The REAL views/tables that exist in the Supabase database:
# locations, customers, order_items, products, purchases, suppliers,
# purchase_items, loyalty_transactions, employees, orders, inventory,
# daily_sales_view, monthly_revenue_view, top_products_view,
# low_inventory_view, employee_performance_view

CORRECT_PERMISSIONS = [
    # admin gets wildcard — full public schema
    ("admin", "*"),
    # analyst — all analytical views
    ("analyst", "daily_sales_view"),
    ("analyst", "monthly_revenue_view"),
    ("analyst", "top_products_view"),
    ("analyst", "low_inventory_view"),
    ("analyst", "employee_performance_view"),
    # regional_manager — sales and inventory
    ("regional_manager", "daily_sales_view"),
    ("regional_manager", "monthly_revenue_view"),
    ("regional_manager", "low_inventory_view"),
    # auditor — can see orders and employee performance
    ("auditor", "daily_sales_view"),
    ("auditor", "employee_performance_view"),
    # viewer — summary views only
    ("viewer", "daily_sales_view"),
    ("viewer", "monthly_revenue_view"),
    ("viewer", "top_products_view"),
]


async def run():
    url = os.getenv("DATABASE_URL")
    conn = await asyncpg.connect(url)

    # 1. Clear old (broken) permissions
    await conn.execute("DELETE FROM uqs_role_permissions")
    print("Cleared old permissions")

    # 2. Insert correct permissions pointing to REAL views
    for role_name, view_name in CORRECT_PERMISSIONS:
        await conn.execute(
            "INSERT INTO uqs_role_permissions (role_name, view_name) VALUES ($1, $2) ON CONFLICT (role_name, view_name) DO NOTHING",
            role_name,
            view_name,
        )
        print(f"  {role_name} -> {view_name}")

    # 3. Verify
    rows = await conn.fetch("SELECT role_name, view_name FROM uqs_role_permissions ORDER BY role_name, view_name")
    print(f"\nTotal permissions: {len(rows)}")
    for r in rows:
        print(f"  {r['role_name']:20s} -> {r['view_name']}")

    # 4. Check all referenced views actually exist
    tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    real_tables = {r["table_name"] for r in tables}
    print(f"\nReal tables/views in DB: {sorted(real_tables)}")

    for role_name, view_name in CORRECT_PERMISSIONS:
        if view_name != "*" and view_name not in real_tables:
            print(f"  WARNING: {view_name} does NOT exist!")

    # 5. Schema check for analyst role specifically
    print("\n--- Schema check for 'analyst' role ---")
    analyst_views = await conn.fetch(
        "SELECT view_name FROM uqs_role_permissions WHERE role_name='analyst'"
    )
    for row in analyst_views:
        vname = row["view_name"]
        cols = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=$1",
            vname,
        )
        if cols:
            print(f"  ✅ {vname}: {len(cols)} columns")
        else:
            print(f"  ❌ {vname}: NO COLUMNS FOUND")

    await conn.close()
    print("\n✅ RBAC permissions fixed!")


asyncio.run(run())
