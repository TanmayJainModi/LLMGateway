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
    ) -> dict:
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

                team = await conn.fetchrow(
                    "SELECT monthly_budget, monthly_spend, daily_budget, daily_spend, daily_spend_date FROM teams WHERE id=$1",
                    team_id,
                )

                from datetime import date
                today = date.today()

                if team["daily_spend_date"] != today:
                    new_daily_spend = float(estimated_cost)
                else:
                    new_daily_spend = float(team["daily_spend"] or 0) + float(estimated_cost)

                updated_team = await conn.fetchrow(
                    """
                    UPDATE teams
                    SET monthly_spend = monthly_spend + $1,
                        daily_spend = $2,
                        daily_spend_date = $3
                    WHERE id = $4
                    RETURNING monthly_spend, monthly_budget, daily_spend, daily_budget
                    """,
                    estimated_cost,
                    new_daily_spend,
                    today,
                    team_id,
                )

                return {
                    "monthly_spend": float(updated_team["monthly_spend"]),
                    "monthly_budget": float(updated_team["monthly_budget"]) if updated_team["monthly_budget"] is not None else None,
                    "daily_spend": float(updated_team["daily_spend"]),
                    "daily_budget": float(updated_team["daily_budget"]) if updated_team["daily_budget"] is not None else None,
                }