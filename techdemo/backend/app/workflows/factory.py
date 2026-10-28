"""Composition helpers for trusted local workflow callers and future API wiring."""

from sqlalchemy.orm import Session

from app.agents.investigation_agent import InvestigationAgent
from app.agents.tool_executor import ToolExecutor
from app.core.config import Settings, get_settings
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.repositories.ticket_repository import TicketRepository
from app.services.refund_eligibility_service import RefundEligibilityService
from app.services.support_workflow_service import SupportWorkflowService
from app.tools.order_tools import OrderInvestigationTool
from app.tools.payment_tools import PaymentInvestigationTool
from app.tools.policy_tools import PolicyLookupTool
from app.tools.refund_tools import RefundHistoryInvestigationTool
from app.tools.return_tools import ReturnInvestigationTool
from app.tools.shipment_tools import ShipmentInvestigationTool


def build_support_workflow_service(
    session: Session,
    *,
    settings: Settings | None = None,
) -> SupportWorkflowService:
    """Compose the existing read-only investigation stack into one workflow service."""
    configured = settings or get_settings()
    orders = OrderRepository(session)
    executor = ToolExecutor(
        OrderInvestigationTool(orders),
        ShipmentInvestigationTool(orders, ShipmentRepository(session)),
        PaymentInvestigationTool(orders, PaymentRepository(session)),
        ReturnInvestigationTool(orders, ReturnRepository(session)),
        RefundHistoryInvestigationTool(orders, RefundRepository(session)),
        PolicyLookupTool(),
        max_output_chars=configured.agent_tool_output_max_chars,
    )
    return SupportWorkflowService(
        TicketRepository(session),
        InvestigationAgent(TicketRepository(session), executor, settings=configured),
        settings=configured,
    )


def build_refund_eligibility_service(session: Session) -> RefundEligibilityService:
    """Compose only read-only repositories used for deterministic assessment."""
    return RefundEligibilityService(
        TicketRepository(session), OrderRepository(session), PaymentRepository(session),
        ReturnRepository(session), RefundRepository(session), ShipmentRepository(session),
        PolicyLookupTool(),
    )
