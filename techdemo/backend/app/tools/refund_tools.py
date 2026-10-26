from app.repositories.order_repository import OrderRepository
from app.repositories.refund_repository import RefundRepository
from app.schemas.investigation import (
    InvestigationOrderDetails,
    InvestigationOutcome,
    InvestigationRefundDetails,
    InvestigationReport,
    MissingData,
    OrderRefunds,
)
from app.tools.context import CustomerInvestigationContext


class RefundHistoryInvestigationTool:
    """Read-only, customer-scoped historical refund lookup; never approves refunds."""

    def __init__(
        self,
        order_repository: OrderRepository,
        refund_repository: RefundRepository,
    ) -> None:
        self._orders = order_repository
        self._refunds = refund_repository

    def get_refund_history(
        self,
        order_id: str,
        context: CustomerInvestigationContext,
    ) -> InvestigationReport:
        """Return existing customer-safe refund facts for an owned order only."""
        order = self._orders.get_by_id(order_id)
        if order is None or order.customer_id != context.customer_id:
            return InvestigationReport(outcome=InvestigationOutcome.ORDER_NOT_FOUND)

        refunds = self._refunds.list_by_order_id(order_id)
        missing_data: list[MissingData] = []
        if not refunds:
            missing_data.append(
                MissingData(
                    field="refunds",
                    reason="No refund records were found for this order.",
                )
            )

        return InvestigationReport(
            outcome=InvestigationOutcome.COMPLETE,
            order=InvestigationOrderDetails.model_validate(order),
            refunds=OrderRefunds(
                order_id=order_id,
                refunds=[
                    InvestigationRefundDetails(
                        refund_id=refund.refund_id,
                        amount_minor=refund.amount_minor,
                        status=refund.status,
                        created_at=refund.created_at,
                    )
                    for refund in refunds
                ],
            ),
            missing_data=missing_data,
        )
