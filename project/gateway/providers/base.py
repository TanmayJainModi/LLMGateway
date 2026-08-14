"""
base.py

Defines the abstract interface that every LLM provider must implement.

The gateway interacts only with BaseProvider and never directly depends on
provider-specific implementations such as GeminiProvider or OpenAIProvider.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.schemas.stream import StreamChunk


class BaseProvider(ABC):
    """
    Abstract base class for every LLM provider.

    Stores the provider API key and defines the common interface
    implemented by all providers.
    """

    def __init__(self, api_key: str):
        """
        Store the provider API key.

        Every provider authenticates differently, but every provider
        needs access to an API key.
        """

        self.api_key = api_key

    @abstractmethod
    async def chat(
        self,
        request: ChatRequest,
    ) -> ChatResponse:
        """
        Execute a chat completion request.
        """
        raise NotImplementedError

    @abstractmethod
    async def chat_stream(
        self,
        request: ChatRequest,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute a streaming chat completion request.
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Verify that the provider is reachable.
        """
        raise NotImplementedError