"""Durable, customer-owned support chat conversations."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.order import Order
    from app.models.ticket import Ticket
    from app.models.support_message import SupportMessage


class SupportConversation(Base):
    __tablename__ = "support_conversations"
    __table_args__ = (
        Index("ix_support_conversations_customer_updated", "customer_id", "updated_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), nullable=False)
    selected_order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.order_id"), nullable=True)
    linked_ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.ticket_id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="OPEN")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=text("CURRENT_TIMESTAMP"))

    customer: Mapped["Customer"] = relationship(back_populates="conversations")
    selected_order: Mapped["Order | None"] = relationship(foreign_keys=[selected_order_id])
    linked_ticket: Mapped["Ticket | None"] = relationship(foreign_keys=[linked_ticket_id])
    messages: Mapped[list["SupportMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
