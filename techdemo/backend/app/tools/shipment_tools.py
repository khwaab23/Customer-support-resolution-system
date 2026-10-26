from app.repositories.order_repository import OrderRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.schemas.investigation import (
    InvestigationOrderDetails,
    InvestigationOutcome,
    InvestigationReport,
    InvestigationShipmentDetails,
    MissingData,
    OrderShipments,
)
from app.tools.context import CustomerInvestigationContext


class ShipmentInvestigationTool:
    """Read-only, customer-scoped shipment lookup for future investigation agents."""

    def __init__(
        self,
        order_repository: OrderRepository,
        shipment_repository: ShipmentRepository,
    ) -> None:
        self._orders = order_repository
        self._shipments = shipment_repository

    def get_shipment_status(
        self,
        order_id: str,
        context: CustomerInvestigationContext,
    ) -> InvestigationReport:
        """Return every verified shipment after verifying trusted order ownership.

        The sole business argument is ``order_id``. The tool intentionally does
        not accept customer identity, role, user ID, or session information.
        """
        order = self._orders.get_by_id(order_id)
        if order is None or order.customer_id != context.customer_id:
            return InvestigationReport(outcome=InvestigationOutcome.ORDER_NOT_FOUND)

        shipments = self._shipments.list_by_order_id(order_id)
        missing_data: list[MissingData] = []
        if not shipments:
            missing_data.append(
                MissingData(
                    field="shipments",
                    reason="No shipment records were found for this order.",
                )
            )

        return InvestigationReport(
            outcome=InvestigationOutcome.COMPLETE,
            order=InvestigationOrderDetails.model_validate(order),
            shipments=OrderShipments(
                order_id=order_id,
                shipments=[
                    InvestigationShipmentDetails.model_validate(shipment)
                    for shipment in shipments
                ],
            ),
            missing_data=missing_data,
        )
