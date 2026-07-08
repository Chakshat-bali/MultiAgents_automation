import asyncio
import os
from sqlalchemy import create_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv

# Load env from parent dir since we are in backend/scratch
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")

async def check_ea():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not found in .env")
        return

    # Create engine (using sync driver for a quick check or async as needed)
    # The URL in .env is asyncpg, so we use create_async_engine
    engine = create_async_engine(DATABASE_URL)
    
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with async_session() as session:
        print("--- Searching for EA Sports Company ---")
        query = text("SELECT id, name, description FROM companies WHERE name ILIKE :name OR name ILIKE :alt")
        result = await session.execute(query, {"name": "%EA sports%", "alt": "%Electronic Arts%"})
        company = result.fetchone()
        print("Company Found:", company)
        
        if company:
            print("\n--- Searching for Reports for this Company ---")
            query_reports = text("SELECT created_at, signal_level FROM intel_reports WHERE company_id = :cid ORDER BY created_at DESC")
            result_reports = await session.execute(query_reports, {"cid": company[0]})
            reports = result_reports.fetchall()
            print(f"Total Reports: {len(reports)}")
            for r in reports:
                print(f"- Date: {r[0]}, Signal: {r[1]}")
        else:
            print("\nNo EA Sports company found in tracked list.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_ea())
