"""
exporter.py

Prometheus HTTP Exporter utility for scraping gateway metrics at /metrics.
"""

from prometheus_client import generate_latest
from project.gateway.telemetry.metrics import REGISTRY


def get_prometheus_metrics_bytes() -> bytes:
    """
    Generates Prometheus plaintext format output for /metrics scraping endpoint.
    """
    return generate_latest(REGISTRY)
