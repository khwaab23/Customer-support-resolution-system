from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.order import Order


class Ticket(Base):
    """ORM mapping for the existing customer support tickets table."""

    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", name="tickets_customer_id_fkey"),
        nullable=False,
    )
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.order_id", name="tickets_order_id_fkey"),
        nullable=True,
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expected_resolution: Mapped[str] = mapped_column(String(100), nullable=False)
    scenario_tag: Mapped[str] = mapped_column(String(100), nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="tickets")
    order: Mapped["Order | None"] = relationship(back_populates="tickets")
