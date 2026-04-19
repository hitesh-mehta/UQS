import asyncio
from backend.core.database import get_db_session
from sqlalchemy import text

async def run():
    async with get_db_session() as session:
        try:
            await session.execute(text("ALTER TABLE uqs_tenants ADD COLUMN admin_role TEXT DEFAULT 'admin';"))
            await session.commit()
            print("Added admin_role column")
        except Exception as e:
            print(f"Error (maybe column exists?): {e}")

asyncio.run(run())
