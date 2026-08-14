from enum import Enum
from pydantic import BaseModel, Field
from project.gateway.schemas.common import Message


class RequestType(str, Enum):
    STREAM = "stream"
    CHAT = "chat"
    BATCH = "batch"


class ChatRequest(BaseModel):
    model: str
    system_prompt: str | None = None
    messages: list[Message]
    temperature: float = 0.7
    max_tokens: int | None = None
    stream: bool = False
    request_type: RequestType | None = None