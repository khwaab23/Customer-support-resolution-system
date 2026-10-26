from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.return_record import ReturnRecord


class OrderItem(Base):
    """ORM mapping for the existing order_items table."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(
            "line_total_minor = (quantity * unit_price_minor)",
            name="order_items_check",
        ),
        CheckConstraint("quantity > 0", name="order_items_quantity_check"),
        CheckConstraint("unit_price_minor >= 0", name="order_items_unit_price_minor_check"),
        Index("idx_order_items_order_id", "order_id"),
        Index("idx_order_items_product_id", "product_id"),
    )

    order_item_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id", name="order_items_order_id_fkey"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", name="order_items_product_id_fkey"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    returns: Mapped[list["ReturnRecord"]] = relationship(back_populates="order_item")
