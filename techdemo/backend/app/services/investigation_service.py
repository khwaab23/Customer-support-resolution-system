"""Read-only orchestration of customer-scoped order and shipment investigation."""

from app.repositories.ticket_repository import TicketRepository
from app.schemas.investigation import (
    InvestigationTicketDetails,
    InvestigationOutcome,
    InvestigationReport,
    MissingData,
    PolicyTopic,
)
from app.tools.context import CustomerInvestigationContext
from app.tools.order_tools import OrderInvestigationTool
from app.tools.payment_tools import PaymentInvestigationTool
from app.tools.policy_tools import PolicyLookupTool
from app.tools.refund_tools import RefundHistoryInvestigationTool
from app.tools.return_tools import ReturnInvestigationTool
from app.tools.shipment_tools import ShipmentInvestigationTool

_POLICY_TOPIC_TERMS: dict[PolicyTopic, tuple[str, ...]] = {
    PolicyTopic.RETURN: ("return",),
    PolicyTopic.REFUND: ("refund",),
    PolicyTopic.DAMAGED_ITEM: ("damaged", "damage", "broken", "defect"),
}


class InvestigationService:
    """Combine trusted, deterministic investigation operations for one ticket."""

    def __init__(
        self,
        ticket_repository: TicketRepository,
        order_tool: OrderInvestigationTool,
        shipment_tool: ShipmentInvestigationTool,
        payment_tool: PaymentInvestigationTool | None = None,
        return_tool: ReturnInvestigationTool | None = None,
        refund_tool: RefundHistoryInvestigationTool | None = None,
        policy_tool: PolicyLookupTool | None = None,
    ) -> None:
        self._tickets = ticket_repository
        self._order_tool = order_tool
        self._shipment_tool = shipment_tool
        self._payment_tool = payment_tool
        self._return_tool = return_tool
        self._refund_tool = refund_tool
        self._policy_tool = policy_tool

    def investigate_order_shipping(
        self,
        ticket_id: str,
        context: CustomerInvestigationContext,
    ) -> InvestigationReport:
        """Return verified order and shipment facts for a customer-owned ticket.

        ``context`` must have been constructed by trusted application code after
        authentication. This service neither authenticates callers nor accepts a
        customer ID as a business argument.
        """
        ticket = self._tickets.get_by_id(ticket_id)
        if ticket is None or ticket.customer_id != context.customer_id:
            # Deliberately use the established not-found result for both cases so
            # a caller cannot determine whether another customer's ticket exists.
            return InvestigationReport(outcome=InvestigationOutcome.ORDER_NOT_FOUND)

        if ticket.order_id is None:
            return InvestigationReport(
                outcome=InvestigationOutcome.MISSING_ORDER_LINK,
                ticket_id=ticket.ticket_id,
                missing_data=[
                    MissingData(
                        field="order_id",
                        reason="This ticket is not associated with an order.",
                    )
                ],
            )

        order_result = self._order_tool.get_order_details(ticket.order_id, context)
        if order_result.outcome is not InvestigationOutcome.COMPLETE:
            return order_result.model_copy(update={"ticket_id": ticket.ticket_id})

        shipment_result = self._shipment_tool.get_shipment_status(
            ticket.order_id,
            context,
        )
        if shipment_result.outcome is not InvestigationOutcome.COMPLETE:
            return shipment_result.model_copy(update={"ticket_id": ticket.ticket_id})

        return InvestigationReport(
            outcome=InvestigationOutcome.COMPLETE,
            ticket_id=ticket.ticket_id,
            order=order_result.order,
            shipments=shipment_result.shipments,
            missing_data=[
                *order_result.missing_data,
                *shipment_result.missing_data,
            ],
        )

    def investigate_ticket(
        self,
        ticket_id: str,
        context: CustomerInvestigationContext,
    ) -> InvestigationReport:
        """Collect verified, read-only evidence for a customer-owned ticket.

        Policy topics are selected by fixed keyword matching over ticket category
        and message text. This is deliberately deterministic; it is not an AI
        classifier and it does not decide refund eligibility.
        """
        ticket = self._tickets.get_by_id(ticket_id)
        if ticket is None or ticket.customer_id != context.customer_id:
            return InvestigationReport(outcome=InvestigationOutcome.ORDER_NOT_FOUND)

        ticket_details = InvestigationTicketDetails.model_validate(ticket)
        if ticket.order_id is None:
            return InvestigationReport(
                outcome=InvestigationOutcome.MISSING_ORDER_LINK,
                ticket_id=ticket.ticket_id,
                ticket=ticket_details,
                missing_data=[
                    MissingData(
                        field="order_id",
                        reason="This ticket is not associated with an order.",
                    )
                ],
            )

        payment_tool, return_tool, refund_tool, policy_tool = self._financial_tools()
        order_result = self._order_tool.get_order_details(ticket.order_id, context)
        if order_result.outcome is not InvestigationOutcome.COMPLETE:
            return order_result.model_copy(
                update={"ticket_id": ticket.ticket_id, "ticket": ticket_details}
            )

        shipment_result = self._shipment_tool.get_shipment_status(ticket.order_id, context)
        if shipment_result.outcome is not InvestigationOutcome.COMPLETE:
            return shipment_result.model_copy(
                update={"ticket_id": ticket.ticket_id, "ticket": ticket_details}
            )

        payment_result = payment_tool.get_payment_history(ticket.order_id, context)
        return_result = return_tool.get_return_history(ticket.order_id, context)
        refund_result = refund_tool.get_refund_history(ticket.order_id, context)
        financial_results = (payment_result, return_result, refund_result)
        for result in financial_results:
            if result.outcome is not InvestigationOutcome.COMPLETE:
                return result.model_copy(
                    update={"ticket_id": ticket.ticket_id, "ticket": ticket_details}
                )

        policies = []
        missing_data = [
            *order_result.missing_data,
            *shipment_result.missing_data,
            *payment_result.missing_data,
            *return_result.missing_data,
            *refund_result.missing_data,
        ]
        topics = self._policy_topics(ticket.category, ticket.message)
        if not topics:
            missing_data.append(
                MissingData(
                    field="policy_topic",
                    reason="No documented policy topic matched the ticket metadata.",
                )
            )
        for topic in topics:
            policy_result = policy_tool.lookup(topic, context)
            policies.extend(policy_result.policies)
            missing_data.extend(policy_result.missing_data)

        return InvestigationReport(
            outcome=InvestigationOutcome.COMPLETE,
            ticket_id=ticket.ticket_id,
            ticket=ticket_details,
            order=order_result.order,
            shipments=shipment_result.shipments,
            payments=payment_result.payments,
            returns=return_result.returns,
            refunds=refund_result.refunds,
            policies=policies,
            missing_data=missing_data,
        )

    def _financial_tools(
        self,
    ) -> tuple[
        PaymentInvestigationTool,
        ReturnInvestigationTool,
        RefundHistoryInvestigationTool,
        PolicyLookupTool,
    ]:
        if (
            self._payment_tool is None
            or self._return_tool is None
            or self._refund_tool is None
            or self._policy_tool is None
        ):
            raise RuntimeError(
                "Financial investigation tools are required for investigate_ticket."
            )
        return (
            self._payment_tool,
            self._return_tool,
            self._refund_tool,
            self._policy_tool,
        )

    @staticmethod
    def _policy_topics(category: str, message: str) -> tuple[PolicyTopic, ...]:
        searchable = f"{category}\n{message}".casefold()
        return tuple(
            topic
            for topic, terms in _POLICY_TOPIC_TERMS.items()
            if any(term in searchable for term in terms)
        )
