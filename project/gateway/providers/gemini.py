"""
gemini.py

Google Gemini provider implementation.

This provider translates the gateway's standardized request/response
schemas into the Google Gemini REST API.
"""

from project.gateway.providers.http_provider import BaseHTTPProvider
from project.gateway.schemas.common import Message, Role, Usage
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from dotenv import load_dotenv

load_dotenv()


class GeminiProvider(BaseHTTPProvider):
    """
    Google Gemini implementation.

    Responsible only for translating between the gateway schema
    and Gemini's REST API.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str):
        super().__init__(
            base_url=self.BASE_URL,
            api_key=api_key,
        )

    def _headers(self) -> dict[str, str]:
        """
        Return the HTTP headers required by Gemini.
        """

        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

    async def chat(
        self,
        request: ChatRequest,
    ) -> ChatResponse:
        """
        Execute a chat completion request.
        """

        self._validate_request(request)

        payload = self._build_payload(request)

        response = await self._post(
            endpoint=f"/models/{request.model}:generateContent",
            payload=payload,
        )

        return self._parse_response(
            request=request,
            response=response,
        )

    async def health_check(self) -> bool:
        """
        Verify that Gemini is reachable.

        Uses the lightweight models endpoint.
        """

        try:

            await self._get("/models")

            return True

        except Exception:

            return False

    def _validate_request(
        self,
        request: ChatRequest,
    ) -> None:
        """
        Validate the incoming ChatRequest.
        """

        if not request.model.strip():
            raise ValueError("Model name cannot be empty.")

        if not request.messages:
            raise ValueError(
                "At least one user message is required."
            )

        for message in request.messages:

            if message.role == Role.SYSTEM:
                raise ValueError(
                    "SYSTEM messages are not allowed inside "
                    "'messages'. Use 'system_prompt' instead."
                )

    def _build_payload(
        self,
        request: ChatRequest,
    ) -> dict:
        """
        Convert ChatRequest into Gemini's request format.
        """

        contents = []

        role_mapping = {
            Role.USER: "user",
            Role.ASSISTANT: "model",
        }

        for message in request.messages:

            contents.append(
                {
                    "role": role_mapping[message.role],
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

    def _parse_response(
        self,
        request: ChatRequest,
        response: dict,
    ) -> ChatResponse:
        """
        Convert Gemini's JSON response into ChatResponse.
        """

        candidates = response.get("candidates")

        if not candidates:
            raise RuntimeError(
                "Gemini returned no response candidates."
            )

        candidate = candidates[0]

        content = candidate.get("content")

        if content is None:
            raise RuntimeError(
                "Gemini response is missing content."
            )

        parts = content.get("parts")

        if not parts:
            raise RuntimeError(
                "Gemini response contains no parts."
            )

        text = parts[0].get("text", "")

        usage_metadata = response.get(
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
            provider="gemini",
            model=request.model,
            message=Message(
                role=Role.ASSISTANT,
                content=text,
            ),
            usage=usage,
        )