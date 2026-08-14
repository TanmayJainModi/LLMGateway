from typing import Optional
from pydantic import BaseModel
from project.gateway.schemas.common import Usage


class StreamChunk(BaseModel):
    provider: str
    model: str
    content: str
    finish_reason: Optional[str] = None
    usage: Optional[Usage] = None


class StreamResult(BaseModel):
    provider: str
    model: str
    full_text: str
    usage: Optional[Usage] = None
    finish_reason: Optional[str] = None
