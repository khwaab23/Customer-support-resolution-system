from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.schemas.investigation import (
    InvestigationOrderDetails,
    InvestigationOutcome,
    InvestigationPaymentDetails,
    InvestigationReport,
    MissingData,
    OrderPayments,
)
from app.tools.context import CustomerInvestigationContext


class PaymentInvestigationTool:
    """Read-only, customer-scoped payment history lookup."""

    def __init__(
        self,
        order_repository: OrderRepository,
        payment_repository: PaymentRepository,
    ) -> None:
        self._orders = order_repository
        self._payments = payment_repository

    def get_payment_history(
        self,
        order_id: str,
        context: CustomerInvestigationContext,
    ) -> InvestigationReport:
        """Return customer-safe payment facts for an owned order only."""
        order = self._orders.get_by_id(order_id)
        if order is None or order.customer_id != context.customer_id:
            return InvestigationReport(outcome=InvestigationOutcome.ORDER_NOT_FOUND)

        payments = self._payments.list_by_order_id(order_id)
        missing_data: list[MissingData] = []
        if not payments:
            missing_data.append(
                MissingData(
                    field="payments",
                    reason="No payment records were found for this order.",
                )
            )

        return InvestigationReport(
            outcome=InvestigationOutcome.COMPLETE,
            order=InvestigationOrderDetails.model_validate(order),
            payments=OrderPayments(
                order_id=order_id,
                payments=[
                    InvestigationPaymentDetails.model_validate(payment)
                    for payment in payments
                ],
            ),
            missing_data=missing_data,
        )
