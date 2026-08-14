"""
priority_queue.py

Redis-backed Aging-Aware Priority Queue Manager.

Prevents starvation of MEDIUM and LOW requests by dynamically increasing
effective priority over waiting time:

    effective_priority = base_priority + aging_factor * (now - enqueue_time)

Preserves:
    - Base Priority: HIGH (300) > MEDIUM (200) > LOW (100)
    - FIFO ordering among requests with equal effective priority
    - Token Bucket capacity reservation semantics (HIGH=0%, MEDIUM=10%, LOW=20%)
    - Non-preemption of executing requests
    - Queue timeouts
    - Concurrency safety via atomic Redis Lua claim script (CLAIM_QUEUE_ITEM_LUA)
"""

import asyncio
import json
import math
import time
from typing import Callable, Awaitable
from project.gateway.ratelimit.priority import PriorityConfig, PriorityLevel, AGING_FACTOR
from project.gateway.ratelimit.exceptions import RateLimitExceededError
from project.gateway.ratelimit.lua_scripts import CLAIM_QUEUE_ITEM_LUA


class PriorityQueueManager:
    """
    Manages aging-aware priority scheduling in Redis for throttled requests.
    """

    @staticmethod
    def _queue_meta_key(tma_id: int) -> str:
        return f"ratelimit:queue_meta:{tma_id}"

    @classmethod
    async def enqueue(
        cls,
        redis,
        tma_id: int,
        request_id: str,
        priority_config: PriorityConfig,
        estimated_cost: int = 1,
    ) -> None:
        """Store request metadata in Redis Hash (HSET)."""
        key = cls._queue_meta_key(tma_id)
        now = time.time()
        payload = json.dumps({
            "request_id": request_id,
            "level": priority_config.level.value,
            "base_priority": float(priority_config.base_priority),
            "reserve_pct": float(priority_config.reserve_pct),
            "queue_timeout_sec": float(priority_config.queue_timeout_sec),
            "enqueue_time": now,
            "estimated_cost": estimated_cost,
        })
        await redis.hset(key, request_id, payload)
        await redis.expire(key, 300)

    @classmethod
    async def dequeue(cls, redis, tma_id: int, request_id: str) -> bool:
        """
        Atomically claim and delete a request_id from the queue metadata hash
        using CLAIM_QUEUE_ITEM_LUA script.
        """
        key = cls._queue_meta_key(tma_id)
        try:
            res = await redis.eval(CLAIM_QUEUE_ITEM_LUA, 1, key, request_id)
            return int(res) == 1
        except Exception:
            return False

    @classmethod
    async def get_sorted_candidates(
        cls,
        redis,
        tma_id: int,
        aging_factor: float = AGING_FACTOR,
    ) -> list[dict]:
        """
        Reads all queued metadata, purges timed-out requests, dynamically calculates
        effective priority for every active item, and returns candidates sorted by:
            1. effective_priority (DESC)
            2. enqueue_time (ASC for FIFO tie-breaking)
        """
        key = cls._queue_meta_key(tma_id)
        raw_map = await redis.hgetall(key)
        if not raw_map:
            return []

        now = time.time()
        active_candidates = []
        timed_out_ids = []

        for req_id, raw_json in raw_map.items():
            try:
                item = json.loads(raw_json)
                elapsed = now - item["enqueue_time"]
                if elapsed >= item["queue_timeout_sec"]:
                    timed_out_ids.append(req_id)
                else:
                    item["effective_priority"] = item["base_priority"] + (aging_factor * elapsed)
                    active_candidates.append(item)
            except Exception:
                timed_out_ids.append(req_id)

        # Purge timed-out items from Redis Hash
        if timed_out_ids:
            try:
                await redis.hdel(key, *timed_out_ids)
            except Exception:
                pass

        # Sort: effective_priority DESC, enqueue_time ASC (FIFO)
        active_candidates.sort(
            key=lambda x: (-x["effective_priority"], x["enqueue_time"])
        )
        return active_candidates

    @classmethod
    async def is_head_of_queue(
        cls,
        redis,
        tma_id: int,
        request_id: str,
        level: PriorityLevel | None = None,
    ) -> bool:
        """
        Returns True if request_id is the highest effective priority candidate.
        """
        candidates = await cls.get_sorted_candidates(redis, tma_id)
        if not candidates:
            return True
        return candidates[0]["request_id"] == request_id

    @classmethod
    async def wait_and_retry(
        cls,
        redis,
        tma_id: int,
        request_id: str,
        priority_config: PriorityConfig,
        check_fn: Callable[[dict], Awaitable[tuple[bool, int, int]]],
        estimated_cost: int = 1,
        aging_factor: float = AGING_FACTOR,
    ) -> tuple[int, int]:
        """
        Enqueues request metadata, recalculates effective priority across all candidates
        on every scheduling turn, tries eligible candidates in sorted order, and executes
        atomically via CLAIM_QUEUE_ITEM_LUA when capacity check passes.
        """
        level = priority_config.level
        timeout_sec = priority_config.queue_timeout_sec
        start_time = time.time()

        await cls.enqueue(redis, tma_id, request_id, priority_config, estimated_cost)

        try:
            while True:
                elapsed = time.time() - start_time
                if elapsed >= timeout_sec:
                    raise RateLimitExceededError(
                        message=f"Request queued for {level.value} priority timed out after {timeout_sec}s.",
                        retry_after=int(math.ceil(timeout_sec)),
                        limit=0,
                        remaining=0,
                        bucket_type=f"priority_queue_{level.value}",
                    )

                candidates = await cls.get_sorted_candidates(redis, tma_id, aging_factor)

                # Iterate candidates in effective priority order
                for cand in candidates:
                    allowed, remaining, retry_after = await check_fn(cand)
                    if allowed:
                        # Attempt atomic claim
                        claimed = await cls.dequeue(redis, tma_id, cand["request_id"])
                        if claimed:
                            if cand["request_id"] == request_id:
                                return remaining, retry_after
                            # If another worker's candidate was claimed, break candidate loop & sleep
                            break

                await asyncio.sleep(0.05)
        finally:
            await cls.dequeue(redis, tma_id, request_id)
