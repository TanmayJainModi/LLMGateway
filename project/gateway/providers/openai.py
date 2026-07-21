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

    

    def get_health_endpoint(self) -> str:
        """
        Endpoint used by the generic health_check() implementation.
        """
        return "/models"