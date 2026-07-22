"""
Database operations related to usage tracking.
"""

from project.database.connection import get_pool


class UsageRepository:

    async def insert_usage(
        self,
        team_id: int,
        model_id: int,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            await conn.execute(
                """
                INSERT INTO usage
                (
                    team_id,
                    model_id,
                    input_tokens,
                    output_tokens,
                    estimated_cost
                )
                VALUES
                ($1,$2,$3,$4,$5)
                """,
                team_id,
                model_id,
                input_tokens,
                output_tokens,
                estimated_cost,
            )

    async def update_monthly_spend(
        self,
        team_id: int,
        cost: float,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            await conn.execute(
                """
                UPDATE teams
                SET monthly_spend =
                    monthly_spend + $1
                WHERE id=$2
                """,
                cost,
                team_id,
            )

    async def get_requests_today(
        self,
        team_id: int,
        model_id: int,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            return await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM usage
                WHERE
                    team_id=$1
                    AND model_id=$2
                    AND created_at::date = CURRENT_DATE
                """,
                team_id,
                model_id,
            )

    async def get_requests_last_minute(
        self,
        team_id: int,
        model_id: int,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            return await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM usage
                WHERE
                    team_id=$1
                    AND model_id=$2
                    AND created_at >
                        NOW() - INTERVAL '1 minute'
                """,
                team_id,
                model_id,
            )