"""
ollama.py

Ollama Cloud provider implementation.

This provider translates the gateway's standardized request/response
schemas into Ollama Cloud's REST API.
"""

import os

from dotenv import load_dotenv

from project.gateway.providers.http_provider import BaseHTTPProvider
from project.gateway.schemas.common import Message, Role, Usage
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.schemas.stream import StreamChunk

load_dotenv()


class OllamaProvider(BaseHTTPProvider):
    """
    Ollama Cloud implementation.

    Responsible only for translating between the gateway schema
    and Ollama Cloud's REST API.
    """

    BASE_URL = "https://ollama.com/api"
    PROVIDER_NAME = "ollama"

    def __init__(
        self,
        api_key: str | None = None,
    ):
        super().__init__(
            api_key=api_key or os.getenv("OLLAMA_API_KEY", ""),
        )

    def build_headers(self) -> dict[str, str]:
        """
        Return the HTTP headers required by Ollama Cloud.
        """

        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get_endpoint(
        self,
        request: ChatRequest,
    ) -> str:
        """
        Return the Ollama generation endpoint.
        """

        return "/generate"

    def get_health_endpoint(self) -> str:
        """
        Lightweight endpoint used for health checks.
        """

        return "/tags"

    def build_payload(
        self,
        request: ChatRequest,
    ) -> dict:
        """
        Convert ChatRequest into Ollama's request format.
        """

        prompt_parts = []

        if request.system_prompt:
            prompt_parts.append(
                f"System: {request.system_prompt}"
            )

        for message in request.messages:

            if message.role == Role.USER:
                role = "User"

            elif message.role == Role.ASSISTANT:
                role = "Assistant"

            else:
                continue

            prompt_parts.append(
                f"{role}: {message.content}"
            )

        payload = {
            "model": request.model,
            "prompt": "\n".join(prompt_parts),
            "stream": request.stream,
            "options": {
                "temperature": request.temperature,
            },
        }

        if request.max_tokens is not None:
            payload["options"]["num_predict"] = request.max_tokens

        return payload

    def parse_response(
        self,
        request: ChatRequest,
        response_json: dict,
    ) -> ChatResponse:
        """
        Convert Ollama's JSON response into ChatResponse.
        """

        usage = Usage(
            input_tokens=response_json.get(
                "prompt_eval_count",
                0,
            ),
            output_tokens=response_json.get(
                "eval_count",
                0,
            ),
            total_tokens=(
                response_json.get(
                    "prompt_eval_count",
                    0,
                )
                + response_json.get(
                    "eval_count",
                    0,
                )
            ),
        )

        return ChatResponse(
            provider=self.PROVIDER_NAME,
            model=request.model,
            message=Message(
                role=Role.ASSISTANT,
                content=response_json.get(
                    "response",
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
        Convert Ollama streaming JSON chunk into StreamChunk.
        """

        text = response_json.get("response", "") or ""
        if not text and "message" in response_json:
            text = response_json.get("message", {}).get("content", "") or ""

        done = response_json.get("done", False)
        finish_reason = "stop" if done else None

        usage = None
        if done and ("prompt_eval_count" in response_json or "eval_count" in response_json):
            prompt_tokens = response_json.get("prompt_eval_count", 0)
            eval_tokens = response_json.get("eval_count", 0)
            usage = Usage(
                input_tokens=prompt_tokens,
                output_tokens=eval_tokens,
                total_tokens=prompt_tokens + eval_tokens,
            )

        if text or finish_reason or usage:
            return StreamChunk(
                provider=self.PROVIDER_NAME,
                model=request.model,
                content=text,
                finish_reason=finish_reason,
                usage=usage,
            )

        return None