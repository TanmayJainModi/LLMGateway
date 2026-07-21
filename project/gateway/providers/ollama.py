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

load_dotenv()


class OllamaProvider(BaseHTTPProvider):
    """
    Ollama Cloud implementation.

    Responsible only for translating between the gateway schema
    and Ollama Cloud's REST API.
    """

    BASE_URL = "https://ollama.com/api"

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
            "stream": False,
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
            provider="ollama",
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