from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.refund import Refund
from app.models.return_record import ReturnRecord
from app.models.ticket import Ticket
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.ticket_repository import TicketRepository
from app.rag.models import PolicyRetrievalResult, RetrievedPolicyPassage, RetrievalStatus
from app.schemas.investigation import (
    InvestigationOrderDetails,
    InvestigationOutcome,
    InvestigationReport,
    OrderPayments,
    OrderRefunds,
    OrderReturns,
    PolicyLookupOutcome,
    PolicyTopic,
)
from app.services.investigation_service import InvestigationService
from app.tools.context import CustomerInvestigationContext
from app.tools.order_tools import OrderInvestigationTool
from app.tools.payment_tools import PaymentInvestigationTool
from app.tools.policy_tools import PolicyLookupTool
from app.tools.refund_tools import RefundHistoryInvestigationTool
from app.tools.return_tools import ReturnInvestigationTool
from app.tools.shipment_tools import ShipmentInvestigationTool


def make_context(customer_id: str = "CUST-001") -> CustomerInvestigationContext:
    return CustomerInvestigationContext(customer_id=customer_id)


def make_order(customer_id: str = "CUST-001") -> Order:
    return Order(
        order_id="ORD-001",
        customer_id=customer_id,
        ordered_at=date(2026, 1, 10),
        status="DELIVERED",
        currency="USD",
        total_minor=2599,
    )


def make_payment(payment_id: str = "PAY-001") -> Payment:
    return Payment(
        payment_id=payment_id,
        order_id="ORD-001",
        amount_minor=2599,
        currency="USD",
        status="CAPTURED",
        captured_at=date(2026, 1, 10),
        provider="MockPay",
    )


def make_order_item() -> OrderItem:
    return OrderItem(
        order_item_id="OITEM-001",
        order_id="ORD-001",
        product_id="PROD-001",
        quantity=1,
        unit_price_minor=2599,
        line_total_minor=2599,
    )


def make_return(return_id: str = "RET-001") -> ReturnRecord:
    record = ReturnRecord(
        return_id=return_id,
        order_id="ORD-001",
        order_item_id="OITEM-001",
        requested_at=date(2026, 1, 12),
        received_at=None,
        inspection_status="PENDING",
        status="IN_TRANSIT",
        reason="DAMAGED",
    )
    record.order_item = make_order_item()
    return record


def make_refund(refund_id: str = "RFD-001") -> Refund:
    return Refund(
        refund_id=refund_id,
        order_id="ORD-001",
        return_id="RET-001",
        payment_id="PAY-001",
        amount_minor=2599,
        status="SUCCEEDED",
        approved_by="INTERNAL-USER",
        approved_at=datetime(2026, 1, 13, tzinfo=timezone.utc),
        idempotency_key="internal-idempotency-key",
        provider_reference="internal-provider-reference",
        created_at=datetime(2026, 1, 13, tzinfo=timezone.utc),
    )


def make_ticket(order_id: str | None = "ORD-001", customer_id: str = "CUST-001") -> Ticket:
    return Ticket(
        ticket_id="TKT-001",
        customer_id=customer_id,
        order_id=order_id,
        category="DAMAGED_ITEM",
        subject="Customer support request",
        message="My item arrived damaged; I need a refund.",
        status="OPEN",
        created_at=datetime(2026, 1, 12, tzinfo=timezone.utc),
        expected_resolution="PENDING_TRIAGE",
        scenario_tag="customer_submitted",
    )


def test_payment_tool_returns_customer_safe_multiple_payment_history() -> None:
    orders = Mock(spec=OrderRepository)
    payments = Mock(spec=PaymentRepository)
    orders.get_by_id.return_value = make_order()
    payments.list_by_order_id.return_value = [make_payment("PAY-002"), make_payment("PAY-001")]

    report = PaymentInvestigationTool(orders, payments).get_payment_history(
        "ORD-001", make_context()
    )

    assert report.outcome is InvestigationOutcome.COMPLETE
    assert report.payments is not None
    assert len(report.payments.payments) == 2
    assert "payment_id" not in report.payments.payments[0].model_dump()
    payments.list_by_order_id.assert_called_once_with("ORD-001")


@pytest.mark.parametrize(
    "tool_factory, method_name",
    [
        (
            lambda orders: PaymentInvestigationTool(orders, Mock(spec=PaymentRepository)),
            "get_payment_history",
        ),
        (
            lambda orders: ReturnInvestigationTool(orders, Mock(spec=ReturnRepository)),
            "get_return_history",
        ),
        (
            lambda orders: RefundHistoryInvestigationTool(orders, Mock(spec=RefundRepository)),
            "get_refund_history",
        ),
    ],
)
def test_financial_tools_reject_another_customers_order(tool_factory, method_name: str) -> None:
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.return_value = make_order(customer_id="CUST-OTHER")
    tool = tool_factory(orders)

    report = getattr(tool, method_name)("ORD-001", make_context())

    assert report.outcome is InvestigationOutcome.ORDER_NOT_FOUND
    assert report.order is None


@pytest.mark.parametrize(
    "tool_factory, method_name, expected_field",
    [
        (
            lambda orders, repository: PaymentInvestigationTool(orders, repository),
            "get_payment_history",
            "payments",
        ),
        (
            lambda orders, repository: ReturnInvestigationTool(orders, repository),
            "get_return_history",
            "returns",
        ),
        (
            lambda orders, repository: RefundHistoryInvestigationTool(orders, repository),
            "get_refund_history",
            "refunds",
        ),
    ],
)
def test_financial_tools_report_missing_history(
    tool_factory, method_name: str, expected_field: str
) -> None:
    orders = Mock(spec=OrderRepository)
    repository = Mock()
    orders.get_by_id.return_value = make_order()
    repository.list_by_order_id.return_value = []
    tool = tool_factory(orders, repository)

    report = getattr(tool, method_name)("ORD-001", make_context())

    assert report.outcome is InvestigationOutcome.COMPLETE
    assert [item.field for item in report.missing_data] == [expected_field]


def test_return_tool_includes_associated_order_items_for_multiple_returns() -> None:
    orders = Mock(spec=OrderRepository)
    returns = Mock(spec=ReturnRepository)
    orders.get_by_id.return_value = make_order()
    returns.list_by_order_id.return_value = [make_return("RET-002"), make_return("RET-001")]

    report = ReturnInvestigationTool(orders, returns).get_return_history(
        "ORD-001", make_context()
    )

    assert report.returns is not None
    assert [item.return_id for item in report.returns.returns] == ["RET-002", "RET-001"]
    assert report.returns.returns[0].order_item.order_item_id == "OITEM-001"


def test_refund_tool_returns_existing_history_without_internal_approval_data() -> None:
    orders = Mock(spec=OrderRepository)
    refunds = Mock(spec=RefundRepository)
    orders.get_by_id.return_value = make_order()
    refunds.list_by_order_id.return_value = [make_refund()]

    report = RefundHistoryInvestigationTool(orders, refunds).get_refund_history(
        "ORD-001", make_context()
    )

    assert report.refunds is not None
    refund = report.refunds.refunds[0].model_dump()
    assert refund["refund_id"] == "RFD-001"
    assert "approved_by" not in refund
    assert "idempotency_key" not in refund
    assert "provider_reference" not in refund


def test_policy_lookup_returns_semantic_source_and_reports_no_evidence() -> None:
    retriever = Mock()
    retriever.retrieve_policy_evidence.return_value = PolicyRetrievalResult(
        query="return eligibility",
        status=RetrievalStatus.FOUND,
        passages=[
            RetrievedPolicyPassage(
                policy_id="NTE-POL-01",
                document_title="Returns & Eligibility",
                policy_version="1.0",
                effective_date=date(2026, 10, 1),
                section_heading="Standard window",
                heading_path=("Returns & Eligibility", "Standard window"),
                source_filename="returns_and_eligibility.md",
                source_path="policies/returns_and_eligibility.md",
                text="A customer may request a standard return within 30 calendar days.",
                distance=0.1,
            )
        ],
    )
    tool = PolicyLookupTool(retriever)

    found = tool.lookup(PolicyTopic.RETURN, make_context())

    assert found.outcome is PolicyLookupOutcome.FOUND
    assert found.policies[0].source == "policies/returns_and_eligibility.md"

    retriever.retrieve_policy_evidence.return_value = PolicyRetrievalResult(
        query="refund handling",
        status=RetrievalStatus.NO_EVIDENCE,
        missing_information=["No applicable policy evidence met the retrieval criteria."],
    )
    missing = tool.lookup(PolicyTopic.REFUND, make_context())

    assert missing.outcome is PolicyLookupOutcome.NOT_FOUND
    assert missing.missing_data[0].field == "policy:REFUND"


def test_policy_lookup_rejects_semantically_retrieved_but_cross_topic_passages() -> None:
    retriever = Mock()
    retriever.retrieve_policy_evidence.return_value = PolicyRetrievalResult(
        query="refund handling",
        status=RetrievalStatus.FOUND,
        passages=[
            RetrievedPolicyPassage(
                policy_id="NTE-POL-01",
                document_title="Returns & Eligibility",
                policy_version="1.0",
                effective_date=date(2026, 10, 1),
                section_heading="Standard window",
                heading_path=("Returns & Eligibility", "Standard window"),
                source_filename="returns_and_eligibility.md",
                source_path="policies/returns_and_eligibility.md",
                text="Return eligibility evidence.",
                distance=0.1,
            )
        ],
    )

    result = PolicyLookupTool(retriever).lookup(PolicyTopic.REFUND, make_context())

    assert result.outcome is PolicyLookupOutcome.NOT_FOUND
    assert result.policies == []


def test_investigate_ticket_assembles_structured_facts_and_policy_evidence() -> None:
    tickets = Mock(spec=TicketRepository)
    tickets.get_by_id.return_value = make_ticket()
    order_report = InvestigationReport(
        outcome=InvestigationOutcome.COMPLETE,
        order=InvestigationOrderDetails.model_validate(make_order()),
    )
    shipment_report = InvestigationReport(outcome=InvestigationOutcome.COMPLETE)
    payment_report = InvestigationReport(
        outcome=InvestigationOutcome.COMPLETE,
        payments=OrderPayments(order_id="ORD-001", payments=[]),
    )
    return_report = InvestigationReport(
        outcome=InvestigationOutcome.COMPLETE,
        returns=OrderReturns(order_id="ORD-001", returns=[]),
    )
    refund_report = InvestigationReport(
        outcome=InvestigationOutcome.COMPLETE,
        refunds=OrderRefunds(order_id="ORD-001", refunds=[]),
    )
    order_tool = Mock(spec=OrderInvestigationTool)
    shipment_tool = Mock(spec=ShipmentInvestigationTool)
    payment_tool = Mock(spec=PaymentInvestigationTool)
    return_tool = Mock(spec=ReturnInvestigationTool)
    refund_tool = Mock(spec=RefundHistoryInvestigationTool)
    policy_tool = Mock(spec=PolicyLookupTool)
    order_tool.get_order_details.return_value = order_report
    shipment_tool.get_shipment_status.return_value = shipment_report
    payment_tool.get_payment_history.return_value = payment_report
    return_tool.get_return_history.return_value = return_report
    refund_tool.get_refund_history.return_value = refund_report
    policy_tool.lookup.return_value = Mock(policies=[], missing_data=[])
    service = InvestigationService(
        tickets,
        order_tool,
        shipment_tool,
        payment_tool,
        return_tool,
        refund_tool,
        policy_tool,
    )

    report = service.investigate_ticket("TKT-001", make_context())

    assert report.outcome is InvestigationOutcome.COMPLETE
    assert report.ticket is not None
    assert report.ticket.message == "My item arrived damaged; I need a refund."
    assert report.order is not None
    assert report.payments is not None
    assert report.returns is not None
    assert report.refunds is not None
    assert policy_tool.lookup.call_count == 2


def test_investigate_ticket_preserves_not_found_and_missing_order_link_behavior() -> None:
    tickets = Mock(spec=TicketRepository)
    service = InvestigationService(
        tickets,
        Mock(spec=OrderInvestigationTool),
        Mock(spec=ShipmentInvestigationTool),
        Mock(spec=PaymentInvestigationTool),
        Mock(spec=ReturnInvestigationTool),
        Mock(spec=RefundHistoryInvestigationTool),
        Mock(spec=PolicyLookupTool),
    )
    tickets.get_by_id.side_effect = [None, make_ticket(customer_id="CUST-OTHER"), make_ticket(order_id=None)]

    assert service.investigate_ticket("TKT-MISSING", make_context()).outcome is InvestigationOutcome.ORDER_NOT_FOUND
    assert service.investigate_ticket("TKT-OTHER", make_context()).outcome is InvestigationOutcome.ORDER_NOT_FOUND
    missing_order = service.investigate_ticket("TKT-UNLINKED", make_context())
    assert missing_order.outcome is InvestigationOutcome.MISSING_ORDER_LINK
    assert missing_order.ticket is not None


def test_financial_tools_do_not_write_or_accept_identity_override() -> None:
    session = Mock(spec=Session)
    session.scalar.return_value = make_order()
    session.scalars.return_value = [make_payment()]
    tool = PaymentInvestigationTool(OrderRepository(session), PaymentRepository(session))

    report = tool.get_payment_history("ORD-001", make_context())

    assert report.outcome is InvestigationOutcome.COMPLETE
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.delete.assert_not_called()
    with pytest.raises(TypeError):
        tool.get_payment_history(  # type: ignore[call-arg]
            "ORD-001", make_context(), customer_id="CUST-OTHER"
        )
