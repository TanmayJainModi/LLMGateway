"""
router.py

Routes validated requests to the appropriate provider.

The router orchestrates rate limiting, request enrichment,
health checks, automatic fallback, usage recording,
and TPM token refund.
"""

from typing import AsyncGenerator, Union

from project.gateway.routing.provider_factory import (
    ProviderFactory,
)
from project.gateway.cost_per_req.cost import estimate_cost
from project.database.team_repository import TeamRepository
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.schemas.stream import StreamChunk, StreamResult
from project.gateway.routing.fallback import FallbackManager
from project.gateway.providers.base import BaseProvider
from project.gateway.enrichment.enricher import RequestEnricher
from project.gateway.ratelimit.limiter import RateLimiter

from project.gateway.validation.result import (
    ValidationResult,
)


from project.gateway.health.service import HealthService, HealthStatus
from project.gateway.telemetry.metrics import gateway_metrics
from project.gateway.telemetry.tracer import gateway_tracer
import project.gateway.telemetry.attributes as attrs



from project.gateway.routing.retry import RetryPolicy, MAX_ATTEMPTS, MAX_RETRIES, RequestType
from project.gateway.circuit_breaker.breaker import CircuitBreaker





class Router:

    """
    Routes requests to providers.
    """

    def __init__(self):
        self.fallback = FallbackManager()
        self.fallback_manager = self.fallback
        self.retry_policy = RetryPolicy()
        self.circuit_breaker = CircuitBreaker()
        self.team_repository = TeamRepository()
        self.enricher = RequestEnricher()
        self.rate_limiter = RateLimiter()
        self.health_service = HealthService()


    async def route(
        self,
        validation: ValidationResult,
        request: ChatRequest,
        automatic_routing: bool = True,
    ) -> Union[ChatResponse, AsyncGenerator[StreamChunk, None]]:
        """
        Route a request to the requested provider.

        Pipeline:
            1. Rate Limit Check (RPM, TPM reserve, RPD)
            2. Request Enrichment (keyword filter, prompt hierarchy)
            3. Provider Execution (streaming or non-streaming)
        Route a request to the requested provider with OpenTelemetry Distributed Tracing.
        """
        import time as _time
        req_start_time = _time.time()
        primary_provider_name = validation.provider["provider_name"]
        primary_model_name = validation.model["model_name"]

        with gateway_tracer.start_span("gateway_request") as root_span:
            # 1. request_receipt span
            with gateway_tracer.start_span("request_receipt") as rx_span:
                gateway_tracer.set_attributes(
                    rx_span,
                    {
                        attrs.PROVIDER_REQUESTED: primary_provider_name,
                        attrs.MODEL_REQUESTED: primary_model_name,
                        attrs.REQUEST_TYPE: (request.request_type.value if request.request_type else ("STREAM" if request.stream else "CHAT")),
                        "gateway.stream": request.stream,
                    },
                )

            # 2. Rate Limit Check (reserves estimated tokens from TPM bucket)
            estimated_tokens = await self.rate_limiter.check_rate_limit(
                validation, request
            )

            # 3. Router-owned Request Enrichment
            request = self.enricher.enrich(request, validation.team)

            if request.stream:
                res = await self._route_stream(
                    validation=validation,
                    request=request,
                    automatic_routing=automatic_routing,
                    estimated_tokens=estimated_tokens,
                )
            else:
                res = await self._route_non_stream(
                    validation=validation,
                    request=request,
                    automatic_routing=automatic_routing,
                    estimated_tokens=estimated_tokens,
                    root_span=root_span,
                    req_start_time=req_start_time,
                )
            return res

    def _generate_budget_warning(self, spend_info: dict) -> str | None:
        if not spend_info:
            return None

        monthly_spend = spend_info.get("monthly_spend", 0.0)
        monthly_budget = spend_info.get("monthly_budget")
        daily_spend = spend_info.get("daily_spend", 0.0)
        daily_budget = spend_info.get("daily_budget")

        warnings = []
        if monthly_budget and monthly_budget > 0:
            pct = (monthly_spend / monthly_budget) * 100
            if pct >= 80.0:
                warnings.append(f"Monthly budget at {pct:.1f}% (${monthly_spend:.2f} / ${monthly_budget:.2f})")

        if daily_budget and daily_budget > 0:
            pct = (daily_spend / daily_budget) * 100
            if pct >= 80.0:
                warnings.append(f"Daily budget at {pct:.1f}% (${daily_spend:.2f} / ${daily_budget:.2f})")

        if warnings:
            return " | ".join(warnings)

    async def _route_non_stream(
        self,
        validation: ValidationResult,
        request: ChatRequest,
        automatic_routing: bool = True,
        estimated_tokens: int = 0,
        root_span=None,
        req_start_time: float = 0.0,
    ) -> ChatResponse:
        attempted = set()
        fallback_attempts = 0

        primary_provider_name = validation.provider["provider_name"]
        primary_model_name = validation.model["model_name"]

        curr_provider_name = primary_provider_name
        curr_model_name = primary_model_name
        input_price = float(validation.model.get("input_price_per_million_tokens") or 0.0)
        output_price = float(validation.model.get("output_price_per_million_tokens") or 0.0)

        # provider_selection span
        with gateway_tracer.start_span("provider_selection") as sel_span:
            gateway_tracer.set_attributes(
                sel_span,
                {
                    attrs.PROVIDER_REQUESTED: primary_provider_name,
                    attrs.MODEL_REQUESTED: primary_model_name,
                },
            )

        # Pre-flight Health & Circuit Check: if primary provider is DOWN or OPEN, jump straight to fallback!
        primary_status = await self.health_service.get_current_status(primary_provider_name, primary_model_name)
        allow_primary_exec, _ = await self.circuit_breaker.allow_request(primary_provider_name, primary_model_name)

        if (primary_status == HealthStatus.DOWN or not allow_primary_exec) and automatic_routing:
            res = await self.fallback.get_next_candidate(
                team_id=validation.team["id"],
                primary_model_name=primary_model_name,
                attempted=attempted,
                fallback_attempts=fallback_attempts,
            )
            if res is not None:
                candidate, fallback_reason = res
                attempted.add((primary_provider_name, primary_model_name))
                curr_provider_name = candidate["provider_name"]
                curr_model_name = candidate["model_name"]
                fallback_attempts += 1

        req_type = request.request_type or (RequestType.STREAM if request.stream else RequestType.CHAT)
        retry_count = 0

        while True:
            attempted.add((curr_provider_name, curr_model_name))

            # Circuit Check for current candidate provider
            allow_exec, is_canary = await self.circuit_breaker.allow_request(curr_provider_name, curr_model_name)
            if not allow_exec and automatic_routing:
                # Fast-fail candidate whose circuit is OPEN
                res = await self.fallback.get_next_candidate(
                    team_id=validation.team["id"],
                    primary_model_name=primary_model_name,
                    attempted=attempted,
                    fallback_attempts=fallback_attempts,
                )
                if res is None:
                    raise RuntimeError("No provider available for fallback (all candidates OPEN/DOWN).")
                candidate, _ = res
                curr_provider_name = candidate["provider_name"]
                curr_model_name = candidate["model_name"]
                fallback_attempts += 1
                continue

            provider = ProviderFactory.create(curr_provider_name)
            request.model = curr_model_name

            import time as _time
            import asyncio as _asyncio
            response = None
            last_exception = None

            # llm_api_call span
            with gateway_tracer.start_span("llm_api_call") as call_span:
                gateway_tracer.set_attributes(
                    call_span,
                    {
                        attrs.PROVIDER_SERVED: curr_provider_name,
                        attrs.MODEL_SERVED: curr_model_name,
                    },
                )

                # Retry loop: max_attempts = 4 (1 initial call + 3 retries)
                for attempt_idx in range(1, MAX_ATTEMPTS + 1):
                    start_time = _time.time()
                    try:
                        gateway_tracer.add_event(call_span, f"attempt_{attempt_idx}", {"attempt": attempt_idx})
                        response = await provider.chat(request)
                        elapsed_ms = int((_time.time() - start_time) * 1000)
                        await self.health_service.record_request_health(
                            curr_provider_name, curr_model_name, elapsed_ms, is_error=False
                        )
                        last_exception = None
                        break  # Call succeeded!
                    except Exception as e:
                        elapsed_ms = int((_time.time() - start_time) * 1000)
                        last_exception = e
                        retry_count += 1
                        gateway_tracer.add_event(call_span, f"retry_{attempt_idx}_failed", {"error": str(e)})

                        # Record passive health metric on EVERY attempt
                        await self.health_service.record_request_health(
                            curr_provider_name, curr_model_name, elapsed_ms, is_error=True
                        )

                        # Non-retryable error check (e.g. 400, 401, 403, 413) -> short circuit immediately!
                        if not self.retry_policy.is_retryable(e):
                            await provider.close()
                            raise e

                        # Retryable error -> calculate backoff & sleep if attempts remaining
                        if attempt_idx < MAX_ATTEMPTS:
                            retry_after_sec = self.retry_policy.extract_retry_after(e)
                            backoff_delay = self.retry_policy.calculate_backoff_delay(
                                attempt=attempt_idx,
                                request_type=req_type,
                                retry_after_sec=retry_after_sec,
                            )
                            await _asyncio.sleep(backoff_delay)

            await provider.close()

            if response is not None:
                # Record successful execution in Circuit Breaker
                await self.circuit_breaker.record_success(curr_provider_name, curr_model_name, is_canary=is_canary)

                cost = 0.0
                in_tok, out_tok, tot_tok = 0, 0, 0

                # response_processing span
                with gateway_tracer.start_span("response_processing") as proc_span:
                    if (
                        response.message is not None
                        and response.message.content
                        and response.usage is not None
                    ):
                        in_tok = response.usage.input_tokens
                        out_tok = response.usage.output_tokens
                        tot_tok = in_tok + out_tok

                        cost = estimate_cost(
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            input_price_per_1m=input_price,
                            output_price_per_1m=output_price,
                        )

                        spend_info = await self.team_repository.add_usage(
                            team_id=validation.team["id"],
                            model_id=validation.model["id"],
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            estimated_cost=cost,
                        )
                        response.warning = self._generate_budget_warning(spend_info)

                        # TPM Refund
                        refund = max(0, estimated_tokens - tot_tok)
                        if refund > 0:
                            tma_id = validation.team_model_access["id"]
                            tpm_capacity = validation.team_model_access["tokens_per_minute"]
                            await self.rate_limiter.refund_tokens(tma_id, tpm_capacity, refund)

                    gateway_tracer.set_attributes(
                        proc_span,
                        {
                            attrs.INPUT_TOKENS: in_tok,
                            attrs.OUTPUT_TOKENS: out_tok,
                            attrs.TOTAL_TOKENS: tot_tok,
                            attrs.ESTIMATED_COST: cost,
                            attrs.BUDGET_WARNING: response.warning,
                        },
                    )

                # Attach rich fallback metadata if fallback occurred
                fallback_used = (curr_provider_name != primary_provider_name or curr_model_name != primary_model_name)
                if fallback_used:
                    response.fallback_metadata = {
                        "original_provider": primary_provider_name,
                        "original_model": primary_model_name,
                        "fallback_provider": curr_provider_name,
                        "fallback_model": curr_model_name,
                        "reason": f"Primary {primary_provider_name}:{primary_model_name} failed after {MAX_RETRIES} retries ({MAX_ATTEMPTS} attempts); fallback attempt #{fallback_attempts} succeeded.",
                    }

                total_latency_ms = int((_time.time() - req_start_time) * 1000)
                duration_seconds = total_latency_ms / 1000.0

                # Record Prometheus Aggregated Metrics
                gateway_metrics.record_completed_request(
                    team_id=validation.team["id"],
                    model_requested=primary_model_name,
                    provider_served=curr_provider_name,
                    model_served=curr_model_name,
                    request_type=(req_type.value if hasattr(req_type, "value") else str(req_type)),
                    duration_seconds=duration_seconds,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=cost,
                    fallback_used=fallback_used,
                    primary_provider=primary_provider_name,
                )

                # response_delivery span
                with gateway_tracer.start_span("response_delivery") as deliv_span:
                    gateway_tracer.set_attributes(
                        deliv_span,
                        {
                            attrs.PROVIDER_SERVED: curr_provider_name,
                            attrs.MODEL_SERVED: curr_model_name,
                            attrs.LATENCY_MS: total_latency_ms,
                            attrs.FALLBACK_USED: fallback_used,
                            attrs.HTTP_STATUS: 200,
                        },
                    )


                # Summary Attribute Aggregation on Root gateway_request Span
                gateway_tracer.set_attributes(
                    root_span,
                    {
                        attrs.TEAM_ID: validation.team["id"],
                        attrs.PROVIDER_REQUESTED: primary_provider_name,
                        attrs.MODEL_REQUESTED: primary_model_name,
                        attrs.PROVIDER_SERVED: curr_provider_name,
                        attrs.MODEL_SERVED: curr_model_name,
                        attrs.INPUT_TOKENS: in_tok,
                        attrs.OUTPUT_TOKENS: out_tok,
                        attrs.TOTAL_TOKENS: tot_tok,
                        attrs.LATENCY_MS: total_latency_ms,
                        attrs.ESTIMATED_COST: cost,
                        attrs.FALLBACK_USED: fallback_used,
                        attrs.RETRY_COUNT: retry_count,
                    },
                )

                return response

            # All retries exhausted for curr_provider -> Record 1 request failure in Circuit Breaker
            await self.circuit_breaker.record_failure(curr_provider_name, curr_model_name, is_canary=is_canary)

            if not automatic_routing:
                raise last_exception or RuntimeError(f"Provider {curr_provider_name} failed after retries.")

            # Trigger Fallback Manager
            res = await self.fallback.get_next_candidate(
                team_id=validation.team["id"],
                primary_model_name=primary_model_name,
                attempted=attempted,
                fallback_attempts=fallback_attempts,
            )

            if res is None:
                raise RuntimeError(
                    f"No provider/model available for fallback after retries exhausted."
                ) from last_exception

            candidate, _ = res
            curr_provider_name = candidate["provider_name"]
            curr_model_name = candidate["model_name"]
            fallback_attempts += 1


    async def _route_stream(
        self,
        validation: ValidationResult,
        request: ChatRequest,
        automatic_routing: bool = True,
        estimated_tokens: int = 0,
    ) -> AsyncGenerator[StreamChunk, None]:
        attempted = set()

        provider_name = validation.provider["provider_name"]
        model_name = validation.model["model_name"]

        while True:

            attempted.add(
                (
                    provider_name,
                    model_name,
                )
            )

            provider = ProviderFactory.create(
                provider_name,
            )

            request.model = model_name

            # Health check before opening stream
            is_healthy = await provider.health_check()

            if not is_healthy:
                await provider.close()

                if not automatic_routing:
                    raise RuntimeError(f"Provider '{provider_name}' is unhealthy.")

                candidate = await self.fallback.get_next_candidate(
                    team_id=validation.team["id"],
                    attempted=attempted,
                )

                if candidate is None:
                    raise RuntimeError(
                        "No provider/model available for fallback."
                    )

                provider_name = candidate["provider_name"]
                model_name = candidate["model_name"]
                continue

            return self._stream_and_record_usage(
                provider, validation, request, estimated_tokens,
            )

    async def _stream_and_record_usage(
        self,
        provider: BaseProvider,
        validation: ValidationResult,
        request: ChatRequest,
        estimated_tokens: int = 0,
    ) -> AsyncGenerator[StreamChunk, None]:
        try:
            async for chunk in provider.chat_stream(request):
                yield chunk

            stream_result: StreamResult | None = getattr(provider, "stream_result", None)

            if stream_result and stream_result.usage is not None:
                usage = stream_result.usage
                input_price = float(validation.model.get("input_price_per_million_tokens") or 0.0)
                output_price = float(validation.model.get("output_price_per_million_tokens") or 0.0)

                cost = estimate_cost(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    input_price_per_1m=input_price,
                    output_price_per_1m=output_price,
                )

                await self.team_repository.add_usage(
                    team_id=validation.team["id"],
                    model_id=validation.model["id"],
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    estimated_cost=cost,
                )

                # TPM Refund after stream completes
                actual_cost = usage.input_tokens + usage.output_tokens
                refund = max(0, estimated_tokens - actual_cost)
                if refund > 0:
                    tma_id = validation.team_model_access["id"]
                    tpm_capacity = validation.team_model_access["tokens_per_minute"]
                    await self.rate_limiter.refund_tokens(
                        tma_id, tpm_capacity, refund,
                    )

        finally:
            await provider.close()