from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.order import Order


class Shipment(Base):
    """ORM mapping for the existing shipments table."""

    __tablename__ = "shipments"

    shipment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id", name="shipments_order_id_fkey"),
        nullable=False,
    )
    carrier: Mapped[str] = mapped_column(String(80), nullable=False)
    tracking_number: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    shipped_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivered_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_delivery_at: Mapped[date] = mapped_column(Date, nullable=False)
    last_updated_at: Mapped[date] = mapped_column(Date, nullable=False)
    service_available: Mapped[bool] = mapped_column(Boolean, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="shipments")
