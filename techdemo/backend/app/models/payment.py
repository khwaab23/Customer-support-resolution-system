from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, CheckConstraint, Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.refund import Refund


class Payment(Base):
    """ORM mapping for the existing payments table."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_minor >= 0", name="payments_amount_minor_check"),
        Index("idx_payments_order_id", "order_id"),
    )

    payment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id", name="payments_order_id_fkey"),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    captured_at: Mapped[date] = mapped_column(Date, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="payments")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment")
