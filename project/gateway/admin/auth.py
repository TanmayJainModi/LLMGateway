"""
auth.py

Admin authentication and context verification using X-Admin-API-Key.
"""

from dataclasses import dataclass
from project.database.connection import get_pool


class AdminUnauthorizedError(Exception):
    """Raised when admin API key is missing or invalid."""
    pass


@dataclass
class AdminContext:
    admin_user: str
    admin_email: str
    role: str
    ip_address: str = "127.0.0.1"
    user_agent: str = "AdminClient"


async def validate_admin_key(
    api_key: str | None,
    ip_address: str = "127.0.0.1",
    user_agent: str = "AdminClient",
) -> AdminContext:
    """
    Validate the X-Admin-API-Key against the admin_users table in PostgreSQL.

    Returns
    -------
    AdminContext
        The authenticated admin's user context.

    Raises
    ------
    AdminUnauthorizedError
        If api_key is missing or not found in admin_users.
    """
    if not api_key:
        raise AdminUnauthorizedError("Missing X-Admin-API-Key header.")

    pool = await get_pool()
    async with pool.acquire() as conn:
        admin = await conn.fetchrow(
            """
            SELECT username, email, role
            FROM admin_users
            WHERE admin_api_key = $1
            """,
            api_key,
        )

        if not admin:
            raise AdminUnauthorizedError("Invalid X-Admin-API-Key.")

        return AdminContext(
            admin_user=admin["username"],
            admin_email=admin["email"],
            role=admin["role"],
            ip_address=ip_address,
            user_agent=user_agent,
        )
