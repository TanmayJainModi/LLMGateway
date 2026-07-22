"""
provider_factory.py

Creates provider instances from a provider name.

The router never imports provider classes directly.
Instead, it asks the factory to construct the correct provider.
"""

import os

from project.gateway.providers.gemini import GeminiProvider
from project.gateway.providers.groq import GroqProvider
from project.gateway.providers.openai import OpenAIProvider
from project.gateway.providers.anthropic import AnthropicProvider
from project.gateway.providers.ollama import OllamaProvider


class ProviderFactory:

    @staticmethod
    def create(provider_name: str):

        provider_name = provider_name.lower()

        if provider_name == "gemini":
            return GeminiProvider(
                os.getenv("GEMINI_API_KEY")
            )

        elif provider_name == "groq":
            return GroqProvider(
                os.getenv("GROQ_API_KEY")
            )

        elif provider_name == "openai":
            return OpenAIProvider(
                os.getenv("OPENAI_API_KEY")
            )

        elif provider_name == "anthropic":
            return AnthropicProvider(
                os.getenv("ANTHROPIC_API_KEY")
            )

        elif provider_name == "ollama":
            return OllamaProvider(
                os.getenv("OLLAMA_API_KEY")
            )

        raise ValueError(
            f"Unknown provider '{provider_name}'."
        )