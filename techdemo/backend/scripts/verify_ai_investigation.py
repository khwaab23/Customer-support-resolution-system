"""Trusted development diagnostic for the bounded AI investigation agent.

This is not an HTTP endpoint and is not an authentication mechanism. It derives
its context from an existing local development ticket inside a read-only session.
"""

import os
import sys
import logging

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.agents.investigation_agent import InvestigationAgent
from app.agents.tool_executor import ToolExecutor
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.ticket import Ticket
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.agent import AgentInvestigationStatus
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
    settings = get_settings()
    if settings.app_environment != "development":
        return fail("This diagnostic only runs against a development database.")
    if not settings.openai_api_key:
        return fail("OPENAI_API_KEY is required for AI investigation verification.")
    if settings.agent_diagnostics_enabled:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s %(message)s",
        )

    requested_ticket_id = os.getenv("AI_VERIFY_TICKET_ID")
    try:
        with get_session_factory()() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            statement = select(Ticket).where(Ticket.order_id.is_not(None))
            if requested_ticket_id:
                statement = statement.where(Ticket.ticket_id == requested_ticket_id)
            ticket = session.scalar(statement.order_by(Ticket.ticket_id.asc()).limit(1))
            if ticket is None:
                return fail("No suitable order-linked development ticket was found.")

            # This script is trusted local development code. The ticket's customer
            # ID is not command input and cannot be supplied by the model.
            context = CustomerInvestigationContext(customer_id=ticket.customer_id)
            orders = OrderRepository(session)
            executor = ToolExecutor(
                OrderInvestigationTool(orders),
                ShipmentInvestigationTool(orders, ShipmentRepository(session)),
                PaymentInvestigationTool(orders, PaymentRepository(session)),
                ReturnInvestigationTool(orders, ReturnRepository(session)),
                RefundHistoryInvestigationTool(orders, RefundRepository(session)),
                PolicyLookupTool(),
                max_output_chars=settings.agent_tool_output_max_chars,
            )
            agent = InvestigationAgent(
                TicketRepository(session),
                executor,
                settings=settings,
            )
            result = agent.investigate(ticket.ticket_id, context)
    except SQLAlchemyError:
        return fail("Database configuration or connectivity is unavailable.")

    print(f"Ticket ID: {result.ticket_id}")
    print(f"Issue type: {result.issue_type.value}")
    print(f"Investigation status: {result.investigation_status.value}")
    print(f"Tools executed: {', '.join(result.tools_executed) or 'none'}")
    print("Verified findings:")
    for fact in result.verified_facts:
        print(f"  - {fact.tool_name}{fact.json_pointer}: {fact.value}")
    print("Policy citations:")
    for citation in result.policy_citations:
        print(
            f"  - {citation.policy_id} v{citation.policy_version}:"
            f" {citation.source} / {citation.section_heading}"
        )
    print("Missing information:")
    for item in result.missing_information:
        print(f"  - {item}")
    print("Recommended next steps:")
    for step in result.recommended_next_steps:
        print(f"  - {step}")
    return 0 if result.investigation_status is AgentInvestigationStatus.COMPLETE else 1


if __name__ == "__main__":
    raise SystemExit(main())
