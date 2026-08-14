"""
Base HTTP Provider

This class implements the common HTTP workflow shared by all
LLM providers.

Every provider only needs to implement:

    - get_endpoint()
    - build_payload()
    - parse_response()
    - parse_stream_chunk()

Everything else (authentication, HTTP requests, response status
checking, streaming SSE parsing, etc.) is handled here.
"""

from abc import abstractmethod
import json
from typing import AsyncGenerator

import httpx

from project.gateway.providers.base import BaseProvider
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.schemas.stream import StreamChunk, StreamResult


class BaseHTTPProvider(BaseProvider):
    """
    Base class for all HTTP-based providers.

    Handles:
        - HTTP client
        - Authorization
        - Sending requests
        - Error checking
        - Streaming SSE/JSON parsing

    Leaves provider-specific request/response translation
    to subclasses.
    """

    BASE_URL: str = ""
    PROVIDER_NAME: str = ""

    def __init__(
        self,
        api_key: str,
        timeout: float = 60.0,
    ):
        super().__init__(api_key)

        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
        )
        self.stream_result: StreamResult | None = None

    # ---------------------------------------------------------
    # Abstract methods every provider must implement
    # ---------------------------------------------------------

    @abstractmethod
    def get_endpoint(
        self,
        request: ChatRequest,
    ) -> str:
        """
        Returns the endpoint for this request.
        """
        pass

    @abstractmethod
    def build_payload(
        self,
        request: ChatRequest,
    ) -> dict:
        """
        Converts ChatRequest into the provider's request format.
        """
        pass

    @abstractmethod
    def parse_response(
        self,
        request: ChatRequest,
        response_json: dict,
    ) -> ChatResponse:
        """
        Converts provider JSON into ChatResponse.
        """
        pass

    @abstractmethod
    def parse_stream_chunk(
        self,
        request: ChatRequest,
        response_json: dict,
    ) -> StreamChunk | None:
        """
        Converts provider streaming JSON chunk into StreamChunk.
        """
        pass

    def get_stream_endpoint(
        self,
        request: ChatRequest,
    ) -> str:
        """
        Returns the endpoint used for streaming.
        Defaults to get_endpoint(request).
        """
        return self.get_endpoint(request)

    # ---------------------------------------------------------
    # Common helpers
    # ---------------------------------------------------------

    def build_headers(self) -> dict:
        """
        Default headers.

        Most providers use Bearer authentication.
        Providers with different authentication
        can override this method.
        """

        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def post(
        self,
        endpoint: str,
        payload: dict,
    ) -> dict:
        """
        Sends a POST request and returns JSON.
        """

        response = await self.client.post(
            endpoint,
            headers=self.build_headers(),
            json=payload,
        )

        if response.is_error:
            raise RuntimeError(
                f"""
        Status Code : {response.status_code}

        Response :
        {response.text}
        """
            )
        return response.json()

    # ---------------------------------------------------------
    # Generic chat workflow
    # ---------------------------------------------------------

    async def chat(
        self,
        request: ChatRequest,
    ) -> ChatResponse:
        """
        Generic chat workflow.

        Every provider follows:

            ChatRequest
                ↓
            build_payload()
                ↓
            POST
                ↓
            parse_response()
                ↓
            ChatResponse
        """

        endpoint = self.get_endpoint(request)

        payload = self.build_payload(request)

        response_json = await self.post(
            endpoint=endpoint,
            payload=payload,
        )

        return self.parse_response(
            request,
            response_json,
        )

    async def chat_stream(
        self,
        request: ChatRequest,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Generic streaming workflow.

        Opens HTTP stream, reads SSE / JSON lines, invokes
        parse_stream_chunk, yields StreamChunk, and accumulates
        stream_result internally.
        """

        endpoint = self.get_stream_endpoint(request)

        payload = self.build_payload(request)

        headers = self.build_headers()

        self.stream_result = StreamResult(
            provider=getattr(self, "PROVIDER_NAME", "unknown"),
            model=request.model,
            full_text="",
            usage=None,
            finish_reason=None,
        )

        async with self.client.stream(
            "POST",
            endpoint,
            headers=headers,
            json=payload,
        ) as response:
            if response.is_error:
                error_bytes = await response.aread()
                raise RuntimeError(
                    f"Status Code : {response.status_code}\n\nResponse :\n{error_bytes.decode('utf-8')}"
                )

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line.startswith("event:"):
                    continue

                if line.startswith("data:"):
                    line = line[5:].strip()

                if line == "[DONE]":
                    break

                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                chunk = self.parse_stream_chunk(request, data)
                if chunk is not None:
                    if chunk.content:
                        self.stream_result.full_text += chunk.content
                    if chunk.usage is not None:
                        self.stream_result.usage = chunk.usage
                    if chunk.finish_reason is not None:
                        self.stream_result.finish_reason = chunk.finish_reason
                    yield chunk

    async def close(self):
        """
        Close the HTTP client.
        """

        await self.client.aclose()

    @abstractmethod
    def get_health_endpoint(self) -> str:
        """
        Endpoint used to verify provider health.
        """
        pass

    async def health_check(self) -> bool:
        """
        Returns True if the provider is reachable.
        """

        try:

            response = await self.client.get(
                self.get_health_endpoint(),
                headers=self.build_headers(),
            )

            response.raise_for_status()

            return True

        except Exception:

            return False