from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.shipment import Shipment
from app.models.ticket import Ticket
from app.repositories.order_repository import OrderRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.investigation import InvestigationOutcome
from app.services.investigation_service import InvestigationService
from app.tools.context import CustomerInvestigationContext
from app.tools.order_tools import OrderInvestigationTool
from app.tools.shipment_tools import ShipmentInvestigationTool


def make_order(customer_id: str = "CUST-001") -> Order:
    return Order(
        order_id="ORD-001",
        customer_id=customer_id,
        ordered_at=date(2026, 1, 10),
        status="SHIPPED",
        currency="USD",
        total_minor=2599,
    )


def make_shipment(
    shipment_id: str = "SHP-001",
    *,
    shipped_at: date | None = date(2026, 1, 11),
    delivered_at: date | None = None,
) -> Shipment:
    return Shipment(
        shipment_id=shipment_id,
        order_id="ORD-001",
        carrier="Example Carrier",
        tracking_number=f"TRACK-{shipment_id}",
        status="IN_TRANSIT",
        shipped_at=shipped_at,
        delivered_at=delivered_at,
        expected_delivery_at=date(2026, 1, 15),
        last_updated_at=date(2026, 1, 12),
        service_available=True,
    )


def make_ticket(
    customer_id: str = "CUST-001",
    order_id: str | None = "ORD-001",
) -> Ticket:
    return Ticket(
        ticket_id="TKT-001",
        customer_id=customer_id,
        order_id=order_id,
        category="GENERAL_SUPPORT",
        subject="Customer support request",
        message="Please help with my order.",
        status="OPEN",
        created_at=datetime(2026, 1, 12, tzinfo=timezone.utc),
        expected_resolution="PENDING_TRIAGE",
        scenario_tag="customer_submitted",
    )


def make_context(customer_id: str = "CUST-001") -> CustomerInvestigationContext:
    return CustomerInvestigationContext(customer_id=customer_id)


def test_order_tool_returns_structured_details_for_an_authorized_order() -> None:
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.return_value = make_order()

    report = OrderInvestigationTool(orders).get_order_details("ORD-001", make_context())

    assert report.outcome is InvestigationOutcome.COMPLETE
    assert report.order is not None
    assert report.order.model_dump() == {
        "order_id": "ORD-001",
        "ordered_at": date(2026, 1, 10),
        "status": "SHIPPED",
        "currency": "USD",
        "total_minor": 2599,
    }
    assert report.shipments is None
    orders.get_by_id.assert_called_once_with("ORD-001")


def test_order_tool_returns_controlled_not_found_for_a_missing_order() -> None:
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.return_value = None

    report = OrderInvestigationTool(orders).get_order_details("ORD-MISSING", make_context())

    assert report.outcome is InvestigationOutcome.ORDER_NOT_FOUND
    assert report.order is None


def test_order_tool_does_not_expose_another_customers_order() -> None:
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.return_value = make_order(customer_id="CUST-OTHER")

    report = OrderInvestigationTool(orders).get_order_details("ORD-001", make_context())

    assert report.outcome is InvestigationOutcome.ORDER_NOT_FOUND
    assert report.order is None


def test_shipment_tool_returns_all_shipments_in_repository_order() -> None:
    orders = Mock(spec=OrderRepository)
    shipments = Mock(spec=ShipmentRepository)
    orders.get_by_id.return_value = make_order()
    shipments.list_by_order_id.return_value = [
        make_shipment("SHP-002"),
        make_shipment("SHP-001"),
    ]

    report = ShipmentInvestigationTool(orders, shipments).get_shipment_status(
        "ORD-001",
        make_context(),
    )

    assert report.outcome is InvestigationOutcome.COMPLETE
    assert report.shipments is not None
    assert [shipment.shipment_id for shipment in report.shipments.shipments] == [
        "SHP-002",
        "SHP-001",
    ]
    shipments.list_by_order_id.assert_called_once_with("ORD-001")


def test_shipment_tool_represents_missing_optional_dates() -> None:
    orders = Mock(spec=OrderRepository)
    shipments = Mock(spec=ShipmentRepository)
    orders.get_by_id.return_value = make_order()
    shipments.list_by_order_id.return_value = [
        make_shipment(shipped_at=None, delivered_at=None),
    ]

    report = ShipmentInvestigationTool(orders, shipments).get_shipment_status(
        "ORD-001",
        make_context(),
    )

    assert report.shipments is not None
    shipment = report.shipments.shipments[0]
    assert shipment.shipped_at is None
    assert shipment.delivered_at is None


def test_shipment_tool_returns_empty_collection_for_an_authorized_order_without_shipments() -> None:
    orders = Mock(spec=OrderRepository)
    shipments = Mock(spec=ShipmentRepository)
    orders.get_by_id.return_value = make_order()
    shipments.list_by_order_id.return_value = []

    report = ShipmentInvestigationTool(orders, shipments).get_shipment_status(
        "ORD-001",
        make_context(),
    )

    assert report.outcome is InvestigationOutcome.COMPLETE
    assert report.shipments is not None
    assert report.shipments.shipments == []
    assert [(item.field, item.reason) for item in report.missing_data] == [
        ("shipments", "No shipment records were found for this order."),
    ]


def test_service_combines_authorized_ticket_order_and_shipments() -> None:
    tickets = Mock(spec=TicketRepository)
    orders = Mock(spec=OrderRepository)
    shipments = Mock(spec=ShipmentRepository)
    tickets.get_by_id.return_value = make_ticket()
    orders.get_by_id.return_value = make_order()
    shipments.list_by_order_id.return_value = [make_shipment()]
    service = InvestigationService(
        tickets,
        OrderInvestigationTool(orders),
        ShipmentInvestigationTool(orders, shipments),
    )

    report = service.investigate_order_shipping("TKT-001", make_context())

    assert report.outcome is InvestigationOutcome.COMPLETE
    assert report.ticket_id == "TKT-001"
    assert report.order is not None
    assert report.order.order_id == "ORD-001"
    assert report.shipments is not None
    assert report.shipments.shipments[0].shipment_id == "SHP-001"
    assert report.missing_data == []


def test_service_returns_controlled_not_found_for_missing_or_foreign_ticket() -> None:
    tickets = Mock(spec=TicketRepository)
    order_tool = Mock(spec=OrderInvestigationTool)
    shipment_tool = Mock(spec=ShipmentInvestigationTool)
    service = InvestigationService(tickets, order_tool, shipment_tool)

    tickets.get_by_id.side_effect = [None, make_ticket(customer_id="CUST-OTHER")]

    missing = service.investigate_order_shipping("TKT-MISSING", make_context())
    foreign = service.investigate_order_shipping("TKT-OTHER", make_context())

    assert missing.outcome is InvestigationOutcome.ORDER_NOT_FOUND
    assert foreign.outcome is InvestigationOutcome.ORDER_NOT_FOUND
    order_tool.get_order_details.assert_not_called()
    shipment_tool.get_shipment_status.assert_not_called()


def test_service_reports_a_customer_owned_ticket_without_an_order_link() -> None:
    tickets = Mock(spec=TicketRepository)
    order_tool = Mock(spec=OrderInvestigationTool)
    shipment_tool = Mock(spec=ShipmentInvestigationTool)
    tickets.get_by_id.return_value = make_ticket(order_id=None)
    service = InvestigationService(tickets, order_tool, shipment_tool)

    report = service.investigate_order_shipping("TKT-001", make_context())

    assert report.outcome is InvestigationOutcome.MISSING_ORDER_LINK
    assert report.ticket_id == "TKT-001"
    assert report.order is None
    assert report.shipments is None
    assert [item.field for item in report.missing_data] == ["order_id"]
    order_tool.get_order_details.assert_not_called()
    shipment_tool.get_shipment_status.assert_not_called()


def test_repository_errors_are_not_hidden_or_converted_to_data() -> None:
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.side_effect = SQLAlchemyError("database unavailable")

    with pytest.raises(SQLAlchemyError):
        OrderInvestigationTool(orders).get_order_details("ORD-001", make_context())

    tickets = Mock(spec=TicketRepository)
    tickets.get_by_id.side_effect = SQLAlchemyError("database unavailable")
    service = InvestigationService(
        tickets,
        Mock(spec=OrderInvestigationTool),
        Mock(spec=ShipmentInvestigationTool),
    )

    with pytest.raises(SQLAlchemyError):
        service.investigate_order_shipping("TKT-001", make_context())


def test_investigation_uses_no_writes_or_commits() -> None:
    session = Mock(spec=Session)
    session.scalar.side_effect = [make_ticket(), make_order(), make_order()]
    session.scalars.return_value = [make_shipment()]
    service = InvestigationService(
        TicketRepository(session),
        OrderInvestigationTool(OrderRepository(session)),
        ShipmentInvestigationTool(OrderRepository(session), ShipmentRepository(session)),
    )

    report = service.investigate_order_shipping("TKT-001", make_context())

    assert report.outcome is InvestigationOutcome.COMPLETE
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.delete.assert_not_called()
    session.flush.assert_not_called()


def test_tools_do_not_accept_customer_identity_as_a_business_argument() -> None:
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.return_value = make_order()
    tool = OrderInvestigationTool(orders)

    with pytest.raises(TypeError):
        tool.get_order_details(  # type: ignore[call-arg]
            "ORD-001",
            make_context(),
            customer_id="CUST-OTHER",
        )
