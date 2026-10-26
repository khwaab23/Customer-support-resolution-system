from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TicketCreateRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=30)
    message: str = Field(min_length=1, max_length=5000)

    @field_validator("order_id", "message")
    @classmethod
    def non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class TicketResponse(BaseModel):
    """Customer-visible ticket fields only; internal triage data remains private."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    order_id: str | None
    message: str
    status: str
    created_at: datetime


class TicketListResponse(BaseModel):
    tickets: list[TicketResponse]
