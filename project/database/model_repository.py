"""
Database operations related to models.
"""

from project.database import connection
from project.database.connection import get_pool


class ModelRepository:

    async def get_model(
        self,
        provider_name: str,
        model_name: str,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            return await conn.fetchrow(
                """
                SELECT
                    m.*,
                    p.provider_name
                FROM models m
                JOIN providers p
                    ON p.id = m.provider_id
                WHERE
                    p.provider_name=$1
                    AND m.model_name=$2
                """,
                provider_name,
                model_name,
            )

    async def get_team_access(
        self,
        team_id: int,
        model_id: int,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            return await conn.fetchrow(
                """
                SELECT *
                FROM team_model_access
                WHERE
                    team_id=$1
                    AND model_id=$2
                    AND enabled=TRUE
                """,
                team_id,
                model_id,
            )

    async def get_allowed_models(
        self,
        team_id: int,
    ):
        """
        Returns every model the team is allowed to use.
        """

        query = """
            SELECT
                m.id,
                m.model_name,
                p.provider_name
            FROM team_model_access tma
            JOIN models m
                ON tma.model_id = m.id
            JOIN providers p
                ON m.provider_id = p.id
            WHERE
                tma.team_id = $1
                AND tma.enabled = TRUE
            ORDER BY
                p.id,
                m.id;
        """

        pool = await get_pool()

        async with pool.acquire() as conn:
            return await conn.fetch(
                query,
                team_id,
            )