"""Deterministic, read-only refund eligibility assessment from verified records."""

from datetime import datetime, timedelta, timezone

from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.schemas.agent import AgentPolicyCitation, VerifiedFact
from app.schemas.review import EligibilityAssessment, EligibilityStatus
from app.tools.context import CustomerInvestigationContext
from app.tools.policy_tools import PolicyLookupTool
from app.schemas.investigation import PolicyLookupOutcome, PolicyTopic


class RefundEligibilityService:
    """Applies the documented prerequisites; it never approves or creates refunds."""

    def __init__(self, tickets: TicketRepository, orders: OrderRepository, payments: PaymentRepository, returns: ReturnRepository, refunds: RefundRepository, shipments: ShipmentRepository, policy_tool: PolicyLookupTool) -> None:
        self._tickets, self._orders, self._payments = tickets, orders, payments
        self._returns, self._refunds, self._shipments, self._policy = returns, refunds, shipments, policy_tool

    def assess(self, ticket_id: str, context: CustomerInvestigationContext) -> EligibilityAssessment:
        now = datetime.now(timezone.utc)
        ticket = self._tickets.get_by_id(ticket_id)
        if ticket is None or ticket.customer_id != context.customer_id or ticket.order_id is None:
            return EligibilityAssessment(assessment_status=EligibilityStatus.NEEDS_REVIEW, reasons=["Ticket ownership or order link could not be verified."], evaluated_at=now)
        order = self._orders.get_by_id(ticket.order_id)
        if order is None or order.customer_id != context.customer_id:
            return EligibilityAssessment(assessment_status=EligibilityStatus.NEEDS_REVIEW, reasons=["Order ownership could not be verified."], evaluated_at=now)
        return_policy = self._policy.lookup(PolicyTopic.RETURN, context)
        refund_policy = self._policy.lookup(PolicyTopic.REFUND, context)
        citations = self._citations([*return_policy.policies, *refund_policy.policies])
        if return_policy.outcome is not PolicyLookupOutcome.FOUND or refund_policy.outcome is not PolicyLookupOutcome.FOUND:
            return EligibilityAssessment(assessment_status=EligibilityStatus.NEEDS_REVIEW, reasons=["Applicable return or refund policy evidence is unavailable."], policy_references=citations, evaluated_at=now)
        returns = self._returns.list_by_order_id(order.order_id)
        payments = self._payments.list_by_order_id(order.order_id)
        refunds = self._refunds.list_by_order_id(order.order_id)
        facts = [VerifiedFact(tool_name="get_order_details", json_pointer="/order/order_id", value=order.order_id)]
        if refunds:
            return EligibilityAssessment(assessment_status=EligibilityStatus.INELIGIBLE, reasons=["Existing refund history prevents a duplicate refund proposal."], verified_facts=facts, policy_references=citations, evaluated_at=now, applicable_policy_version=refund_policy.policies[0].policy_version)
        received = [item for item in returns if item.status == "RECEIVED" and item.inspection_status == "PASSED"]
        if not received:
            return EligibilityAssessment(assessment_status=EligibilityStatus.NEEDS_REVIEW, reasons=["No received and passed return record is available."], verified_facts=facts, policy_references=citations, missing_information=["A received return with a passed inspection is required."], evaluated_at=now, applicable_policy_version=refund_policy.policies[0].policy_version)
        delivered = [item.delivered_at for item in self._shipments.list_by_order_id(order.order_id) if item.delivered_at is not None]
        if not delivered or received[0].requested_at > max(delivered) + timedelta(days=30):
            return EligibilityAssessment(assessment_status=EligibilityStatus.NEEDS_REVIEW, reasons=["Return-window timing cannot be verified as satisfying the documented policy."], verified_facts=facts, policy_references=citations, missing_information=["Verified delivery date and qualifying return-window timing are required."], evaluated_at=now, applicable_policy_version=refund_policy.policies[0].policy_version)
        captured = [item for item in payments if item.status == "CAPTURED"]
        if not captured:
            return EligibilityAssessment(assessment_status=EligibilityStatus.NEEDS_REVIEW, reasons=["No captured payment record is available."], verified_facts=facts, policy_references=citations, missing_information=["Captured payment evidence is required."], evaluated_at=now, applicable_policy_version=refund_policy.policies[0].policy_version)
        amount = min(received[0].order_item.line_total_minor, sum(item.amount_minor for item in captured))
        return EligibilityAssessment(assessment_status=EligibilityStatus.ELIGIBLE, reasons=["Documented return, inspection, payment, and duplicate-refund prerequisites are verified. Human approval remains required."], verified_facts=facts, policy_references=citations, evaluated_at=now, applicable_policy_version=refund_policy.policies[0].policy_version, proposed_refundable_amount_minor=amount)

    @staticmethod
    def _citations(policies):
        return [AgentPolicyCitation(policy_id=item.policy_id, policy_version=item.policy_version, source=item.source, section_heading=item.section_heading, effective_date=item.effective_date) for item in policies if item.policy_id and item.policy_version and item.section_heading]
