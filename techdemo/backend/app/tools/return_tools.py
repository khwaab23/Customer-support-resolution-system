from app.repositories.order_repository import OrderRepository
from app.repositories.return_repository import ReturnRepository
from app.schemas.investigation import (
    InvestigationOrderDetails,
    InvestigationOrderItemDetails,
    InvestigationOutcome,
    InvestigationReport,
    InvestigationReturnDetails,
    MissingData,
    OrderReturns,
)
from app.tools.context import CustomerInvestigationContext


class ReturnInvestigationTool:
    """Read-only, customer-scoped return and damaged-item history lookup."""

    def __init__(
        self,
        order_repository: OrderRepository,
        return_repository: ReturnRepository,
    ) -> None:
        self._orders = order_repository
        self._returns = return_repository

    def get_return_history(
        self,
        order_id: str,
        context: CustomerInvestigationContext,
    ) -> InvestigationReport:
        """Return verified return records and their associated order items."""
        order = self._orders.get_by_id(order_id)
        if order is None or order.customer_id != context.customer_id:
            return InvestigationReport(outcome=InvestigationOutcome.ORDER_NOT_FOUND)

        returns = self._returns.list_by_order_id(order_id)
        missing_data: list[MissingData] = []
        if not returns:
            missing_data.append(
                MissingData(
                    field="returns",
                    reason="No return records were found for this order.",
                )
            )

        return InvestigationReport(
            outcome=InvestigationOutcome.COMPLETE,
            order=InvestigationOrderDetails.model_validate(order),
            returns=OrderReturns(
                order_id=order_id,
                returns=[
                    InvestigationReturnDetails(
                        return_id=return_record.return_id,
                        requested_at=return_record.requested_at,
                        received_at=return_record.received_at,
                        inspection_status=return_record.inspection_status,
                        status=return_record.status,
                        reason=return_record.reason,
                        order_item=InvestigationOrderItemDetails.model_validate(
                            return_record.order_item
                        ),
                    )
                    for return_record in returns
                ],
            ),
            missing_data=missing_data,
        )
