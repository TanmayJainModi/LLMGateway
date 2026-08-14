"""
openai.py

OpenAI provider implementation.

Implements the OpenAI Responses API while exposing the gateway's
standardized ChatRequest and ChatResponse interface.
"""

from dotenv import load_dotenv

from project.gateway.providers.http_provider import BaseHTTPProvider
from project.gateway.schemas.common import Message, Role, Usage
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.schemas.stream import StreamChunk

load_dotenv()


class OpenAIProvider(BaseHTTPProvider):
    """
    OpenAI Responses API provider.
    """

    BASE_URL = "https://api.openai.com/v1"

    PROVIDER_NAME = "openai"

    def get_endpoint(
        self,
        request: ChatRequest,
    ) -> str:
        return "/responses"

    def build_payload(
        self,
        request: ChatRequest,
    ) -> dict:
        """
        Convert ChatRequest into OpenAI Responses API format.
        """

        payload = {
            "model": request.model,
            "input": [],
            "temperature": request.temperature,
            "stream": request.stream,
        }

        if request.max_tokens is not None:
            payload["max_output_tokens"] = request.max_tokens

        if request.system_prompt:
            payload["instructions"] = request.system_prompt

        for message in request.messages:
            payload["input"].append(
                {
                    "role": message.role.value,
                    "content": [
                        {
                            "type": "input_text",
                            "text": message.content,
                        }
                    ],
                }
            )

        return payload

    def parse_response(
        self,
        request: ChatRequest,
        response_json: dict,
    ) -> ChatResponse:
        """
        Convert OpenAI Responses API response into ChatResponse.
        """

        text = ""

        for item in response_json.get("output", []):

            if item.get("type") != "message":
                continue

            for content in item.get("content", []):

                if content.get("type") == "output_text":
                    text += content.get("text", "")

        usage_json = response_json.get("usage", {})

        usage = Usage(
            input_tokens=usage_json.get("input_tokens", 0),
            output_tokens=usage_json.get("output_tokens", 0),
            total_tokens=usage_json.get("total_tokens", 0),
        )

        return ChatResponse(
            provider=self.PROVIDER_NAME,
            model=response_json.get("model", request.model),
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
        Convert OpenAI streaming JSON chunk into StreamChunk.
        """

        event_type = response_json.get("type")

        if event_type == "response.output_text.delta":
            delta_text = response_json.get("delta", "")
            return StreamChunk(
                provider=self.PROVIDER_NAME,
                model=request.model,
                content=delta_text,
            )

        elif event_type == "response.completed":
            usage_data = response_json.get("response", {}).get("usage", {})
            usage = None
            if usage_data:
                usage = Usage(
                    input_tokens=usage_data.get("input_tokens", 0),
                    output_tokens=usage_data.get("output_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )
            return StreamChunk(
                provider=self.PROVIDER_NAME,
                model=request.model,
                content="",
                finish_reason="completed",
                usage=usage,
            )

        # Fallback for standard OpenAI Chat Completions streaming format if used
        choices = response_json.get("choices", [])
        if choices:
            choice = choices[0]
            delta = choice.get("delta", {})
            content = delta.get("content", "") or ""
            finish_reason = choice.get("finish_reason")
            usage_json = response_json.get("usage")
            usage = None
            if usage_json:
                usage = Usage(
                    input_tokens=usage_json.get("prompt_tokens", 0),
                    output_tokens=usage_json.get("completion_tokens", 0),
                    total_tokens=usage_json.get("total_tokens", 0),
                )
            if content or finish_reason or usage:
                return StreamChunk(
                    provider=self.PROVIDER_NAME,
                    model=request.model,
                    content=content,
                    finish_reason=finish_reason,
                    usage=usage,
                )

        return None

    def get_health_endpoint(self) -> str:
        """
        Endpoint used by the generic health_check() implementation.
        """
        return "/models"