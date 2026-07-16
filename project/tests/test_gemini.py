import asyncio
import os

from project.gateway.providers.gemini import GeminiProvider
from project.gateway.schemas.common import Message, Role
from project.gateway.schemas.request import ChatRequest


API_KEY = os.getenv("GEMINI_API_KEY")


async def main():

    provider = GeminiProvider(API_KEY)

    request = ChatRequest(
        model="gemini-2.5-flash",
        system_prompt="You are a helpful assistant.",
        messages=[
            Message(
                role=Role.USER,
                content="Who are you?"
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