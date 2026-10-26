"""Read-only verification of the internal order and shipment investigation tools."""

import sys

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.ticket import Ticket
from app.repositories.order_repository import OrderRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.repositories.ticket_repository import TicketRepository
from app.services.investigation_service import InvestigationService
from app.tools.context import CustomerInvestigationContext
from app.tools.order_tools import OrderInvestigationTool
from app.tools.shipment_tools import ShipmentInvestigationTool


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    """Verify tool results against existing records without changing database state."""
    try:
        settings = get_settings()
        if settings.app_environment != "development":
            return fail("This verification script only runs against a development database.")

        with get_session_factory()() as session:
            # PostgreSQL rejects writes for the remainder of this transaction.
            session.execute(text("SET TRANSACTION READ ONLY"))

            ticket = session.scalar(
                select(Ticket)
                .where(Ticket.order_id.is_not(None))
                .order_by(Ticket.ticket_id.asc())
                .limit(1)
            )
            if ticket is None:
                return fail("No order-linked ticket exists to verify.")

            # This local development script is trusted application code. It does
            # not authenticate a caller and must never be exposed as an API path.
            context = CustomerInvestigationContext(customer_id=ticket.customer_id)
            order_repository = OrderRepository(session)
            shipment_repository = ShipmentRepository(session)
            order_tool = OrderInvestigationTool(order_repository)
            shipment_tool = ShipmentInvestigationTool(order_repository, shipment_repository)
            service = InvestigationService(
                TicketRepository(session),
                order_tool,
                shipment_tool,
            )

            order_result = order_tool.get_order_details(ticket.order_id, context)
            shipment_result = shipment_tool.get_shipment_status(ticket.order_id, context)
            report = service.investigate_order_shipping(ticket.ticket_id, context)

            database_order = order_repository.get_by_id(ticket.order_id)
            database_shipments = shipment_repository.list_by_order_id(ticket.order_id)
            if database_order is None:
                return fail("The selected ticket references an order that no longer exists.")
            if report.order is None or report.shipments is None:
                return fail("The investigation report did not include expected order data.")

            facts_match = (
                order_result.order is not None
                and order_result.order.order_id == database_order.order_id
                and order_result.order.status == database_order.status
                and shipment_result.shipments is not None
                and [shipment.shipment_id for shipment in report.shipments.shipments]
                == [shipment.shipment_id for shipment in database_shipments]
                and report.order.order_id == database_order.order_id
                and report.order.status == database_order.status
            )
            if not facts_match:
                return fail("Tool facts did not match the current database records.")

            statuses = [shipment.status for shipment in report.shipments.shipments]
            indicators = [f"{item.field}: {item.reason}" for item in report.missing_data]
            print(f"Ticket ID: {ticket.ticket_id}")
            print(f"Order: {report.order.order_id} ({report.order.status})")
            print(f"Shipment count: {len(report.shipments.shipments)}")
            print(f"Shipment statuses: {', '.join(statuses) if statuses else 'none'}")
            print(f"Investigation outcome: {report.outcome.value}")
            print(f"Missing information: {', '.join(indicators) if indicators else 'none'}")
            print("PASS: Investigation facts match the existing database records.")
            return 0
    except (SQLAlchemyError, ValidationError):
        return fail("Database configuration or connectivity is unavailable.")


if __name__ == "__main__":
    raise SystemExit(main())
