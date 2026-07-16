from pydantic import BaseModel
from project.gateway.schemas.common import Message, Usage

class ChatResponse(BaseModel):
    provider: str
    model: str
    message: Message
    usage: Usage