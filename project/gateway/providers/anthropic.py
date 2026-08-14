"""
anthropic.py

Anthropic Claude provider implementation.

This provider translates the gateway's standardized request/response
schemas into Anthropic's Messages API.
"""

import os

from dotenv import load_dotenv

from project.gateway.providers.http_provider import BaseHTTPProvider
from project.gateway.schemas.common import Message, Role, Usage
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.schemas.stream import StreamChunk

load_dotenv()


class AnthropicProvider(BaseHTTPProvider):
    """
    Anthropic Claude implementation.
    """

    BASE_URL = "https://api.anthropic.com/v1"
    PROVIDER_NAME = "anthropic"

    def __init__(self, api_key: str | None = None):
        super().__init__(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY", ""),
        )
        self._current_input_tokens = 0

    # ---------------------------------------------------------
    # BaseHTTPProvider methods
    # ---------------------------------------------------------

    def get_endpoint(
        self,
        request: ChatRequest,
    ) -> str:
        return "/messages"

    def build_headers(self) -> dict:
        """
        Anthropic authentication headers.
        """

        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def build_payload(
        self,
        request: ChatRequest,
    ) -> dict:
        """
        Convert ChatRequest into Anthropic's request format.

        Anthropic requires alternating user/assistant turns.
        Consecutive messages from the same role are merged into
        a single message separated by blank lines.
        """

        merged_messages = []

        for message in request.messages:

            # First message
            if not merged_messages:
                merged_messages.append(
                    {
                        "role": message.role.value,
                        "content": message.content,
                    }
                )
                continue

            previous = merged_messages[-1]

            # Merge consecutive messages having the same role
            if previous["role"] == message.role.value:
                previous["content"] += "\n\n" + message.content
            else:
                merged_messages.append(
                    {
                        "role": message.role.value,
                        "content": message.content,
                    }
                )

        payload = {
            "model": request.model,
            "messages": merged_messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or 1024,
            "stream": request.stream,
        }

        if request.system_prompt:
            payload["system"] = request.system_prompt

        return payload

    def parse_response(
        self,
        request: ChatRequest,
        response_json: dict,
    ) -> ChatResponse:
        """
        Convert Anthropic response into the gateway's ChatResponse.
        """

        text = ""

        for block in response_json.get("content", []):

            if block.get("type") == "text":
                text += block.get("text", "")

        usage_json = response_json.get("usage", {})

        input_tokens = usage_json.get(
            "input_tokens",
            0,
        )

        output_tokens = usage_json.get(
            "output_tokens",
            0,
        )

        usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

        return ChatResponse(
            provider=self.PROVIDER_NAME,
            model=response_json.get(
                "model",
                request.model,
            ),
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
        Convert Anthropic streaming JSON chunk into StreamChunk.
        """

        event_type = response_json.get("type")

        if event_type == "message_start":
            message_obj = response_json.get("message", {})
            usage_obj = message_obj.get("usage", {})
            self._current_input_tokens = usage_obj.get("input_tokens", 0)
            return None

        elif event_type == "content_block_delta":
            delta = response_json.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                return StreamChunk(
                    provider=self.PROVIDER_NAME,
                    model=request.model,
                    content=text,
                )

        elif event_type == "message_delta":
            usage_obj = response_json.get("usage", {})
            output_tokens = usage_obj.get("output_tokens", 0)
            input_tokens = getattr(self, "_current_input_tokens", 0)
            total_tokens = input_tokens + output_tokens
            usage = Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
            delta = response_json.get("delta", {})
            stop_reason = delta.get("stop_reason")
            return StreamChunk(
                provider=self.PROVIDER_NAME,
                model=request.model,
                content="",
                finish_reason=stop_reason,
                usage=usage,
            )

        return None

    def get_health_endpoint(self) -> str:
        """
        Endpoint used by the generic health_check() implementation.
        """
        return "/models"