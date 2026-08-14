"""
metrics.py

Rolling 5-minute time window metrics in Redis and Health Status State Machine evaluation.
"""

import json
import time
import math
from enum import Enum
from dataclasses import dataclass
from project.gateway.health.config import HealthConfig


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    RECOVERING = "RECOVERING"


@dataclass
class RollingMetrics:
    total_samples: int
    error_count: int
    error_rate_pct: float
    avg_latency_ms: int
    p99_latency_ms: int
    consecutive_failures: int
    last_traffic_timestamp: float


class HealthMetricsTracker:
    """
    Tracks passive & active request metrics in Redis 5-minute rolling time windows.
    """

    @staticmethod
    def _metric_key(provider: str, model: str) -> str:
        return f"health:metrics:{provider}:{model}"

    @classmethod
    async def record_metric(
        cls,
        redis,
        provider: str,
        model: str,
        latency_ms: int,
        is_error: bool,
        status_code: int = 200,
    ) -> None:
        key = cls._metric_key(provider, model)
        now = time.time()
        payload = json.dumps({
            "latency": latency_ms,
            "is_error": 1 if is_error else 0,
            "status": status_code,
            "ts": now,
        })
        await redis.zadd(key, {payload: now})
        await redis.expire(key, 3600)

    @classmethod
    async def compute_rolling_metrics(
        cls,
        redis,
        provider: str,
        model: str,
        config: HealthConfig,
    ) -> RollingMetrics:
        key = cls._metric_key(provider, model)
        now = time.time()
        min_ts = now - config.window_seconds

        # Prune metrics older than 5 minutes
        await redis.zremrangebyscore(key, "-inf", min_ts)

        # Retrieve remaining 5-minute metrics
        raw_items = await redis.zrange(key, 0, -1)

        if not raw_items:
            return RollingMetrics(
                total_samples=0,
                error_count=0,
                error_rate_pct=0.0,
                avg_latency_ms=0,
                p99_latency_ms=0,
                consecutive_failures=0,
                last_traffic_timestamp=0.0,
            )

        items = [json.loads(item) for item in raw_items]
        total_samples = len(items)
        errors = [item for item in items if item["is_error"] == 1]
        error_count = len(errors)
        error_rate_pct = round((error_count / total_samples) * 100.0, 2)

        latencies = sorted([item["latency"] for item in items])
        avg_latency_ms = int(sum(latencies) / len(latencies))

        # Compute exact P99 index
        p99_idx = max(0, int(math.ceil(0.99 * len(latencies))) - 1)
        p99_latency_ms = latencies[p99_idx]

        # Calculate recent consecutive failures (from end of list backwards)
        consecutive_failures = 0
        for item in reversed(items):
            if item["is_error"] == 1:
                consecutive_failures += 1
            else:
                break

        last_traffic_timestamp = items[-1]["ts"]

        return RollingMetrics(
            total_samples=total_samples,
            error_count=error_count,
            error_rate_pct=error_rate_pct,
            avg_latency_ms=avg_latency_ms,
            p99_latency_ms=p99_latency_ms,
            consecutive_failures=consecutive_failures,
            last_traffic_timestamp=last_traffic_timestamp,
        )

    @classmethod
    def evaluate_next_status(
        cls,
        current_status: HealthStatus,
        metrics: RollingMetrics,
        config: HealthConfig,
    ) -> tuple[HealthStatus, str]:
        """
        Evaluate health status state machine transitions with reason strings.

        Returns
        -------
        tuple[HealthStatus, str]
            (next_status, transition_reason)
        """
        if metrics.total_samples == 0:
            return HealthStatus.HEALTHY, "No metrics recorded (default HEALTHY)"

        err_pct = metrics.error_rate_pct
        p99 = metrics.p99_latency_ms
        consec_fails = metrics.consecutive_failures

        # Down check
        if err_pct >= (config.down_error_rate * 100) or consec_fails >= 3:
            reason = f"Error rate {err_pct:.1f}% >= 50% (or {consec_fails} consecutive failures)"
            return HealthStatus.DOWN, reason

        # State transition handling
        if current_status == HealthStatus.DOWN:
            if consec_fails == 0:
                return HealthStatus.RECOVERING, "Probes succeeding after DOWN status"
            return HealthStatus.DOWN, f"Remaining DOWN ({consec_fails} failures)"

        if current_status == HealthStatus.RECOVERING:
            if err_pct < (config.degraded_error_rate * 100) and p99 <= config.degraded_latency_ms:
                return HealthStatus.HEALTHY, f"Normalized: error rate {err_pct:.1f}% < 5% and P99 {p99}ms <= 2500ms"
            return HealthStatus.RECOVERING, f"Still recovering: error rate {err_pct:.1f}%, P99 {p99}ms"

        # Degraded check
        if err_pct >= (config.degraded_error_rate * 100) or p99 > config.degraded_latency_ms:
            reasons = []
            if err_pct >= (config.degraded_error_rate * 100):
                reasons.append(f"Error rate {err_pct:.1f}% >= 5%")
            if p99 > config.degraded_latency_ms:
                reasons.append(f"P99 latency {p99}ms > {config.degraded_latency_ms}ms")
            return HealthStatus.DEGRADED, " | ".join(reasons)

        return HealthStatus.HEALTHY, f"Healthy: error rate {err_pct:.1f}%, P99 {p99}ms"
