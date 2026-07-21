"""
Provider Registry

The registry maintains all available LLM providers.

Instead of instantiating providers throughout the codebase,
the gateway registers them once and retrieves them by name.

This makes it easy to add or replace providers without changing
the gateway logic.
"""

from project.gateway.providers.base import BaseProvider


class ProviderRegistry:
    """
    Stores and manages provider instances.

    Example:
        registry = ProviderRegistry()

        registry.register("gemini", GeminiProvider(...))

        provider = registry.get("gemini")
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider) -> None:
        """
        Register a provider instance.

        Raises:
            ValueError:
                If the provider name is already registered.
        """

        name = name.lower()

        if name in self._providers:
            raise ValueError(f"Provider '{name}' is already registered.")

        self._providers[name] = provider

    def get(self, name: str) -> BaseProvider:
        """
        Retrieve a provider by name.

        Raises:
            ValueError:
                If the provider is not registered.
        """

        name = name.lower()

        provider = self._providers.get(name)

        if provider is None:
            raise ValueError(f"Unknown provider '{name}'.")

        return provider

    def list_providers(self) -> list[str]:
        """
        Return all registered provider names.
        """

        return sorted(self._providers.keys())

    def unregister(self, name: str) -> None:
        """
        Remove a provider from the registry.
        """

        name = name.lower()

        self._providers.pop(name, None)

    def exists(self, name: str) -> bool:
        """
        Check whether a provider is registered.
        """

        return name.lower() in self._providers