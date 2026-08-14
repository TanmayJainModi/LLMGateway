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
        ssl=False,
    )

    await conn.execute(
        """
        ALTER TABLE team_model_access
            ADD COLUMN IF NOT EXISTS tokens_per_minute INTEGER NOT NULL DEFAULT 100000;
        """
    )

    # Set specific TPM values for each team
    # Founders Team (team_id=1): 500k TPM
    await conn.execute(
        "UPDATE team_model_access SET tokens_per_minute = 500000 WHERE team_id = 1"
    )
    # Tech Team (team_id=2): 200k TPM
    await conn.execute(
        "UPDATE team_model_access SET tokens_per_minute = 200000 WHERE team_id = 2"
    )
    # Sales, Marketing, Creative Teams: 100k TPM (already default)

    print("Migration completed: tokens_per_minute column added and seeded.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
