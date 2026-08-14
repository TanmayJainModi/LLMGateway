"""
service.py

Health Service managing Passive Traffic Monitoring, Smart Idle Active Probes,
State Machine Evaluation, and PostgreSQL Compact History Logging.
"""

import time
from datetime import datetime
from project.database.connection import get_pool
from project.cache.connection import get_redis
from project.gateway.health.config import HealthConfig
from project.gateway.health.metrics import HealthMetricsTracker, HealthStatus, RollingMetrics
from project.gateway.routing.provider_factory import ProviderFactory


class HealthService:
    """
    Core service orchestrating active and passive provider health monitoring.
    """

    def __init__(self, config: HealthConfig | None = None):
        self.config = config or HealthConfig()
        self.tracker = HealthMetricsTracker()

    @staticmethod
    def _status_key(provider: str, model: str) -> str:
        return f"health:status:{provider}:{model}"

    @staticmethod
    def _last_log_key(provider: str, model: str) -> str:
        return f"health:last_log:{provider}:{model}"

    async def get_current_status(self, provider: str, model: str) -> HealthStatus:
        """Fetch live health status from Redis (defaults to HEALTHY)."""
        try:
            redis = await get_redis()
            val = await redis.get(self._status_key(provider, model))
            if val:
                return HealthStatus(val)
        except Exception:
            pass
        return HealthStatus.HEALTHY

    async def record_request_health(
        self,
        provider_name: str,
        model_name: str,
        latency_ms: int,
        is_error: bool,
        status_code: int = 200,
    ) -> HealthStatus:
        """
        Passive Monitoring: Recorded on EVERY real user request.
        Updates 5-minute rolling window in Redis and re-evaluates status.
        """
        try:
            redis = await get_redis()
            await self.tracker.record_metric(
                redis=redis,
                provider=provider_name,
                model=model_name,
                latency_ms=latency_ms,
                is_error=is_error,
                status_code=status_code,
            )

            metrics = await self.tracker.compute_rolling_metrics(
                redis=redis,
                provider=provider_name,
                model=model_name,
                config=self.config,
            )

            return await self._evaluate_and_log_status(provider_name, model_name, metrics)
        except Exception:
            return HealthStatus.HEALTHY

    async def check_idle_and_probe_all(self) -> dict[str, HealthStatus]:
        """
        Active Probing: Executed by background loop every 30 seconds.
        For each active provider-model:
            - Checks last_traffic_timestamp in Redis.
            - If traffic occurred within idle_threshold_seconds (e.g. 3 mins) -> SKIP PROBE!
            - If idle -> Executes lightweight provider.health_check(), measures latency, updates metrics.
        """
        results = {}
        pool = await get_pool()
        async with pool.acquire() as conn:
            models = await conn.fetch(
                """
                SELECT m.model_name, p.provider_name
                FROM models m
                JOIN providers p ON p.id = m.provider_id
                ORDER BY p.id
                """
            )

        now = time.time()
        redis = await get_redis()

        for row in models:
            provider_name = row["provider_name"]
            model_name = row["model_name"]

            metrics = await self.tracker.compute_rolling_metrics(
                redis=redis,
                provider=provider_name,
                model=model_name,
                config=self.config,
            )

            # Check if received real traffic recently
            is_idle = (now - metrics.last_traffic_timestamp) >= self.config.idle_threshold_seconds

            if not is_idle and metrics.total_samples > 0:
                # Real traffic is fresh! Skip active probe to save cost.
                status = await self._evaluate_and_log_status(provider_name, model_name, metrics)
                results[f"{provider_name}:{model_name}"] = status
                continue

            # Provider is IDLE -> Execute lightweight active health check
            start = time.time()
            is_success = False
            try:
                provider = ProviderFactory.create(provider_name)
                is_success = await provider.health_check()
                await provider.close()
            except Exception:
                is_success = False

            elapsed_ms = int((time.time() - start) * 1000)
            is_error = not is_success

            await self.tracker.record_metric(
                redis=redis,
                provider=provider_name,
                model=model_name,
                latency_ms=elapsed_ms,
                is_error=is_error,
                status_code=200 if is_success else 500,
            )

            updated_metrics = await self.tracker.compute_rolling_metrics(
                redis=redis,
                provider=provider_name,
                model=model_name,
                config=self.config,
            )

            status = await self._evaluate_and_log_status(provider_name, model_name, updated_metrics)
            results[f"{provider_name}:{model_name}"] = status

        return results

    async def _evaluate_and_log_status(
        self,
        provider: str,
        model: str,
        metrics: RollingMetrics,
    ) -> HealthStatus:
        redis = await get_redis()
        current_status = await self.get_current_status(provider, model)
        next_status, reason = self.tracker.evaluate_next_status(current_status, metrics, self.config)

        # Update current status in Redis
        await redis.set(self._status_key(provider, model), next_status.value)

        # Determine if we should insert a log row into PostgreSQL:
        # 1. Status changed (e.g. HEALTHY -> DEGRADED)
        # 2. OR 10 minutes (600s) elapsed since last DB insert
        last_log_ts = await redis.get(self._last_log_key(provider, model))
        now = time.time()
        time_since_last_log = (now - float(last_log_ts)) if last_log_ts else 999999.0

        status_changed = current_status != next_status
        should_log = status_changed or (time_since_last_log >= 600.0)

        if should_log:
            await redis.set(self._last_log_key(provider, model), str(now))
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
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    provider,
                    model,
                    next_status.value,
                    current_status.value if status_changed else None,
                    reason,
                    metrics.avg_latency_ms,
                    metrics.p99_latency_ms,
                    metrics.error_rate_pct,
                    metrics.consecutive_failures,
                )

        return next_status
