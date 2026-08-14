"""
config.py

Health monitoring configuration parameters.
"""

from dataclasses import dataclass


@dataclass
class HealthConfig:
    window_seconds: int = 300            # 5-minute rolling window
    probe_interval_seconds: int = 30     # Active probe check cycle (30s)
    idle_threshold_seconds: int = 180    # Active probe ONLY if idle for 3+ minutes
    degraded_latency_ms: int = 2500      # P99 latency threshold for DEGRADED (2.5s)
    degraded_error_rate: float = 0.05    # 5% error rate threshold for DEGRADED
    down_error_rate: float = 0.50        # 50% error rate threshold for DOWN
    recovery_consecutive_success: int = 3 # Successes required to transition DOWN -> RECOVERING -> HEALTHY
