import asyncio
import os

from project.gateway.providers.gemini import GeminiProvider
from project.gateway.providers.groq import GroqProvider
from project.gateway.providers.openai import OpenAIProvider
from project.gateway.providers.anthropic import AnthropicProvider
from project.gateway.schemas.common import Message, Role
from project.gateway.schemas.request import ChatRequest
from project.gateway.providers.ollama import OllamaProvider


from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("OLLAMA_API_KEY")
print("API KEY:", repr(API_KEY))


async def main():

    provider = OllamaProvider(API_KEY)

    request = ChatRequest(
        model="gemma4",
        system_prompt="You are a helpful assistant.",
        messages=[
            Message(
                role=Role.USER,
                content="Who are you?Are you Ollama or Gemini? And what model am I using currently ? what are the models which I can use without a subscription"
            )
        ],
        temperature=0.7,
        max_tokens=100,
    )

    response = await provider.chat(request)

    print("\n========== RESPONSE ==========\n")

    print("Provider :", response.provider)
    print("Model    :", response.model)
    print("Reply    :", response.message.content)

    print("\n========== USAGE ==========\n")

    print(response.usage)

    await provider.close()


if __name__ == "__main__":
    asyncio.run(main())