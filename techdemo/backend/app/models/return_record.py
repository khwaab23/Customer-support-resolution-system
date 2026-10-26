from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.order_item import OrderItem
    from app.models.refund import Refund


class ReturnRecord(Base):
    """ORM mapping for the existing returns table."""

    __tablename__ = "returns"

    return_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id", name="returns_order_id_fkey"),
        nullable=False,
    )
    order_item_id: Mapped[str] = mapped_column(
        ForeignKey("order_items.order_item_id", name="returns_order_item_id_fkey"),
        nullable=False,
    )
    requested_at: Mapped[date] = mapped_column(Date, nullable=False)
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    inspection_status: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="returns")
    order_item: Mapped["OrderItem"] = relationship(back_populates="returns")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="return_record")
