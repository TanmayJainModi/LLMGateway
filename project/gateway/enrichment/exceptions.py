"""
exceptions.py

Exceptions raised by the RequestEnricher.
"""


class EnrichmentError(Exception):
    """
    Base exception for request enrichment errors.
    """
    pass


class PolicyViolationError(EnrichmentError):
    """
    Raised when user message content violates team keyword filtering policies.
    """
    pass
