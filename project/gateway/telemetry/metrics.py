"""
metrics.py

Prometheus Metrics Module for LLM Gateway.
Defines counters, histograms, and gauges for request counts, error rates, latency durations,
token throughput, USD costs, fallback events, and circuit breaker states.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry()

# 1. Requests Counter
REQUESTS_TOTAL = Counter(
    "llm_gateway_requests_total",
    "Total requests processed by the LLM Gateway.",
    ["team_id", "model_requested", "provider_served", "model_served", "request_type"],
    registry=REGISTRY,
)

# 2. Errors Counter
ERRORS_TOTAL = Counter(
    "llm_gateway_errors_total",
    "Total request errors categorized by error type.",
    ["team_id", "model_requested", "provider_served", "model_served", "error_type"],
    registry=REGISTRY,
)

# 3. Latency Histogram (seconds)
LATENCY_SECONDS = Histogram(
    "llm_gateway_request_duration_seconds",
    "Request latency duration in seconds (for P50, P95, P99 calculation).",
    ["provider_served", "model_served"],
    buckets=(0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 15.0, 30.0),
    registry=REGISTRY,
)

# 4. Token Throughput Counter
TOKENS_TOTAL = Counter(
    "llm_gateway_tokens_total",
    "Total token throughput processed.",
    ["token_type", "team_id", "provider_served", "model_served"],
    registry=REGISTRY,
)

# 5. Cost USD Counter
COST_USD_TOTAL = Counter(
    "llm_gateway_cost_usd_total",
    "Cumulative cost in USD incurred per team.",
    ["team_id", "provider_served", "model_served"],
    registry=REGISTRY,
)

# 6. Fallbacks Counter
FALLBACKS_TOTAL = Counter(
    "llm_gateway_fallbacks_total",
    "Total fallback routing triggers executed.",
    ["team_id", "primary_provider", "fallback_provider"],
    registry=REGISTRY,
)

# 7. Circuit Breaker State Changes Counter
CIRCUIT_STATE_CHANGES_TOTAL = Counter(
    "llm_gateway_circuit_breaker_state_changes_total",
    "Total circuit breaker state transitions.",
    ["provider", "model", "from_state", "to_state"],
    registry=REGISTRY,
)

# 8. Circuit Breaker Current State Gauge (0=CLOSED, 1=HALF_OPEN, 2=OPEN)
CIRCUIT_STATE_GAUGE = Gauge(
    "llm_gateway_circuit_breaker_state",
    "Current circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN).",
    ["provider", "model"],
    registry=REGISTRY,
)

# 9. Team Configured Budget Gauge (period = "daily" or "monthly")
TEAM_BUDGET_USD = Gauge(
    "llm_gateway_team_budget_usd",
    "Configured daily and monthly budget caps per team in USD.",
    ["team_id", "period"],
    registry=REGISTRY,
)

STATE_VALUE_MAP = {
    "CLOSED": 0,
    "HALF_OPEN": 1,
    "OPEN": 2,
}



class GatewayMetrics:
    """
    Unified telemetry metrics recorder for the LLM Gateway.
    """

    def record_completed_request(
        self,
        team_id: str,
        model_requested: str,
        provider_served: str,
        model_served: str,
        request_type: str,
        duration_seconds: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        fallback_used: bool = False,
        primary_provider: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """
        Unified recording method for a completed gateway request.
        """
        # Increment Request Counter
        REQUESTS_TOTAL.labels(
            team_id=team_id,
            model_requested=model_requested,
            provider_served=provider_served,
            model_served=model_served,
            request_type=request_type,
        ).inc()

        # Record Latency Histogram
        LATENCY_SECONDS.labels(
            provider_served=provider_served,
            model_served=model_served,
        ).observe(duration_seconds)

        # Record Token Throughput
        if input_tokens > 0:
            TOKENS_TOTAL.labels(
                token_type="input",
                team_id=team_id,
                provider_served=provider_served,
                model_served=model_served,
            ).inc(input_tokens)

        if output_tokens > 0:
            TOKENS_TOTAL.labels(
                token_type="output",
                team_id=team_id,
                provider_served=provider_served,
                model_served=model_served,
            ).inc(output_tokens)

        # Record Cost USD
        if cost_usd > 0.0:
            COST_USD_TOTAL.labels(
                team_id=team_id,
                provider_served=provider_served,
                model_served=model_served,
            ).inc(cost_usd)

        # Record Fallback if used
        if fallback_used and primary_provider:
            FALLBACKS_TOTAL.labels(
                team_id=team_id,
                primary_provider=primary_provider,
                fallback_provider=provider_served,
            ).inc()

        # Record Error if present
        if error_type:
            ERRORS_TOTAL.labels(
                team_id=team_id,
                model_requested=model_requested,
                provider_served=provider_served,
                model_served=model_served,
                error_type=error_type,
            ).inc()

    def record_circuit_change(self, provider: str, model: str, from_state: str, to_state: str) -> None:
        """
        Record a Circuit Breaker state transition and update state gauge.
        """
        CIRCUIT_STATE_CHANGES_TOTAL.labels(
            provider=provider,
            model=model,
            from_state=from_state,
            to_state=to_state,
        ).inc()

        val = STATE_VALUE_MAP.get(to_state, 0)
        CIRCUIT_STATE_GAUGE.labels(provider=provider, model=model).set(val)

    def set_team_budget(
        self,
        team_id: str,
        daily_budget: float | None = None,
        monthly_budget: float | None = None,
    ) -> None:
        """
        Set daily and monthly configured budget gauges for a team.
        """
        if daily_budget is not None and daily_budget > 0.0:
            TEAM_BUDGET_USD.labels(team_id=team_id, period="daily").set(daily_budget)
        if monthly_budget is not None and monthly_budget > 0.0:
            TEAM_BUDGET_USD.labels(team_id=team_id, period="monthly").set(monthly_budget)



# Singleton metrics instance
gateway_metrics = GatewayMetrics()
