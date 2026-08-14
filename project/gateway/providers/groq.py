"""
Groq Provider

Implements the Groq Chat Completions API.

This provider translates between the gateway's standardized
schemas and Groq's OpenAI-compatible REST API.
"""

from project.gateway.providers.http_provider import BaseHTTPProvider
from project.gateway.schemas.common import Message, Role, Usage
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.schemas.stream import StreamChunk


class GroqProvider(BaseHTTPProvider):
    """
    Groq provider implementation.
    """

    BASE_URL = "https://api.groq.com"

    PROVIDER_NAME = "groq"

    # ---------------------------------------------------------
    # Provider Endpoints
    # ---------------------------------------------------------

    def get_endpoint(
        self,
        request: ChatRequest,
    ) -> str:
        """
        Returns the Chat Completions endpoint.
        """

        return "/openai/v1/chat/completions"

    def get_health_endpoint(self) -> str:
        """
        Endpoint used for provider health checks.

        We use the models endpoint because it is lightweight
        and requires authentication.
        """

        return "/openai/v1/models"

    # ---------------------------------------------------------
    # Request Builder
    # ---------------------------------------------------------

    def build_payload(
        self,
        request: ChatRequest,
    ) -> dict:
        """
        Convert ChatRequest into Groq's request format.
        """

        messages = []

        if request.system_prompt:

            messages.append(
                {
                    "role": "system",
                    "content": request.system_prompt,
                }
            )

        for message in request.messages:

            messages.append(
                {
                    "role": message.role.value,
                    "content": message.content,
                }
            )

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": request.stream,
        }

        if request.stream:
            payload["stream_options"] = {"include_usage": True}

        if request.max_tokens is not None:

            payload["max_completion_tokens"] = request.max_tokens

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
        Convert Groq's JSON response into ChatResponse.
        """

        choices = response_json.get("choices")

        if not choices:
            raise RuntimeError(
                "Groq returned no completion choices."
            )

        assistant_message = choices[0]["message"]

        usage_json = response_json.get(
            "usage",
            {},
        )

        usage = Usage(
            input_tokens=usage_json.get(
                "prompt_tokens",
                0,
            ),
            output_tokens=usage_json.get(
                "completion_tokens",
                0,
            ),
            total_tokens=usage_json.get(
                "total_tokens",
                0,
            ),
        )

        return ChatResponse(
            provider=self.PROVIDER_NAME,
            model=response_json.get(
                "model",
                request.model,
            ),
            message=Message(
                role=Role.ASSISTANT,
                content=assistant_message.get(
                    "content",
                    "",
                ),
            ),
            usage=usage,
        )

    def parse_stream_chunk(
        self,
        request: ChatRequest,
        response_json: dict,
    ) -> StreamChunk | None:
        """
        Convert Groq streaming JSON chunk into StreamChunk.
        """

        choices = response_json.get("choices", [])
        usage_json = response_json.get("usage")

        usage = None
        if usage_json:
            usage = Usage(
                input_tokens=usage_json.get("prompt_tokens", 0),
                output_tokens=usage_json.get("completion_tokens", 0),
                total_tokens=usage_json.get("total_tokens", 0),
            )

        if choices:
            choice = choices[0]
            delta = choice.get("delta", {})
            content = delta.get("content", "") or ""
            finish_reason = choice.get("finish_reason")

            if content or finish_reason or usage:
                return StreamChunk(
                    provider=self.PROVIDER_NAME,
                    model=request.model,
                    content=content,
                    finish_reason=finish_reason,
                    usage=usage,
                )
        elif usage:
            return StreamChunk(
                provider=self.PROVIDER_NAME,
                model=request.model,
                content="",
                finish_reason=None,
                usage=usage,
            )

        return None