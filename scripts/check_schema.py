import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def run():
    url = os.getenv('DATABASE_URL').replace('+asyncpg', '')
    conn = await asyncpg.connect(url)
    res = await conn.fetch("SELECT view_name FROM uqs_role_permissions WHERE role_name = 'analyst' ORDER BY view_name")
    views = [r['view_name'] for r in res]
    print('Analyst views registered in RBAC:', views)
    
    if views:
        res2 = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        real_tables = [r['table_name'] for r in res2]
        
        has_at_least_one_valid_schema = False
        
        for v in views:
            if v not in real_tables:
                print(f"WARNING: The view {v} is registered in uqs_role_permissions but DO NOT exist in the database! It's a dangling permission.")
            else:
                res3 = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=$1", v)
                if res3:
                     print(f"✅ View '{v}' SCHEMA LOADED:", [dict(r) for r in res3])
                     has_at_least_one_valid_schema = True
                else:
                     print(f"❌ View '{v}' SCHEMA IS EMPTY")
                     
        if not has_at_least_one_valid_schema:
             print("CRITICAL LOGIC FAILURE: The system WILL send an empty schema to Gemini, causing 'irrelevant data' fallback.")
    else:
         print("CRITICAL LOGIC FAILURE: Analyst role has NO views registered in uqs_role_permissions.")
                 
    await conn.close()

asyncio.run(run())
