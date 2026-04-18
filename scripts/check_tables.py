import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def run():
    url = os.getenv('DATABASE_URL').replace('+asyncpg', '')
    conn = await asyncpg.connect(url)
    res = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = [r['table_name'] for r in res]
    print("TABLES IN PUBLIC SCHEMA:", tables)
    if 'uqs_role_permissions' in tables:
        print("YES! uqs_role_permissions exists.")
    else:
        print("NO! uqs_role_permissions MISSING.")
    await conn.close()

asyncio.run(run())
