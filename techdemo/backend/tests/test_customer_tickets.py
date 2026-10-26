from datetime import date, datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth.dependencies import get_current_user, require_csrf, require_customer
from app.api.customer.routes import get_ticket_service
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import create_app
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.user import User, UserRole
from app.repositories.order_repository import OrderRepository
from app.repositories.ticket_repository import TicketRepository
from app.services.ticket_service import (
    INITIAL_STATUS,
    TicketOrderNotFoundError,
    TicketPersistenceError,
    TicketService,
)

LOCAL_API_ORIGIN = "http://127.0.0.1:8001"


def make_settings() -> Settings:
    return Settings.model_construct(
        db_host="unused",
        db_port=5432,
        db_name="unused",
        db_user="unused",
        db_password="unused",
        app_environment="development",
        session_cookie_name="techdemo_session",
        csrf_cookie_name="techdemo_csrf",
        session_cookie_secure=False,
        session_cookie_samesite="lax",
        session_ttl_minutes=480,
        trusted_origins=(
            "http://localhost:3000,"
            "http://127.0.0.1:3000,"
            "http://localhost:8001,"
            "http://127.0.0.1:8001"
        ),
    )


def make_user(role: UserRole, customer_id: str | None = None) -> User:
    return User(
        user_id=uuid4(),
        email=f"{role.value.lower()}@example.test",
        password_hash="not-used",
        role=role,
        customer_id=customer_id,
        is_active=True,
    )


def make_order(order_id: str, customer_id: str) -> Order:
    return Order(
        order_id=order_id,
        customer_id=customer_id,
        ordered_at=date(2026, 1, 2),
        status="COMPLETED",
        currency="USD",
        total_minor=2500,
    )


def make_ticket(ticket_id: str = "TKT-NEW", customer_id: str = "cust-1") -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        customer_id=customer_id,
        order_id="order-1",
        category="GENERAL_SUPPORT",
        subject="Customer support request",
        message="Please help with my order.",
        status="OPEN",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        expected_resolution="PENDING_TRIAGE",
        scenario_tag="customer_submitted",
    )


def app_with_customer_and_service(user: User, service: Mock):
    app = create_app()
    app.dependency_overrides[require_customer] = lambda: user
    app.dependency_overrides[require_csrf] = lambda: None
    app.dependency_overrides[get_ticket_service] = lambda: service
    return app


def render_postgresql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_customer_can_create_a_ticket() -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    service.create_customer_ticket.return_value = make_ticket()
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).post(
            "/v1/customer/tickets",
            json={"order_id": "order-1", "message": "Please help with my order."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {
        "ticket_id": "TKT-NEW",
        "order_id": "order-1",
        "message": "Please help with my order.",
        "status": "OPEN",
        "created_at": "2026-01-02T00:00:00Z",
    }
    service.create_customer_ticket.assert_called_once_with(
        customer_id="cust-1",
        order_id="order-1",
        message="Please help with my order.",
    )


def test_unauthenticated_ticket_creation_returns_401() -> None:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: Mock()

    try:
        response = TestClient(app).post(
            "/v1/customer/tickets",
            json={"order_id": "order-1", "message": "Need help"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_admin_cannot_access_customer_ticket_endpoints() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.ADMIN)

    try:
        response = TestClient(app).get("/v1/customer/tickets")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.parametrize("order_id", ["other-customer-order", "missing-order"])
def test_unowned_or_missing_order_returns_404(order_id: str) -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    service.create_customer_ticket.side_effect = TicketOrderNotFoundError()
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).post(
            "/v1/customer/tickets",
            json={"order_id": order_id, "message": "Need help"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Order not found"}


@pytest.mark.parametrize("message", ["", "   ", "x" * 5001])
def test_ticket_request_rejects_empty_or_excessively_long_messages(message: str) -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).post(
            "/v1/customer/tickets",
            json={"order_id": "order-1", "message": message},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    service.create_customer_ticket.assert_not_called()


def test_customer_can_list_only_own_tickets() -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    service.list_customer_tickets.return_value = [make_ticket("TKT-002"), make_ticket("TKT-001")]
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).get("/v1/customer/tickets?limit=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [ticket["ticket_id"] for ticket in response.json()["tickets"]] == [
        "TKT-002",
        "TKT-001",
    ]
    service.list_customer_tickets.assert_called_once_with("cust-1", 2)


def test_customer_cannot_retrieve_another_customers_ticket() -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    service.get_customer_ticket.return_value = None
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).get("/v1/customer/tickets/TKT-OTHER")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}
    service.get_customer_ticket.assert_called_once_with("cust-1", "TKT-OTHER")


def test_ticket_creation_requires_csrf_protection() -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    app = create_app()
    app.dependency_overrides[require_customer] = lambda: user
    app.dependency_overrides[get_ticket_service] = lambda: service
    app.dependency_overrides[get_settings] = make_settings

    try:
        response = TestClient(app).post(
            "/v1/customer/tickets",
            headers={"Origin": LOCAL_API_ORIGIN},
            json={"order_id": "order-1", "message": "Need help"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF validation failed"}
    service.create_customer_ticket.assert_not_called()


def test_ticket_repository_filters_sorts_and_checks_ownership() -> None:
    session = Mock(spec=Session)
    session.scalars.return_value = [make_ticket("TKT-003"), make_ticket("TKT-002")]
    session.scalar.side_effect = [make_ticket("TKT-003"), "TKT-003", None]
    repository = TicketRepository(session)

    assert [ticket.ticket_id for ticket in repository.list_by_customer("cust-1")] == [
        "TKT-003",
        "TKT-002",
    ]
    list_query = render_postgresql(session.scalars.call_args.args[0])
    assert "WHERE tickets.customer_id = 'cust-1'" in list_query
    assert "ORDER BY tickets.created_at DESC, tickets.ticket_id ASC" in list_query
    assert "LIMIT 10" in list_query

    assert repository.get_by_id_for_customer("cust-1", "TKT-003") is not None
    assert repository.is_owned_by_customer("cust-1", "TKT-003") is True
    assert repository.is_owned_by_customer("cust-1", "TKT-OTHER") is False


def test_ticket_service_commits_a_new_ticket_only_after_order_ownership_check() -> None:
    session = Mock(spec=Session)
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.return_value = make_order("order-1", "cust-1")
    service = TicketService(TicketRepository(session), orders, session)

    ticket = service.create_customer_ticket("cust-1", "order-1", "Need help")

    assert ticket.ticket_id.startswith("TKT-")
    assert len(ticket.ticket_id) <= 30
    assert ticket.status == INITIAL_STATUS
    assert ticket.customer_id == "cust-1"
    assert ticket.order_id == "order-1"
    session.add.assert_called_once_with(ticket)
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_ticket_service_returns_not_found_for_another_customers_order() -> None:
    session = Mock(spec=Session)
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.return_value = make_order("order-1", "cust-2")
    service = TicketService(TicketRepository(session), orders, session)

    with pytest.raises(TicketOrderNotFoundError):
        service.create_customer_ticket("cust-1", "order-1", "Need help")

    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_ticket_service_rolls_back_when_database_commit_fails() -> None:
    session = Mock(spec=Session)
    session.commit.side_effect = SQLAlchemyError("database unavailable")
    orders = Mock(spec=OrderRepository)
    orders.get_by_id.return_value = make_order("order-1", "cust-1")
    service = TicketService(TicketRepository(session), orders, session)

    with pytest.raises(TicketPersistenceError):
        service.create_customer_ticket("cust-1", "order-1", "Need help")

    session.add.assert_called_once()
    session.commit.assert_called_once()
    session.rollback.assert_called_once()
