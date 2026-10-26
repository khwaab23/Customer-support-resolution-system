from typing import TYPE_CHECKING

from sqlalchemy import CHAR, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.ticket import Ticket


class Customer(Base):
    """ORM mapping for the existing customers table."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("email", name="customers_email_key"),)

    customer_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    account_status: Mapped[str] = mapped_column(String(30), nullable=False)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="customer")
