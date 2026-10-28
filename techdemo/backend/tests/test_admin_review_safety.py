"""Isolated safeguards for deterministic review decisions; no database is used."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.return_record import ReturnRecord
from app.models.ticket import Ticket
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.investigation import PolicyLookupOutcome, PolicyReference, PolicyTopic
from app.schemas.review import EligibilityStatus, ReviewDecision, ReviewDecisionRequest
from app.services.admin_review_service import ReviewValidationError
from app.services.refund_eligibility_service import RefundEligibilityService
from app.tools.context import CustomerInvestigationContext
from app.api.customer.routes import customer_safe_review_status


def _ticket() -> Ticket:
    return Ticket(ticket_id="TKT-1", customer_id="CUST-1", order_id="ORD-1", category="REFUND", subject="s", message="m", status="OPEN", created_at=datetime.now(timezone.utc), expected_resolution="x", scenario_tag="x")


def _order() -> Order:
    return Order(order_id="ORD-1", customer_id="CUST-1", ordered_at=date(2026, 10, 1), status="DELIVERED", currency="USD", total_minor=1000)


def _policy(topic: PolicyTopic, _context: CustomerInvestigationContext):
    reference = PolicyReference(policy_id="NTE-POL-01" if topic is PolicyTopic.RETURN else "NTE-POL-02", topic=topic, policy_version="1.0", source="policy.md", section_heading="Eligibility", text="verified", effective_date=date(2026, 10, 1))
    return SimpleNamespace(outcome=PolicyLookupOutcome.FOUND, policies=[reference])


def _service():
    tickets, orders = Mock(spec=TicketRepository), Mock(spec=OrderRepository)
    payments, returns, refunds, shipments = Mock(spec=PaymentRepository), Mock(spec=ReturnRepository), Mock(spec=RefundRepository), Mock(spec=ShipmentRepository)
    policy = Mock()
    tickets.get_by_id.return_value = _ticket()
    orders.get_by_id.return_value = _order()
    policy.lookup.side_effect = _policy
    return RefundEligibilityService(tickets, orders, payments, returns, refunds, shipments, policy), payments, returns, refunds, shipments, policy


def test_refund_eligibility_is_eligible_only_for_verified_prerequisites() -> None:
    service, payments, returns, refunds, shipments, policy = _service()
    item = OrderItem(order_item_id="ITEM-1", order_id="ORD-1", product_id="P", quantity=1, unit_price_minor=1000, line_total_minor=1000)
    returns.list_by_order_id.return_value = [ReturnRecord(return_id="RET-1", order_id="ORD-1", order_item_id="ITEM-1", requested_at=date(2026, 10, 2), received_at=date(2026, 10, 4), inspection_status="PASSED", status="RECEIVED", reason="RETURNED", order_item=item)]
    payments.list_by_order_id.return_value = [Payment(payment_id="PAY-1", order_id="ORD-1", amount_minor=1000, currency="USD", status="CAPTURED", captured_at=date(2026, 10, 1), provider="test")]
    refunds.list_by_order_id.return_value = []
    shipments.list_by_order_id.return_value = [SimpleNamespace(delivered_at=date(2026, 10, 1))]

    assessment = service.assess("TKT-1", CustomerInvestigationContext("CUST-1"))

    assert assessment.assessment_status is EligibilityStatus.ELIGIBLE
    assert assessment.proposed_refundable_amount_minor == 1000
    assert {call.args[0] for call in policy.lookup.call_args_list} == {PolicyTopic.RETURN, PolicyTopic.REFUND}


def test_missing_policy_or_history_never_becomes_eligible() -> None:
    service, _payments, returns, _refunds, _shipments, policy = _service()
    policy.lookup.side_effect = None
    policy.lookup.return_value = SimpleNamespace(outcome=PolicyLookupOutcome.NOT_FOUND, policies=[])
    returns.list_by_order_id.return_value = []

    assessment = service.assess("TKT-1", CustomerInvestigationContext("CUST-1"))

    assert assessment.assessment_status is EligibilityStatus.NEEDS_REVIEW
    assert assessment.proposed_refundable_amount_minor is None


def test_other_customer_ticket_cannot_be_assessed_as_eligible() -> None:
    service, *_ = _service()
    assessment = service.assess("TKT-1", CustomerInvestigationContext("CUST-OTHER"))
    assert assessment.assessment_status is EligibilityStatus.NEEDS_REVIEW


@pytest.mark.parametrize("decision", [ReviewDecision.REJECT, ReviewDecision.REQUEST_MORE_INFORMATION])
def test_nonapproval_decisions_require_a_human_reason(decision: ReviewDecision) -> None:
    with pytest.raises(ValueError):
        ReviewDecisionRequest(decision=decision, version=1).validated_reason()


def test_approval_request_carries_no_reviewer_identity_or_money_execution_field() -> None:
    request = ReviewDecisionRequest(decision=ReviewDecision.APPROVE, version=1)
    assert request.model_dump() == {"decision": "APPROVE", "reason": None, "version": 1}


def test_customer_review_projection_contains_only_a_safe_status() -> None:
    session = Mock()
    session.scalar.return_value = SimpleNamespace(review_status="APPROVED_INTERNAL")
    assert customer_safe_review_status(session, "TKT-1") == "INTERNALLY_APPROVED_PROCESSING_NOT_STARTED"
