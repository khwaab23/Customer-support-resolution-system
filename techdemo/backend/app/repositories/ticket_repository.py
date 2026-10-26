from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket


class TicketRepository:
    """Persistence and read queries for customer support tickets."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, ticket: Ticket) -> Ticket:
        self._session.add(ticket)
        return ticket

    def get_by_id(self, ticket_id: str) -> Ticket | None:
        statement = select(Ticket).where(Ticket.ticket_id == ticket_id)
        return self._session.scalar(statement)

    def get_by_id_for_customer(self, customer_id: str, ticket_id: str) -> Ticket | None:
        statement = select(Ticket).where(
            Ticket.ticket_id == ticket_id,
            Ticket.customer_id == customer_id,
        )
        return self._session.scalar(statement)

    def list_by_customer(self, customer_id: str, limit: int = 10) -> list[Ticket]:
        if limit <= 0:
            return []

        statement = (
            select(Ticket)
            .where(Ticket.customer_id == customer_id)
            .order_by(Ticket.created_at.desc(), Ticket.ticket_id.asc())
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    def is_owned_by_customer(self, customer_id: str, ticket_id: str) -> bool:
        statement = select(Ticket.ticket_id).where(
            Ticket.ticket_id == ticket_id,
            Ticket.customer_id == customer_id,
        )
        return self._session.scalar(statement) is not None
