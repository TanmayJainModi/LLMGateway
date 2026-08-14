"""
Google Gemini Provider

This provider converts the gateway's standardized request and
response schemas into Google's Gemini Generate Content API.

Responsibilities
----------------
- Build Gemini request payloads.
- Parse Gemini responses.
- Define Gemini-specific endpoints.
- Provide Gemini authentication headers.

Networking, retries and HTTP communication are handled by
BaseHTTPProvider.
"""

from project.gateway.providers.http_provider import BaseHTTPProvider
from project.gateway.schemas.common import Message, Role, Usage
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.schemas.stream import StreamChunk


class GeminiProvider(BaseHTTPProvider):
    """
    Google Gemini provider implementation.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    PROVIDER_NAME = "gemini"

    ROLE_MAPPING = {
        Role.USER: "user",
        Role.ASSISTANT: "model",
    }

    # ---------------------------------------------------------
    # Provider Endpoints
    # ---------------------------------------------------------

    def get_endpoint(
        self,
        request: ChatRequest,
    ) -> str:
        """
        Returns the Generate Content endpoint.
        """

        return f"/models/{request.model}:generateContent"

    def get_stream_endpoint(
        self,
        request: ChatRequest,
    ) -> str:
        """
        Returns the Stream Generate Content endpoint.
        """

        return f"/models/{request.model}:streamGenerateContent?alt=sse"

    def get_health_endpoint(self) -> str:
        """
        Lightweight endpoint used for health checks.
        """

        return "/models"

    # ---------------------------------------------------------
    # Authentication
    # ---------------------------------------------------------

    def build_headers(self) -> dict:
        """
        Gemini uses API-Key authentication instead of
        Bearer authentication.
        """

        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

    # ---------------------------------------------------------
    # Request Builder
    # ---------------------------------------------------------

    def build_payload(
        self,
        request: ChatRequest,
    ) -> dict:
        """
        Convert ChatRequest into Gemini's GenerateContentRequest.
        """

        contents = []

        for message in request.messages:

            contents.append(
                {
                    "role": self.ROLE_MAPPING[message.role],
                    "parts": [
                        {
                            "text": message.content,
                        }
                    ],
                }
            )

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
            },
        }

        if request.system_prompt:

            payload["systemInstruction"] = {
                "parts": [
                    {
                        "text": request.system_prompt,
                    }
                ]
            }

        if request.max_tokens is not None:

            payload["generationConfig"][
                "maxOutputTokens"
            ] = request.max_tokens

        return payload

    # ---------------------------------------------------------
    # Response Parsers
    # ---------------------------------------------------------

    def parse_response(
        self,
        request: ChatRequest,
        response_json: dict,
    ) -> ChatResponse:
        """
        Convert Gemini's JSON response into ChatResponse.
        """

        candidates = response_json.get("candidates")

        if not candidates:
            raise RuntimeError(
                "Gemini returned no candidates."
            )

        candidate = candidates[0]

        content = candidate.get("content")

        if content is None:
            raise RuntimeError(
                "Gemini response missing content."
            )

        parts = content.get("parts", [])

        if not parts:
            raise RuntimeError(
                "Gemini response contains no text."
            )

        text = parts[0].get("text", "")

        usage_metadata = response_json.get(
            "usageMetadata",
            {},
        )

        usage = Usage(
            input_tokens=usage_metadata.get(
                "promptTokenCount",
                0,
            ),
            output_tokens=usage_metadata.get(
                "candidatesTokenCount",
                0,
            ),
            total_tokens=usage_metadata.get(
                "totalTokenCount",
                0,
            ),
        )

        return ChatResponse(
            provider=self.PROVIDER_NAME,
            model=request.model,
            message=Message(
                role=Role.ASSISTANT,
                content=text,
            ),
            usage=usage,
        )

    def parse_stream_chunk(
        self,
        request: ChatRequest,
        response_json: dict,
    ) -> StreamChunk | None:
        """
        Convert Gemini streaming JSON chunk into StreamChunk.
        """

        candidates = response_json.get("candidates", [])
        usage_metadata = response_json.get("usageMetadata", {})

        usage = None
        if usage_metadata and ("promptTokenCount" in usage_metadata or "candidatesTokenCount" in usage_metadata):
            usage = Usage(
                input_tokens=usage_metadata.get("promptTokenCount", 0),
                output_tokens=usage_metadata.get("candidatesTokenCount", 0),
                total_tokens=usage_metadata.get("totalTokenCount", 0),
            )

        if candidates:
            candidate = candidates[0]
            content = candidate.get("content", {})
            parts = content.get("parts", []) if content else []
            text = parts[0].get("text", "") if parts else ""
            finish_reason = candidate.get("finishReason")
            if text or finish_reason or usage:
                return StreamChunk(
                    provider=self.PROVIDER_NAME,
                    model=request.model,
                    content=text,
                    finish_reason=finish_reason,
                    usage=usage,
                )

        # Interactions API stream format fallback
        if response_json.get("event_type") == "step.delta":
            delta = response_json.get("delta", {})
            if delta.get("type") == "text":
                return StreamChunk(
                    provider=self.PROVIDER_NAME,
                    model=request.model,
                    content=delta.get("text", ""),
                )
        elif response_json.get("event_type") == "interaction.completed":
            usage_data = response_json.get("interaction", {}).get("usage", {})
            usage = None
            if usage_data:
                usage = Usage(
                    input_tokens=usage_data.get("total_input_tokens", 0),
                    output_tokens=usage_data.get("total_output_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )
            return StreamChunk(
                provider=self.PROVIDER_NAME,
                model=request.model,
                content="",
                finish_reason="completed",
                usage=usage,
            )

        return None