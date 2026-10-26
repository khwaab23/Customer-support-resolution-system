from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.return_record import ReturnRecord


class ReturnRepository:
    """Read-only return records, with their required order item loaded."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_order_id(self, order_id: str) -> list[ReturnRecord]:
        statement = (
            select(ReturnRecord)
            .options(joinedload(ReturnRecord.order_item))
            .where(ReturnRecord.order_id == order_id)
            .order_by(ReturnRecord.requested_at.desc(), ReturnRecord.return_id.asc())
        )
        return list(self._session.scalars(statement))
