from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order_item import OrderItem


class OrderItemRepository:
    """Read-only order-item lookups backed by a caller-provided session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_order_id(self, order_id: str) -> list[OrderItem]:
        statement = (
            select(OrderItem)
            .where(OrderItem.order_id == order_id)
            .order_by(OrderItem.order_item_id.asc())
        )
        return list(self._session.scalars(statement))
