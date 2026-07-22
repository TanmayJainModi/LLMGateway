"""
Database connection.

Creates a reusable PostgreSQL connection pool for the gateway.
"""

import os

from dotenv import load_dotenv
import asyncpg

load_dotenv()

_pool = None


async def get_pool():
    global _pool

    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST"),
            port=int(os.getenv("POSTGRES_PORT")),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            database=os.getenv("POSTGRES_DB"),
        )

    return _pool