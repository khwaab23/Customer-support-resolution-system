"""Read-only verification for payment, return, refund, and policy investigation."""

import sys

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.payment import Payment
from app.models.refund import Refund
from app.models.return_record import ReturnRecord
from app.models.ticket import Ticket
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.repositories.ticket_repository import TicketRepository
from app.services.investigation_service import InvestigationService
from app.tools.context import CustomerInvestigationContext
from app.tools.order_tools import OrderInvestigationTool
from app.tools.payment_tools import PaymentInvestigationTool
from app.tools.policy_tools import PolicyLookupTool
from app.tools.refund_tools import RefundHistoryInvestigationTool
from app.tools.return_tools import ReturnInvestigationTool
from app.tools.shipment_tools import ShipmentInvestigationTool


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    """Compare a financial investigation report with existing development records."""
    try:
        settings = get_settings()
        if settings.app_environment != "development":
            return fail("This verification script only runs against a development database.")

        with get_session_factory()() as session:
            # PostgreSQL rejects writes for this transaction. Closing the session
            # rolls it back; this script never calls commit.
            session.execute(text("SET TRANSACTION READ ONLY"))
            ticket = session.scalar(
                select(Ticket)
                .join(Payment, Payment.order_id == Ticket.order_id)
                .join(ReturnRecord, ReturnRecord.order_id == Ticket.order_id)
                .join(Refund, Refund.order_id == Ticket.order_id)
                .where(Ticket.order_id.is_not(None))
                .order_by(Ticket.ticket_id.asc())
                .limit(1)
            )
            if ticket is None or ticket.order_id is None:
                return fail(
                    "No ticket linked to payment, return, and refund records exists to verify."
                )

            # This local development script is trusted application code. It is
            # not an authentication mechanism and must never become an API route.
            context = CustomerInvestigationContext(customer_id=ticket.customer_id)
            orders = OrderRepository(session)
            payments = PaymentRepository(session)
            returns = ReturnRepository(session)
            refunds = RefundRepository(session)
            service = InvestigationService(
                TicketRepository(session),
                OrderInvestigationTool(orders),
                ShipmentInvestigationTool(orders, ShipmentRepository(session)),
                PaymentInvestigationTool(orders, payments),
                ReturnInvestigationTool(orders, returns),
                RefundHistoryInvestigationTool(orders, refunds),
                PolicyLookupTool(),
            )

            report = service.investigate_ticket(ticket.ticket_id, context)
            database_order = orders.get_by_id(ticket.order_id)
            database_payments = payments.list_by_order_id(ticket.order_id)
            database_returns = returns.list_by_order_id(ticket.order_id)
            database_refunds = refunds.list_by_order_id(ticket.order_id)
            if (
                database_order is None
                or report.order is None
                or report.payments is None
                or report.returns is None
                or report.refunds is None
            ):
                return fail("The report did not include the expected verified financial facts.")

            facts_match = (
                report.order.order_id == database_order.order_id
                and report.order.status == database_order.status
                and [(item.amount_minor, item.status) for item in report.payments.payments]
                == [(item.amount_minor, item.status) for item in database_payments]
                and [(item.return_id, item.status) for item in report.returns.returns]
                == [(item.return_id, item.status) for item in database_returns]
                and [(item.refund_id, item.amount_minor, item.status) for item in report.refunds.refunds]
                == [(item.refund_id, item.amount_minor, item.status) for item in database_refunds]
            )
            if not facts_match:
                return fail("Investigation facts did not match the current repository data.")

            policy_sources = [policy.source for policy in report.policies]
            indicators = [f"{item.field}: {item.reason}" for item in report.missing_data]
            print(f"Ticket ID: {report.ticket_id}")
            print(f"Order: {report.order.order_id} ({report.order.status})")
            print(f"Payments: {len(report.payments.payments)}")
            print(f"Returns: {len(report.returns.returns)}")
            print(f"Refunds: {len(report.refunds.refunds)}")
            print(f"Policy sources: {', '.join(policy_sources) if policy_sources else 'none documented'}")
            print(f"Investigation outcome: {report.outcome.value}")
            print(f"Missing information: {', '.join(indicators) if indicators else 'none'}")
            print("PASS: Financial investigation facts match the existing database records.")
            return 0
    except (SQLAlchemyError, ValidationError):
        return fail("Database configuration or connectivity is unavailable.")


if __name__ == "__main__":
    raise SystemExit(main())
