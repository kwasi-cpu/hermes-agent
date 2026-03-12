from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass
class InternalAuthContext:
    tenant_id: Optional[str]
    user_sub: str
    user_email: Optional[str]
    role: Optional[str]
    request_id: str


class InternalChatStreamRequest(BaseModel):
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=12000)
    client_message_id: Optional[str] = Field(default=None, max_length=128)
