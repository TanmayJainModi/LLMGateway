"""
http_provider.py

Provides a reusable HTTP implementation for cloud-based LLM providers.

This class centralizes HTTP communication so individual providers only
need to translate requests and responses between the gateway schema and
their respective APIs.
"""

from abc import abstractmethod

import httpx

from project.gateway.providers.base import BaseProvider


class BaseHTTPProvider(BaseProvider):
    """
    Base class for providers that communicate over HTTP.

    Responsibilities:
        - Manage the HTTP client.
        - Send GET and POST requests.
        - Apply provider-specific headers.
        - Handle HTTP errors.

    Child classes are responsible only for translating request and
    response formats.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

        # Reuse a single AsyncClient for all requests.
        self.client = httpx.AsyncClient(timeout=timeout)

    @abstractmethod
    def _headers(self) -> dict[str, str]:
        """
        Return provider-specific HTTP headers.

        Examples:
            Authorization: Bearer <API_KEY>

        or

            x-api-key: <API_KEY>

        Each provider implements this differently.
        """
        raise NotImplementedError

    async def _post(
        self,
        endpoint: str,
        payload: dict,
    ) -> dict:
        """
        Send an HTTP POST request.

        Parameters
        ----------
        endpoint:
            API endpoint relative to base_url.

        payload:
            JSON request body.

        Returns
        -------
        dict
            Parsed JSON response.
        """

        response = await self.client.post(
            url=f"{self.base_url}{endpoint}",
            headers=self._headers(),
            json=payload,
        )

        return self._handle_response(response)

    async def _get(
        self,
        endpoint: str,
    ) -> dict:
        """
        Send an HTTP GET request.

        Parameters
        ----------
        endpoint:
            API endpoint relative to base_url.

        Returns
        -------
        dict
            Parsed JSON response.
        """

        response = await self.client.get(
            url=f"{self.base_url}{endpoint}",
            headers=self._headers(),
        )

        return self._handle_response(response)

    def _handle_response(
        self,
        response: httpx.Response,
    ) -> dict:
        """
        Validate the HTTP response and return the JSON body.

        All providers use the same HTTP error handling logic, keeping
        provider implementations clean.
        """

        try:
            response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Provider request failed "
                f"({response.status_code}): "
                f"{response.text}"
            ) from exc

        return response.json()

    async def close(self) -> None:
        """
        Close the underlying HTTP client.

        This should be called when the gateway shuts down to
        release network resources.
        """

        await self.client.aclose()