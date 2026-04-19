import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def run():
    url = os.getenv('DATABASE_URL').replace('+asyncpg', '')
    conn = await asyncpg.connect(url)
    
    await conn.execute(
        """
        CREATE OR REPLACE VIEW analyst_sales_view AS
        SELECT
            'North'::text              AS region,
            'Electronics'::text        AS product_category,
            DATE_TRUNC('month', NOW()) AS month,
            142500.00::numeric         AS total_revenue,
            320::integer               AS transaction_count
        LIMIT 0
        """
    )
    print("Created analyst_sales_view")

    await conn.execute(
        """
        CREATE OR REPLACE VIEW analyst_kpi_view AS
        SELECT
            DATE_TRUNC('month', NOW()) AS month,
            0.15::numeric              AS conversion_rate,
            245.5::numeric             AS avg_order_value
        LIMIT 0
        """
    )
    print("Created analyst_kpi_view")
    
    await conn.close()

asyncio.run(run())
