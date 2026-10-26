from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, CheckConstraint, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.order_item import OrderItem
    from app.models.payment import Payment
    from app.models.refund import Refund
    from app.models.return_record import ReturnRecord
    from app.models.shipment import Shipment
    from app.models.ticket import Ticket


class Order(Base):
    """ORM mapping for the existing orders table."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_minor >= 0", name="orders_total_minor_check"),
    )

    order_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", name="orders_customer_id_fkey"),
        nullable=False,
    )
    ordered_at: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")
    returns: Mapped[list["ReturnRecord"]] = relationship(back_populates="order")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="order")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="order")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="order")
