"""
retry.py

Request-Type-Aware Exponential Backoff Retry Engine with Jitter,
Retry-After Header Parsing, and Strict Error Classification.
"""

import random
import re
from dataclasses import dataclass
from project.gateway.schemas.request import RequestType


MAX_RETRIES: int = 3
MAX_ATTEMPTS: int = 1 + MAX_RETRIES  # 4 total attempts


@dataclass
class BackoffConfig:
    initial_backoff: float
    max_backoff: float
    absolute_max_delay: float
    jitter: float = 0.05  # 0 to 50ms random jitter


BACKOFF_CONFIGS: dict[RequestType, BackoffConfig] = {
    RequestType.STREAM: BackoffConfig(
        initial_backoff=0.10,   # 100ms -> 200ms -> 400ms (total ~700ms)
        max_backoff=0.80,
        absolute_max_delay=3.0,
    ),
    RequestType.CHAT: BackoffConfig(
        initial_backoff=0.20,   # 200ms -> 400ms -> 800ms (total ~1.4s)
        max_backoff=1.60,
        absolute_max_delay=5.0,
    ),
    RequestType.BATCH: BackoffConfig(
        initial_backoff=0.50,   # 500ms -> 1.0s -> 2.0s (total ~3.5s)
        max_backoff=4.00,
        absolute_max_delay=10.0,
    ),
}


class RetryPolicy:
    """
    Manages error classification, backoff calculation, and retry decisions.
    """

    @staticmethod
    def is_retryable(e: Exception) -> bool:
        """
        Classifies an exception as retryable or non-retryable.

        Non-Retryable Errors (False):
            - 400 Bad Request / Schema Error / Content Policy Violation
            - 401 Unauthorized / Invalid Credentials
            - 403 Forbidden / Permission Denied
            - 404 Model Not Found
            - 413 Payload Too Large / Context Window Exceeded

        Retryable Errors (True):
            - 429 Rate Limit
            - Timeouts / Connection Errors
            - HTTP 500, 502, 503, 504 Server Errors
        """
        status_code = getattr(e, "status_code", None) or getattr(e, "code", None)
        msg = str(e).lower()

        # Non-retryable HTTP status codes
        if status_code in (400, 401, 403, 404, 413):
            return False

        # Non-retryable string keywords
        if any(kw in msg for kw in ("unauthorized", "invalid api key", "permission denied", "content policy", "payload too large")):
            return False

        # Retryable HTTP status codes
        if status_code in (429, 500, 502, 503, 504):
            return True

        # Retryable string keywords
        if any(kw in msg for kw in ("timeout", "connection", "rate limit", "429", "500", "502", "503", "504", "unavailable", "service unavailable")):
            return True

        # Default: network/unknown errors are retryable
        return True

    @staticmethod
    def extract_retry_after(e: Exception) -> float | None:
        """Extract Retry-After header or property if present."""
        retry_after = getattr(e, "retry_after", None)
        if retry_after is not None:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass

        headers = getattr(e, "headers", None)
        if isinstance(headers, dict):
            val = headers.get("Retry-After") or headers.get("retry-after")
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass

        msg = str(e)
        match = re.search(r"retry[-_]after[:=]\s*(\d+(\.\d+)?)", msg, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, TypeError):
                pass

        return None

    @classmethod
    def calculate_backoff_delay(
        cls,
        attempt: int,
        request_type: RequestType = RequestType.CHAT,
        retry_after_sec: float | None = None,
    ) -> float:
        """
        Calculates exponential backoff delay with jitter and absolute maximum cap.

        Formula:
            base_delay = min(max_backoff, initial_backoff * 2^(attempt - 1))
            delay = min(absolute_max_delay, max(base_delay, retry_after_sec) + random(0, jitter))
        """
        cfg = BACKOFF_CONFIGS.get(request_type, BACKOFF_CONFIGS[RequestType.CHAT])

        base_delay = min(cfg.max_backoff, cfg.initial_backoff * (2 ** (attempt - 1)))
        effective_base = max(base_delay, retry_after_sec or 0.0)
        jitter_amount = random.uniform(0.0, cfg.jitter)
        total_delay = effective_base + jitter_amount

        return min(cfg.absolute_max_delay, total_delay)
