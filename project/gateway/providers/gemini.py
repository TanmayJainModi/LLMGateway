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
                #"thinkingConfig": {
                #    "thinkingBudget": 0
                #}
                
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
    # Response Parser
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

        '''
        import json

        print(json.dumps(response_json, indent=2))
        '''

        return ChatResponse(
            provider=self.PROVIDER_NAME,
            model=request.model,
            message=Message(
                role=Role.ASSISTANT,
                content=text,
            ),
            usage=usage,
        )