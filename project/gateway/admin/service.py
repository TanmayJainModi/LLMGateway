"""
service.py

Admin Service orchestrating live team status reports, dynamic limit updates,
spending dashboards, and threshold alert configurations.
"""

from datetime import date
from project.database.connection import get_pool
from project.cache.connection import get_redis
from project.gateway.admin.auth import AdminContext
from project.gateway.admin.audit_repository import AuditRepository
from project.gateway.ratelimit.priority import PriorityLevel


class AdminService:
    """
    Core administrative service logic.
    """

    def __init__(self):
        self.audit_repo = AuditRepository()

    async def get_team_live_status(self, team_id: int) -> dict:
        """
        Build a comprehensive live team status report combining:
        1. PostgreSQL configured limits & budgets
        2. Redis live remaining RPM, TPM, and RPD capacity
        3. Redis live Priority Queue lengths (HIGH, MEDIUM, LOW)
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            team = await conn.fetchrow(
                """
                SELECT
                    t.id, t.team_name, t.monthly_budget, t.monthly_spend,
                    t.daily_budget, t.daily_spend, t.daily_spend_date,
                    tma.id as tma_id, tma.requests_per_minute, tma.tokens_per_minute, tma.requests_per_day
                FROM teams t
                LEFT JOIN team_model_access tma ON tma.team_id = t.id
                WHERE t.id = $1
                """,
                team_id,
            )

            if not team:
                raise ValueError(f"Team {team_id} not found.")

        tma_id = team["tma_id"] or team_id
        rpm_limit = team["requests_per_minute"] or 60
        tpm_limit = team["tokens_per_minute"] or 100000
        rpd_limit = team["requests_per_day"] or 10000

        # Query Redis for live state
        rpm_remaining = rpm_limit
        tpm_remaining = tpm_limit
        rpd_remaining = rpd_limit
        high_queue_len = 0
        med_queue_len = 0
        low_queue_len = 0

        try:
            redis = await get_redis()
            rpm_data = await redis.hmget(f"ratelimit:tma:{tma_id}:rpm", "tokens")
            if rpm_data and rpm_data[0] is not None:
                rpm_remaining = int(float(rpm_data[0]))

            tpm_data = await redis.hmget(f"ratelimit:tma:{tma_id}:tpm", "tokens")
            if tpm_data and tpm_data[0] is not None:
                tpm_remaining = int(float(tpm_data[0]))

            today = date.today().isoformat()
            rpd_data = await redis.get(f"ratelimit:tma:{tma_id}:rpd:{today}")
            if rpd_data is not None:
                rpd_count = int(rpd_data)
                rpd_remaining = max(0, rpd_limit - rpd_count)

            high_queue_len = await redis.llen(f"ratelimit:queue:{tma_id}:{PriorityLevel.HIGH.value}")
            med_queue_len = await redis.llen(f"ratelimit:queue:{tma_id}:{PriorityLevel.MEDIUM.value}")
            low_queue_len = await redis.llen(f"ratelimit:queue:{tma_id}:{PriorityLevel.LOW.value}")
        except Exception:
            pass

        return {
            "team_id": team["id"],
            "team_name": team["team_name"],
            "configured": {
                "requests_per_minute": rpm_limit,
                "tokens_per_minute": tpm_limit,
                "requests_per_day": rpd_limit,
                "monthly_budget": float(team["monthly_budget"]) if team["monthly_budget"] is not None else None,
                "daily_budget": float(team["daily_budget"]) if team["daily_budget"] is not None else None,
            },
            "live": {
                "rpm_remaining": rpm_remaining,
                "tpm_remaining": tpm_remaining,
                "rpd_remaining": rpd_remaining,
                "monthly_spend": float(team["monthly_spend"] or 0),
                "daily_spend": float(team["daily_spend"] or 0),
            },
            "queues": {
                "high": high_queue_len,
                "medium": med_queue_len,
                "low": low_queue_len,
            },
        }

    async def update_team_limits(
        self,
        admin_ctx: AdminContext,
        team_id: int,
        new_limits: dict,
        reason: str | None = None,
    ) -> dict:
        """
        Dynamically update RPM, TPM, RPD, or budgets for a team in PostgreSQL.
        No Redis reload required — next gateway request reads updated limits from DB.
        Writes rich record to audit_logs.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                old_team = await conn.fetchrow(
                    """
                    SELECT t.monthly_budget, t.daily_budget, tma.requests_per_minute, tma.tokens_per_minute, tma.requests_per_day
                    FROM teams t
                    LEFT JOIN team_model_access tma ON tma.team_id = t.id
                    WHERE t.id = $1
                    """,
                    team_id,
                )

                if not old_team:
                    raise ValueError(f"Team {team_id} not found.")

                old_values = {
                    "monthly_budget": float(old_team["monthly_budget"]) if old_team["monthly_budget"] is not None else None,
                    "daily_budget": float(old_team["daily_budget"]) if old_team["daily_budget"] is not None else None,
                    "requests_per_minute": old_team["requests_per_minute"],
                    "tokens_per_minute": old_team["tokens_per_minute"],
                    "requests_per_day": old_team["requests_per_day"],
                }

                if "monthly_budget" in new_limits or "daily_budget" in new_limits:
                    await conn.execute(
                        """
                        UPDATE teams
                        SET monthly_budget = COALESCE($1, monthly_budget),
                            daily_budget = COALESCE($2, daily_budget)
                        WHERE id = $3
                        """,
                        new_limits.get("monthly_budget"),
                        new_limits.get("daily_budget"),
                        team_id,
                    )

                if any(k in new_limits for k in ("requests_per_minute", "tokens_per_minute", "requests_per_day")):
                    await conn.execute(
                        """
                        UPDATE team_model_access
                        SET requests_per_minute = COALESCE($1, requests_per_minute),
                            tokens_per_minute = COALESCE($2, tokens_per_minute),
                            requests_per_day = COALESCE($3, requests_per_day)
                        WHERE team_id = $4
                        """,
                        new_limits.get("requests_per_minute"),
                        new_limits.get("tokens_per_minute"),
                        new_limits.get("requests_per_day"),
                        team_id,
                    )

                await self.audit_repo.log_audit_event(
                    admin_ctx=admin_ctx,
                    action="update_team_limits",
                    target_team_id=team_id,
                    reason=reason,
                    old_values=old_values,
                    new_values=new_limits,
                )

        return await self.get_team_live_status(team_id)

    async def configure_team_alerts(
        self,
        admin_ctx: AdminContext,
        team_id: int,
        thresholds: list[float],
        alert_email: str | None = None,
        webhook_url: str | None = None,
        reason: str | None = None,
    ) -> dict:
        """
        Configure multi-threshold alert rules (e.g. [80.0, 90.0, 95.0, 100.0]).
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                old_alert = await conn.fetchrow(
                    "SELECT thresholds, alert_email, webhook_url FROM team_alerts WHERE team_id = $1",
                    team_id,
                )
                old_values = dict(old_alert) if old_alert else {}

                new_values = {
                    "thresholds": thresholds,
                    "alert_email": alert_email,
                    "webhook_url": webhook_url,
                }

                await conn.execute(
                    """
                    INSERT INTO team_alerts (team_id, thresholds, alert_email, webhook_url)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (team_id) DO UPDATE
                    SET thresholds = EXCLUDED.thresholds,
                        alert_email = EXCLUDED.alert_email,
                        webhook_url = EXCLUDED.webhook_url
                    """,
                    team_id,
                    thresholds,
                    alert_email,
                    webhook_url,
                )

                await self.audit_repo.log_audit_event(
                    admin_ctx=admin_ctx,
                    action="configure_team_alerts",
                    target_team_id=team_id,
                    reason=reason,
                    old_values=old_values,
                    new_values=new_values,
                )

                return new_values

    async def get_dashboard_analytics(self) -> dict:
        """
        Returns high-level summary cards and spend breakdown using cached team spend metrics.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            teams = await conn.fetch(
                "SELECT id, team_name, monthly_budget, monthly_spend, daily_budget, daily_spend FROM teams ORDER BY id"
            )
            model_spend = await conn.fetch(
                """
                SELECT m.model_name, SUM(u.estimated_cost) as total_cost, SUM(u.input_tokens) as input_tokens, SUM(u.output_tokens) as output_tokens
                FROM usage u
                JOIN models m ON m.id = u.model_id
                GROUP BY m.model_name
                ORDER BY total_cost DESC
                """
            )

            total_gateway_spend = sum(float(t["monthly_spend"] or 0) for t in teams)

            return {
                "total_gateway_spend": round(total_gateway_spend, 4),
                "total_teams": len(teams),
                "teams_spend": [
                    {
                        "team_id": t["id"],
                        "team_name": t["team_name"],
                        "monthly_spend": float(t["monthly_spend"] or 0),
                        "monthly_budget": float(t["monthly_budget"]) if t["monthly_budget"] is not None else None,
                        "daily_spend": float(t["daily_spend"] or 0),
                        "daily_budget": float(t["daily_budget"]) if t["daily_budget"] is not None else None,
                    }
                    for t in teams
                ],
                "models_spend": [
                    {
                        "model_name": m["model_name"],
                        "total_cost": float(m["total_cost"] or 0),
                        "input_tokens": int(m["input_tokens"] or 0),
                        "output_tokens": int(m["output_tokens"] or 0),
                    }
                    for m in model_spend
                ],
            }
