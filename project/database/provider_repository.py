"""
Database operations related to providers.
"""

from project.database.connection import get_pool


class ProviderRepository:

    async def get_provider(
        self,
        provider_name: str,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            return await conn.fetchrow(
                """
                SELECT *
                FROM providers
                WHERE provider_name=$1
                """,
                provider_name,
            )