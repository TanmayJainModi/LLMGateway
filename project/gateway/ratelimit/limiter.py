"""
limiter.py

Distributed token bucket rate limiter backed by Redis.

Enforces per-team-model-access rate limits:
    - RPM (Requests Per Minute)
    - TPM (Tokens Per Minute) with reserve-and-refund
    - RPD (Requests Per Day)

All operations are atomic via Lua scripts.
Fails closed (503) if Redis is unreachable.
"""

import uuid
import time
from datetime import date

from project.cache.connection import get_redis
from project.gateway.schemas.request import ChatRequest
from project.gateway.validation.result import ValidationResult
from project.gateway.ratelimit.estimator import TokenEstimator
from project.gateway.ratelimit.priority import get_priority_config
from project.gateway.ratelimit.priority_queue import PriorityQueueManager
from project.gateway.ratelimit.exceptions import (
    RateLimitExceededError,
    RateLimiterUnavailableError,
)
from project.gateway.ratelimit.lua_scripts import (
    TOKEN_BUCKET_LUA,
    REFUND_LUA,
    DAILY_COUNTER_LUA,
)


from project.gateway.telemetry.tracer import gateway_tracer
import project.gateway.telemetry.attributes as attrs


class RateLimiter:
    """
    Distributed rate limiter using Redis, atomic Lua scripts, and Priority Queues.
    """

    def __init__(self):
        self.estimator = TokenEstimator()

    async def check_rate_limit(
        self,
        validation: ValidationResult,
        request: ChatRequest,
        estimated_tokens: int | None = None,
        enable_queue: bool = True,
    ) -> int:
        """
        Check all rate limits for the request with priority capacity reservation.
        """
        with gateway_tracer.start_span("rate_limit_check") as span:
            try:
                redis = await get_redis()
            except Exception as e:
                raise RateLimiterUnavailableError(
                    f"Rate limiter unavailable: Redis connection failed. {e}"
                )

            tma = validation.team_model_access
            tma_id = tma["id"]

            rpm = tma["requests_per_minute"]
            rpd = tma["requests_per_day"]
            tpm = tma["tokens_per_minute"]

            provider_name = validation.provider["provider_name"]
            priority_config = get_priority_config(request)
            request_id = str(uuid.uuid4())

            if estimated_tokens is None:
                estimated_tokens = self.estimator.estimate(request, provider_name)

            gateway_tracer.set_attributes(
                span,
                {
                    attrs.TEAM_ID: validation.team["id"],
                    attrs.PRIORITY_LEVEL: priority_config.level.value,
                    attrs.RESERVE_PCT: priority_config.reserve_pct,
                    "ratelimit.rpm": rpm,
                    "ratelimit.tpm": tpm,
                    "ratelimit.estimated_cost_tokens": estimated_tokens,
                },
            )



        now = time.time()

        # ─── 1. RPM Check ────────────────────────────────────
        async def eval_rpm(cand: dict | None = None):
            res_pct = cand["reserve_pct"] if cand is not None else priority_config.reserve_pct
            res = await redis.eval(
                TOKEN_BUCKET_LUA,
                1,
                f"ratelimit:tma:{tma_id}:rpm",
                str(rpm),                   # capacity
                str(rpm / 60.0),            # refill_rate (tokens/sec)
                "1",                        # cost = 1 request
                str(time.time()),
                str(res_pct),
            )
            return bool(int(res[0])), int(res[1]), int(res[2])

        allowed, remaining, retry_after = await eval_rpm()

        if not allowed:
            if enable_queue:
                remaining, retry_after = await PriorityQueueManager.wait_and_retry(
                    redis=redis,
                    tma_id=tma_id,
                    request_id=request_id,
                    priority_config=priority_config,
                    check_fn=eval_rpm,
                    estimated_cost=1,
                )
            else:
                raise RateLimitExceededError(
                    message=f"RPM limit exceeded for {priority_config.level.value} priority. Limit: {rpm} requests/min.",
                    retry_after=retry_after,
                    limit=rpm,
                    remaining=remaining,
                    bucket_type="rpm",
                )

        # ─── 2. TPM Reserve ──────────────────────────────────
        async def eval_tpm(cand: dict | None = None):
            res_pct = cand["reserve_pct"] if cand is not None else priority_config.reserve_pct
            cost = cand["estimated_cost"] if cand is not None else estimated_tokens
            res = await redis.eval(
                TOKEN_BUCKET_LUA,
                1,
                f"ratelimit:tma:{tma_id}:tpm",
                str(tpm),                   # capacity
                str(tpm / 60.0),            # refill_rate (tokens/sec)
                str(cost),                  # cost = estimated tokens
                str(time.time()),
                str(res_pct),
            )
            return bool(int(res[0])), int(res[1]), int(res[2])

        allowed, remaining, retry_after = await eval_tpm()

        if not allowed:
            if enable_queue:
                remaining, retry_after = await PriorityQueueManager.wait_and_retry(
                    redis=redis,
                    tma_id=tma_id,
                    request_id=request_id,
                    priority_config=priority_config,
                    check_fn=eval_tpm,
                    estimated_cost=estimated_tokens,
                )
            else:
                raise RateLimitExceededError(
                    message=f"TPM limit exceeded for {priority_config.level.value} priority. Limit: {tpm} tokens/min.",
                    retry_after=retry_after,
                    limit=tpm,
                    remaining=remaining,
                    bucket_type="tpm",
                )


        # ─── 3. RPD Check ────────────────────────────────────
        today = date.today().isoformat()

        try:
            rpd_result = await redis.eval(
                DAILY_COUNTER_LUA,
                1,
                f"ratelimit:tma:{tma_id}:rpd:{today}",
                str(rpd),
            )
        except Exception as e:
            raise RateLimiterUnavailableError(
                f"Rate limiter unavailable: RPD check failed. {e}"
            )

        allowed, current_count, retry_after = int(rpd_result[0]), int(rpd_result[1]), int(rpd_result[2])

        if not allowed:
            raise RateLimitExceededError(
                message=f"RPD limit exceeded. Limit: {rpd} requests/day.",
                retry_after=retry_after,
                limit=rpd,
                remaining=0,
                bucket_type="rpd",
            )

        return estimated_tokens

    async def refund_tokens(
        self,
        tma_id: int,
        tpm_capacity: int,
        refund_amount: int,
    ) -> None:
        """
        Refund unused tokens back to the TPM bucket
        after the actual provider usage is known.

        Parameters
        ----------
        tma_id : int
            The team_model_access ID.
        tpm_capacity : int
            The TPM capacity (bucket never exceeds this).
        refund_amount : int
            Number of tokens to return (estimated - actual).
        """

        if refund_amount <= 0:
            return

        try:
            redis = await get_redis()

            await redis.eval(
                REFUND_LUA,
                1,
                f"ratelimit:tma:{tma_id}:tpm",
                str(refund_amount),
                str(tpm_capacity),
            )
        except Exception:
            # Refund failure is non-critical.
            # The bucket will self-correct via natural refill.
            pass
