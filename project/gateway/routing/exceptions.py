"""
routing/exceptions.py

Exceptions raised by the Router.
"""


class RoutingError(Exception):
    """
    Base routing exception.
    """


class UnknownProviderError(RoutingError):
    """
    Raised when the requested provider
    is not supported by the router.
    """


class ProviderUnavailableError(RoutingError):
    """
    Raised when the provider cannot
    currently serve requests.
    """


class NoFallbackAvailableError(RoutingError):
    """
    Raised when automatic routing is enabled
    but no fallback provider can be found.
    """