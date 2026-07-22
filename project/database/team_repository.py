"""
Database operations related to teams.
"""

from project.database.connection import get_pool


class TeamRepository:

    async def get_team_by_api_key(
        self,
        api_key: str,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            return await conn.fetchrow(
                """
                SELECT *
                FROM teams
                WHERE api_key=$1
                """,
                api_key,
            )


    async def add_usage(
        self,
        team_id: int,
        model_id: int,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
    ):
        pool = await get_pool()

        async with pool.acquire() as conn:

            async with conn.transaction():

                await conn.execute(
                    """
                    INSERT INTO usage(
                        team_id,
                        model_id,
                        input_tokens,
                        output_tokens,
                        estimated_cost
                    )
                    VALUES(
                        $1,$2,$3,$4,$5
                    )
                    """,
                    team_id,
                    model_id,
                    input_tokens,
                    output_tokens,
                    estimated_cost,
                )

                await conn.execute(
                    """
                    UPDATE teams
                    SET monthly_spend =
                        monthly_spend + $1
                    WHERE id=$2
                    """,
                    estimated_cost,
                    team_id,
                )