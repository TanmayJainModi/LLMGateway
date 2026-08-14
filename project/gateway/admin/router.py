"""
router.py

RESTful Admin API endpoints for rate limit status, hot limit updates,
spending dashboards, multi-threshold alerts, and audit history.
"""

from project.gateway.admin.auth import validate_admin_key, AdminContext, AdminUnauthorizedError
from project.gateway.admin.service import AdminService
from project.gateway.admin.audit_repository import AuditRepository
from project.database.connection import get_pool


class AdminRouter:
    """
    Handles routing and authorization for /admin/* endpoints.
    """

    def __init__(self):
        self.service = AdminService()
        self.audit_repo = AuditRepository()

    async def _authenticate(self, admin_api_key: str | None, ip_address: str = "127.0.0.1", user_agent: str = "AdminClient") -> AdminContext:
        return await validate_admin_key(admin_api_key, ip_address, user_agent)

    async def get_teams(self, admin_api_key: str | None) -> list[dict]:
        """GET /admin/teams"""
        await self._authenticate(admin_api_key)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, team_name, monthly_budget, monthly_spend, daily_budget, daily_spend FROM teams ORDER BY id")
            return [dict(r) for r in rows]

    async def get_team_status(self, admin_api_key: str | None, team_id: int) -> dict:
        """GET /admin/teams/{id}/status"""
        await self._authenticate(admin_api_key)
        return await self.service.get_team_live_status(team_id)

    async def update_team_limits(
        self,
        admin_api_key: str | None,
        team_id: int,
        new_limits: dict,
        reason: str | None = None,
        ip_address: str = "127.0.0.1",
        user_agent: str = "AdminClient",
    ) -> dict:
        """POST /admin/teams/{id}/limits"""
        admin_ctx = await self._authenticate(admin_api_key, ip_address, user_agent)
        return await self.service.update_team_limits(admin_ctx, team_id, new_limits, reason)

    async def configure_team_alerts(
        self,
        admin_api_key: str | None,
        team_id: int,
        thresholds: list[float],
        alert_email: str | None = None,
        webhook_url: str | None = None,
        reason: str | None = None,
        ip_address: str = "127.0.0.1",
        user_agent: str = "AdminClient",
    ) -> dict:
        """POST /admin/teams/{id}/alerts"""
        admin_ctx = await self._authenticate(admin_api_key, ip_address, user_agent)
        return await self.service.configure_team_alerts(admin_ctx, team_id, thresholds, alert_email, webhook_url, reason)

    async def get_dashboard(self, admin_api_key: str | None) -> dict:
        """GET /admin/dashboard"""
        await self._authenticate(admin_api_key)
        return await self.service.get_dashboard_analytics()

    async def get_audit_logs(
        self,
        admin_api_key: str | None,
        limit: int = 20,
        offset: int = 0,
        team_id: int | None = None,
        admin_user: str | None = None,
        action: str | None = None,
    ) -> list[dict]:
        """GET /admin/audit-logs (Paginated & Filterable)"""
        await self._authenticate(admin_api_key)
        return await self.audit_repo.get_audit_logs(
            limit=limit,
            offset=offset,
            team_id=team_id,
            admin_user=admin_user,
            action=action,
        )

    async def get_models(self, admin_api_key: str | None) -> list[dict]:
        """GET /admin/models"""
        await self._authenticate(admin_api_key)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id, m.model_name, p.provider_name, m.input_price_per_million_tokens, m.output_price_per_million_tokens, m.currency
                FROM models m
                JOIN providers p ON p.id = m.provider_id
                ORDER BY m.id
                """
            )
            return [dict(r) for r in rows]

    async def get_providers(self, admin_api_key: str | None) -> list[dict]:
        """GET /admin/providers"""
        await self._authenticate(admin_api_key)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, provider_name FROM providers ORDER BY id")
            return [dict(r) for r in rows]

    async def get_health_history(
        self,
        admin_api_key: str | None,
        limit: int = 20,
        offset: int = 0,
        provider_name: str | None = None,
    ) -> list[dict]:
        """GET /admin/health/history (Paginated RCA history)"""
        await self._authenticate(admin_api_key)
        pool = await get_pool()
        conditions = []
        params = []
        idx = 1

        if provider_name:
            conditions.append(f"provider_name = ${idx}")
            params.append(provider_name)
            idx += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        query = f"""
            SELECT id, provider_name, model_name, status, previous_status, reason, latency_avg_ms, latency_p99_ms, error_rate_pct, consecutive_failures, recorded_at
            FROM provider_health_history
            {where_clause}
            ORDER BY recorded_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

