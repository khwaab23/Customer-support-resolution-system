from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.shipment import Shipment


class ShipmentRepository:
    """Read-only shipment queries backed by a caller-provided session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_order_id(self, order_id: str) -> list[Shipment]:
        """Return every shipment for an order in deterministic recency order."""
        statement = (
            select(Shipment)
            .where(Shipment.order_id == order_id)
            .order_by(Shipment.last_updated_at.desc(), Shipment.shipment_id.asc())
        )
        return list(self._session.scalars(statement))
