from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment import Payment


class PaymentRepository:
    """Read-only payment lookups backed by a caller-provided session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_order_id(self, order_id: str) -> list[Payment]:
        statement = (
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.captured_at.desc(), Payment.payment_id.asc())
        )
        return list(self._session.scalars(statement))
