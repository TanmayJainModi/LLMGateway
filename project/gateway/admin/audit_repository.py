"""
audit_repository.py

Repository for rich audit log insertion and paginated/filterable query retrieval.
"""

import json
from project.database.connection import get_pool
from project.gateway.admin.auth import AdminContext


class AuditRepository:
    """
    Handles logging and querying admin audit events.
    """

    async def log_audit_event(
        self,
        admin_ctx: AdminContext,
        action: str,
        target_team_id: int | None = None,
        reason: str | None = None,
        old_values: dict | None = None,
        new_values: dict | None = None,
    ) -> int:
        """
        Record a rich audit log entry in PostgreSQL.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO audit_logs (
                    admin_user,
                    admin_email,
                    ip_address,
                    user_agent,
                    action,
                    target_team_id,
                    reason,
                    old_values,
                    new_values
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
                RETURNING id
                """,
                admin_ctx.admin_user,
                admin_ctx.admin_email,
                admin_ctx.ip_address,
                admin_ctx.user_agent,
                action,
                target_team_id,
                reason,
                json.dumps(old_values) if old_values is not None else None,
                json.dumps(new_values) if new_values is not None else None,
            )
            return row["id"]

    async def get_audit_logs(
        self,
        limit: int = 20,
        offset: int = 0,
        team_id: int | None = None,
        admin_user: str | None = None,
        action: str | None = None,
    ) -> list[dict]:
        """
        Retrieve audit logs with limit/offset pagination and optional filters.
        """
        pool = await get_pool()
        conditions = []
        params = []
        idx = 1

        if team_id is not None:
            conditions.append(f"target_team_id = ${idx}")
            params.append(team_id)
            idx += 1

        if admin_user:
            conditions.append(f"admin_user = ${idx}")
            params.append(admin_user)
            idx += 1

        if action:
            conditions.append(f"action = ${idx}")
            params.append(action)
            idx += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        params.extend([limit, offset])
        limit_idx = idx
        offset_idx = idx + 1

        query = f"""
            SELECT
                id,
                admin_user,
                admin_email,
                ip_address,
                user_agent,
                action,
                target_team_id,
                reason,
                old_values,
                new_values,
                created_at
            FROM audit_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${limit_idx} OFFSET ${offset_idx}
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]
