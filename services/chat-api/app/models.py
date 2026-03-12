from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass
class AuthContext:
    tenant_id: Optional[str]
    user_sub: str
    user_email: Optional[str]
    role: Optional[str]


class ChatStreamRequest(BaseModel):
    conversation_id: Optional[UUID] = None
    message: str = Field(min_length=1, max_length=12000)
    client_message_id: Optional[str] = Field(default=None, max_length=128)


class InternalChatRequest(BaseModel):
    conversation_id: UUID
    message: str
    client_message_id: Optional[str] = None
