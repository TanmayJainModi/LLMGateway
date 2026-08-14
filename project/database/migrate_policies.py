import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def migrate():
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT")),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DB"),
    )

    await conn.execute(
        """
        ALTER TABLE teams ADD COLUMN IF NOT EXISTS default_system_prompt TEXT;
        ALTER TABLE teams ADD COLUMN IF NOT EXISTS compliance_disclaimer TEXT;
        ALTER TABLE teams ADD COLUMN IF NOT EXISTS blocked_keywords TEXT[];
        ALTER TABLE teams ADD COLUMN IF NOT EXISTS enable_request_filter BOOLEAN DEFAULT TRUE;
        """
    )

    print("PostgreSQL migration completed successfully! Policy columns added to 'teams' table.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
