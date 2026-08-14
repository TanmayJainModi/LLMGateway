"""
connection.py

Redis connection pool management.

Mirrors the PostgreSQL connection.py pattern:
a single shared connection pool used across the gateway.
"""

import os
from redis.asyncio import Redis, ConnectionPool

_redis_pool: ConnectionPool | None = None


async def get_redis() -> Redis:
    """
    Return a Redis client backed by a shared connection pool.

    Connection parameters are read from environment variables:
    - REDIS_HOST (default: localhost)
    - REDIS_PORT (default: 6379)
    - REDIS_DB   (default: 0)
    """

    global _redis_pool

    if _redis_pool is None:
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", 6379))
        db = int(os.getenv("REDIS_DB", 0))

        _redis_pool = ConnectionPool(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
        )

    return Redis(connection_pool=_redis_pool)
