from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.repositories.order_repository import OrderRepository
from app.repositories.ticket_repository import TicketRepository

INITIAL_STATUS = "OPEN"
INITIAL_CATEGORY = "GENERAL_SUPPORT"
INITIAL_SUBJECT = "Customer support request"
INITIAL_EXPECTED_RESOLUTION = "PENDING_TRIAGE"
INITIAL_SCENARIO_TAG = "customer_submitted"


class TicketOrderNotFoundError(Exception):
    """Raised when an order is absent or not owned by the authenticated customer."""


class TicketPersistenceError(Exception):
    """Raised after a failed ticket transaction has been rolled back."""


class TicketService:
    """Customer ticket policy and the write transaction boundary."""

    def __init__(
        self,
        ticket_repository: TicketRepository,
        order_repository: OrderRepository,
        session: Session,
    ) -> None:
        self._tickets = ticket_repository
        self._orders = order_repository
        self._session = session

    def create_customer_ticket(
        self,
        customer_id: str,
        order_id: str,
        message: str,
    ) -> Ticket:
        """Create one ticket and commit it only after order ownership is verified."""
        try:
            order = self._orders.get_by_id(order_id)
            if order is None or order.customer_id != customer_id:
                raise TicketOrderNotFoundError()

            ticket = Ticket(
                ticket_id=self._new_ticket_id(),
                customer_id=customer_id,
                order_id=order_id,
                category=INITIAL_CATEGORY,
                subject=INITIAL_SUBJECT,
                message=message,
                status=INITIAL_STATUS,
                created_at=datetime.now(timezone.utc),
                expected_resolution=INITIAL_EXPECTED_RESOLUTION,
                scenario_tag=INITIAL_SCENARIO_TAG,
            )
            self._tickets.create(ticket)
            self._session.commit()
            return ticket
        except TicketOrderNotFoundError:
            # End the read transaction opened by the ownership lookup without writing.
            self._session.rollback()
            raise
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise TicketPersistenceError() from exc

    def list_customer_tickets(self, customer_id: str, limit: int = 10) -> list[Ticket]:
        return self._tickets.list_by_customer(customer_id, limit)

    def get_customer_ticket(self, customer_id: str, ticket_id: str) -> Ticket | None:
        return self._tickets.get_by_id_for_customer(customer_id, ticket_id)

    @staticmethod
    def _new_ticket_id() -> str:
        # "TKT-" plus 24 hexadecimal characters fits varchar(30) and avoids MAX()+1 races.
        return f"TKT-{uuid4().hex[:24].upper()}"
