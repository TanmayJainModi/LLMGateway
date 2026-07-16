from pydantic import BaseModel, Field
from project.gateway.schemas.common import Message


class ChatRequest(BaseModel):
    model: str
    system_prompt: str | None = None
    messages: list[Message]
    temperature: float = 0.7
    max_tokens: int | None = None
    stream: bool = False