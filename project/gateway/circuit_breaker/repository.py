"""
repository.py

Repository for logging Circuit Breaker state transitions to PostgreSQL provider_health_history.
"""

from project.database.connection import get_pool


class CircuitBreakerRepository:
    """
    Handles logging of circuit state transitions for post-incident RCA.
    """

    async def log_circuit_state_change(
        self,
        provider_name: str,
        model_name: str,
        status: str,
        previous_status: str | None,
        reason: str,
        consecutive_failures: int = 0,
    ) -> None:
        """
        Record a state transition in PostgreSQL provider_health_history.
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO provider_health_history (
                        provider_name,
                        model_name,
                        status,
                        previous_status,
                        reason,
                        latency_avg_ms,
                        latency_p99_ms,
                        error_rate_pct,
                        consecutive_failures
                    )
                    VALUES ($1, $2, $3, $4, $5, 0, 0, 100.0, $6)
                    """,
                    provider_name,
                    model_name,
                    status,
                    previous_status,
                    reason,
                    consecutive_failures,
                )
        except Exception:
            # Audit logging failure is non-blocking for gateway routing
            pass
