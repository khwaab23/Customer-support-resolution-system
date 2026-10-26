from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.payment import Payment
    from app.models.return_record import ReturnRecord


class Refund(Base):
    """ORM mapping for the existing refunds table."""

    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="refunds_amount_minor_check"),
        UniqueConstraint("idempotency_key", name="refunds_idempotency_key_key"),
    )

    refund_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id", name="refunds_order_id_fkey"),
        nullable=False,
    )
    return_id: Mapped[str] = mapped_column(
        ForeignKey("returns.return_id", name="refunds_return_id_fkey"),
        nullable=False,
    )
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.payment_id", name="refunds_payment_id_fkey"),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(80), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="refunds")
    payment: Mapped["Payment"] = relationship(back_populates="refunds")
    return_record: Mapped["ReturnRecord"] = relationship(back_populates="refunds")
