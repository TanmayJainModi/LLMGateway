"""
priority.py

Priority levels, configs, and gateway-owned request_type mapping.
"""

from enum import Enum
from dataclasses import dataclass
from project.gateway.schemas.request import ChatRequest, RequestType


class PriorityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


AGING_FACTOR: float = 10.0  # Configurable aging factor (points per second waiting)


@dataclass
class PriorityConfig:
    level: PriorityLevel
    base_priority: float
    reserve_pct: float
    queue_timeout_sec: float


PRIORITY_MAP: dict[RequestType, PriorityConfig] = {
    RequestType.STREAM: PriorityConfig(
        level=PriorityLevel.HIGH,
        base_priority=300.0,
        reserve_pct=0.00,        # 100% capacity allowed
        queue_timeout_sec=0.20,   # Fast 200ms fail/retry for live chat
    ),
    RequestType.CHAT: PriorityConfig(
        level=PriorityLevel.MEDIUM,
        base_priority=200.0,
        reserve_pct=0.10,        # 90% capacity allowed (reserves 10% for HIGH)
        queue_timeout_sec=2.00,   # 2s queue timeout
    ),
    RequestType.BATCH: PriorityConfig(
        level=PriorityLevel.LOW,
        base_priority=100.0,
        reserve_pct=0.20,        # 80% capacity allowed (reserves 20% for HIGH/MEDIUM)
        queue_timeout_sec=30.00,  # 30s queue timeout (batch jobs tolerate waiting)
    ),
}



def get_priority_config(request: ChatRequest) -> PriorityConfig:
    """
    Derive the priority configuration for a request.

    If request_type is explicitly provided, map it directly.
    Otherwise, auto-infer:
        - request.stream == True -> RequestType.STREAM (HIGH priority)
        - request.stream == False -> RequestType.CHAT (MEDIUM priority)
    """
    req_type = request.request_type

    if req_type is None:
        if request.stream:
            req_type = RequestType.STREAM
        else:
            req_type = RequestType.CHAT

    return PRIORITY_MAP[req_type]
