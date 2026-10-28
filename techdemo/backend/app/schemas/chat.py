from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatSenderRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    ASSISTANT = "ASSISTANT"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class ConversationStatus(str, Enum):
    OPEN = "OPEN"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"


class ChatConversationCreateRequest(BaseModel):
    selected_order_id: str | None = Field(default=None, max_length=30)


class ChatOrderSelectionRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=30)


class ChatMessageCreateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    client_request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("message")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: UUID
    sender_role: ChatSenderRole
    message_text: str
    created_at: datetime
    metadata: dict | None = None


class ChatConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: UUID
    selected_order_id: str | None
    linked_ticket_id: str | None
    status: ConversationStatus
    version: int
    created_at: datetime
    updated_at: datetime
    review_status: str | None = None


class ChatConversationDetailResponse(ChatConversationResponse):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatConversationListResponse(BaseModel):
    conversations: list[ChatConversationResponse]
    offset: int
    limit: int


class ChatMessageListResponse(BaseModel):
    messages: list[ChatMessageResponse]
    offset: int
    limit: int


class ChatTurnResponse(BaseModel):
    conversation: ChatConversationResponse
    customer_message: ChatMessageResponse
    assistant_message: ChatMessageResponse | None = None
    idempotent_replay: bool = False
