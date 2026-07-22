"""
Base HTTP Provider

This class implements the common HTTP workflow shared by all
LLM providers.

Every provider only needs to implement:

    - get_endpoint()
    - build_payload()
    - parse_response()

Everything else (authentication, HTTP requests, response status
checking, etc.) is handled here.
"""

from project.gateway.schemas import response
from abc import abstractmethod

import httpx

from project.gateway.providers.base import BaseProvider
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse


class BaseHTTPProvider(BaseProvider):
    """
    Base class for all HTTP-based providers.

    Handles:
        - HTTP client
        - Authorization
        - Sending requests
        - Error checking

    Leaves provider-specific request/response translation
    to subclasses.
    """

    BASE_URL: str = ""

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
        '''
        import json

        print(json.dumps(payload, indent=2))
        '''
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