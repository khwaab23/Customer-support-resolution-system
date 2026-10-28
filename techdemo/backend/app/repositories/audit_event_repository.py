from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


class AuditEventRepository:
    """Small append-only repository for review-decision audit events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: AuditEvent) -> AuditEvent:
        self._session.add(event)
        return event

    def list_for_ticket(self, ticket_id: str) -> list[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.ticket_id == ticket_id)
            .order_by(AuditEvent.recorded_at.desc(), AuditEvent.event_id.asc())
        )
        return list(self._session.scalars(statement))
