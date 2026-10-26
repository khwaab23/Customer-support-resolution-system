from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order


class OrderRepository:
    """Read-only order queries backed by a caller-provided session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, order_id: str) -> Order | None:
        statement = select(Order).where(Order.order_id == order_id)
        return self._session.scalar(statement)

    def list_by_customer(self, customer_id: str, limit: int = 10) -> list[Order]:
        if limit <= 0:
            return []

        statement = (
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.ordered_at.desc(), Order.order_id.asc())
            .limit(limit)
        )
        return list(self._session.scalars(statement))
