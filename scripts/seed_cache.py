"""
Seed initial report cache with dummy reports for testing.
Run: python -m scripts.seed_cache
"""
import asyncio
from backend.cache.cron_generator import generate_report

async def main():
    print("Seeding report cache...")
    for granularity in ["daily", "weekly", "monthly"]:
        try:
            report = await generate_report(granularity)
            print(f"  OK {granularity}: {report.period}")
        except Exception as e:
            print(f"  FAIL  {granularity} failed: {e}")
    print("Cache seeding complete!")

if __name__ == "__main__":
    asyncio.run(main())
