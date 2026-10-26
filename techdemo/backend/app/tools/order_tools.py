from app.repositories.order_repository import OrderRepository
from app.schemas.investigation import (
    InvestigationOrderDetails,
    InvestigationOutcome,
    InvestigationReport,
)
from app.tools.context import CustomerInvestigationContext


class OrderInvestigationTool:
    """Read-only, customer-scoped order lookup for future investigation agents."""

    def __init__(self, order_repository: OrderRepository) -> None:
        self._orders = order_repository

    def get_order_details(
        self,
        order_id: str,
        context: CustomerInvestigationContext,
    ) -> InvestigationReport:
        """Return order facts only when the trusted context owns the order.

        The sole business argument is ``order_id``. Customer identity is kept
        in trusted execution context and must never be supplied by an LLM.
        """
        order = self._orders.get_by_id(order_id)
        if order is None or order.customer_id != context.customer_id:
            return InvestigationReport(outcome=InvestigationOutcome.ORDER_NOT_FOUND)

        return InvestigationReport(
            outcome=InvestigationOutcome.COMPLETE,
            order=InvestigationOrderDetails.model_validate(order),
        )
