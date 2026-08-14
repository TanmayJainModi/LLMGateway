"""
tracer.py

OpenTelemetry Distributed Tracing manager for the LLM Gateway.
Provides context management, span creation, and attribute aggregation.
"""

from contextlib import contextmanager
from typing import Generator
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, Span
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
try:
    from opentelemetry.sdk.trace.export import InMemorySpanExporter
except ImportError:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter



class GatewayTracer:
    """
    OpenTelemetry Tracer for LLM Gateway pipeline operations.
    """

    def __init__(self):
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.processor = SimpleSpanProcessor(self.exporter)
        self.provider.add_span_processor(self.processor)
        self.tracer = self.provider.get_tracer("llm_gateway.telemetry", "1.0.0")

    def get_tracer(self):
        return self.tracer

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: dict[str, any] | None = None,
    ) -> Generator[Span, None, None]:
        """
        Context manager to create, auto-attribute, and close a telemetry span.
        """
        with self.tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    if v is not None:
                        span.set_attribute(k, v)
            yield span

    @staticmethod
    def set_attributes(span: Span, attributes: dict[str, any]) -> None:
        """
        Inject attributes into an active span.
        """
        if span and attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, v)

    @staticmethod
    def add_event(span: Span, name: str, attributes: dict[str, any] | None = None) -> None:
        """
        Record a child event within an active span.
        """
        if span:
            span.add_event(name, attributes=attributes or {})


# Singleton tracer instance
gateway_tracer = GatewayTracer()
