from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, CheckConstraint, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer


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
