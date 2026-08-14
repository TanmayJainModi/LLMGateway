"""
exceptions.py

Exceptions raised by the rate limiter.
"""


class RateLimitExceededError(Exception):
    """
    Raised when a request exceeds the team's rate limit.

    Contains metadata for constructing HTTP 429 responses
    with accurate Retry-After headers.
    """

    def __init__(
        self,
        message: str,
        retry_after: int,
        limit: int,
        remaining: int,
        bucket_type: str,
    ):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.bucket_type = bucket_type


class RateLimiterUnavailableError(Exception):
    """
    Raised when Redis is unreachable.

    Fail Closed: if the rate limiter cannot verify
    limits, the request is rejected with HTTP 503.
    """
    pass
