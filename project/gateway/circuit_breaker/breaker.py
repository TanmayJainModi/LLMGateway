"""
breaker.py

Distributed Provider Circuit Breaker backed by Redis.
Manages CLOSED, OPEN, and HALF_OPEN state transitions with atomic canary probe locking.
"""

import time
from enum import Enum
from project.cache.connection import get_redis
from project.gateway.circuit_breaker.config import CircuitBreakerConfig
from project.gateway.circuit_breaker.repository import CircuitBreakerRepository


from project.gateway.telemetry.tracer import gateway_tracer
import project.gateway.telemetry.attributes as attrs


from project.gateway.telemetry.metrics import gateway_metrics


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Distributed Provider Circuit Breaker.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None):
        self.config = config or CircuitBreakerConfig()
        self.repository = CircuitBreakerRepository()

    @staticmethod
    def _state_key(provider: str, model: str) -> str:
        return f"circuit:state:{provider}:{model}"

    @staticmethod
    def _failures_key(provider: str, model: str) -> str:
        return f"circuit:failures:{provider}:{model}"

    @staticmethod
    def _cooldown_key(provider: str, model: str) -> str:
        return f"circuit:cooldown:{provider}:{model}"

    @staticmethod
    def _probe_lock_key(provider: str, model: str) -> str:
        return f"circuit:probe_lock:{provider}:{model}"

    async def get_state(self, provider: str, model: str) -> CircuitState:
        """
        Fetch current circuit state from Redis.
        Auto-transitions OPEN -> HALF_OPEN when cooldown timer expires.
        """
        try:
            redis = await get_redis()
            state_val = await redis.get(self._state_key(provider, model))
            if not state_val:
                return CircuitState.CLOSED

            curr_state = CircuitState(state_val)
            if curr_state == CircuitState.OPEN:
                cooldown = await redis.get(self._cooldown_key(provider, model))
                if not cooldown:
                    # Cooldown expired! Transition OPEN -> HALF_OPEN
                    await redis.set(self._state_key(provider, model), CircuitState.HALF_OPEN.value)
                    gateway_metrics.record_circuit_change(provider, model, CircuitState.OPEN.value, CircuitState.HALF_OPEN.value)
                    await self.repository.log_circuit_state_change(
                        provider_name=provider,
                        model_name=model,
                        status=CircuitState.HALF_OPEN.value,
                        previous_status=CircuitState.OPEN.value,
                        reason=f"Cooldown period of {self.config.cooldown_seconds}s expired; entering HALF_OPEN state.",
                    )
                    return CircuitState.HALF_OPEN

            return curr_state
        except Exception:
            return CircuitState.CLOSED

    async def allow_request(self, provider: str, model: str) -> tuple[bool, bool]:
        """
        Determines whether a request to provider:model is allowed.
        """
        with gateway_tracer.start_span("circuit_breaker_check") as span:
            state = await self.get_state(provider, model)
            allowed, is_canary = True, False

            if state == CircuitState.CLOSED:
                allowed, is_canary = True, False
            elif state == CircuitState.OPEN:
                allowed, is_canary = False, False
            elif state == CircuitState.HALF_OPEN:
                try:
                    redis = await get_redis()
                    acquired = await redis.set(
                        self._probe_lock_key(provider, model),
                        "1",
                        nx=True,
                        ex=int(self.config.canary_timeout_sec),
                    )
                    if acquired:
                        allowed, is_canary = True, True
                    else:
                        allowed, is_canary = False, False
                except Exception:
                    allowed, is_canary = False, False

            gateway_tracer.set_attributes(
                span,
                {
                    attrs.PROVIDER_SERVED: provider,
                    attrs.MODEL_SERVED: model,
                    attrs.CIRCUIT_STATE: state.value,
                    attrs.CIRCUIT_ALLOWED: allowed,
                    "gateway.is_canary": is_canary,
                },
            )

            return allowed, is_canary

    async def record_success(self, provider: str, model: str, is_canary: bool = False) -> None:
        """
        Record a successful request execution.
        If canary probe succeeds, resets circuit back to CLOSED.
        """
        try:
            redis = await get_redis()
            state = await self.get_state(provider, model)

            if is_canary or state == CircuitState.HALF_OPEN:
                await redis.set(self._state_key(provider, model), CircuitState.CLOSED.value)
                await redis.delete(
                    self._failures_key(provider, model),
                    self._cooldown_key(provider, model),
                    self._probe_lock_key(provider, model),
                )
                gateway_metrics.record_circuit_change(provider, model, CircuitState.HALF_OPEN.value, CircuitState.CLOSED.value)
                await self.repository.log_circuit_state_change(
                    provider_name=provider,
                    model_name=model,
                    status=CircuitState.CLOSED.value,
                    previous_status=CircuitState.HALF_OPEN.value,
                    reason=f"Canary probe succeeded; circuit returned to CLOSED state.",
                )
        except Exception:
            pass

    async def record_failure(self, provider: str, model: str, is_canary: bool = False) -> None:
        """
        Record a request-level failure (called ONLY ONCE when entire request exhausts retries).
        If failure count >= N or canary fails, trips circuit to OPEN.
        """
        try:
            redis = await get_redis()
            state = await self.get_state(provider, model)

            if is_canary or state == CircuitState.HALF_OPEN:
                # Canary probe failed -> re-open circuit & reset cooldown
                await redis.set(self._state_key(provider, model), CircuitState.OPEN.value)
                await redis.setex(self._cooldown_key(provider, model), self.config.cooldown_seconds, "1")
                await redis.delete(self._probe_lock_key(provider, model))
                gateway_metrics.record_circuit_change(provider, model, CircuitState.HALF_OPEN.value, CircuitState.OPEN.value)
                await self.repository.log_circuit_state_change(
                    provider_name=provider,
                    model_name=model,
                    status=CircuitState.OPEN.value,
                    previous_status=CircuitState.HALF_OPEN.value,
                    reason=f"Canary probe failed; circuit returned to OPEN state.",
                )
                return

            # Regular request failure -> push timestamp to rolling window list
            fail_key = self._failures_key(provider, model)
            now = time.time()
            min_ts = now - self.config.window_seconds_m

            await redis.zadd(fail_key, {str(now): now})
            await redis.zremrangebyscore(fail_key, "-inf", min_ts)
            await redis.expire(fail_key, 3600)

            fail_count = await redis.zcard(fail_key)

            if fail_count >= self.config.failure_threshold_n:
                # Trip circuit OPEN!
                await redis.set(self._state_key(provider, model), CircuitState.OPEN.value)
                await redis.setex(self._cooldown_key(provider, model), self.config.cooldown_seconds, "1")
                gateway_metrics.record_circuit_change(provider, model, state.value, CircuitState.OPEN.value)
                await self.repository.log_circuit_state_change(
                    provider_name=provider,
                    model_name=model,
                    status=CircuitState.OPEN.value,
                    previous_status=state.value,
                    reason=f"Circuit TRIPPED: {fail_count} request failures in {self.config.window_seconds_m}s window.",
                    consecutive_failures=fail_count,
                )
        except Exception:
            pass

