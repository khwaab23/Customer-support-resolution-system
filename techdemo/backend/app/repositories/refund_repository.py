from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.refund import Refund


class RefundRepository:
    """Read-only historical refund lookups backed by a caller-provided session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_order_id(self, order_id: str) -> list[Refund]:
        statement = (
            select(Refund)
            .where(Refund.order_id == order_id)
            .order_by(Refund.created_at.desc(), Refund.refund_id.asc())
        )
        return list(self._session.scalars(statement))
