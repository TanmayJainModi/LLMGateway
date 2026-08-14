"""
config.py

Configuration parameters for Distributed Provider Circuit Breakers.
"""

from dataclasses import dataclass


@dataclass
class CircuitBreakerConfig:
    failure_threshold_n: int = 5      # Trip circuit after 5 request failures
    window_seconds_m: int = 60        # 60-second rolling failure window
    cooldown_seconds: int = 30        # 30-second cooldown period in OPEN state
    canary_timeout_sec: float = 10.0  # Probe lock expiration for HALF_OPEN state
