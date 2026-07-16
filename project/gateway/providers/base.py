"""
base.py

Defines the abstract interface that every LLM provider must implement.

The gateway interacts only with BaseProvider and never directly depends on
provider-specific implementations such as GeminiProvider or OpenAIProvider.
"""

from abc import ABC, abstractmethod

from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse


class BaseProvider(ABC):
    """
    Abstract base class for every LLM provider.

    Every provider must implement these methods so that the gateway
    can interact with all providers through one common interface.
    """

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Send a chat completion request to the provider.

        Parameters
        ----------
        request : ChatRequest
            Standardized gateway request.

        Returns
        -------
        ChatResponse
            Standardized gateway response.
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check whether the provider is reachable.

        Returns
        -------
        bool
            True if the provider is healthy, otherwise False.
        """
        raise NotImplementedError