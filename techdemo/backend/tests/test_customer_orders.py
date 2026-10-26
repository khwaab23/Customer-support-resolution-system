from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.auth.dependencies import get_current_user, require_customer
from app.api.customer.routes import get_order_service
from app.core.database import get_db
from app.main import create_app
from app.models.order import Order
from app.models.user import User, UserRole
from app.repositories.order_repository import OrderRepository
from app.services.order_service import OrderService


def make_user(role: UserRole, customer_id: str | None = None) -> User:
    return User(
        user_id=uuid4(),
        email=f"{role.value.lower()}@example.test",
        password_hash="not-used",
        role=role,
        customer_id=customer_id,
        is_active=True,
    )


def make_order(
    order_id: str,
    customer_id: str,
    ordered_at: date = date(2025, 1, 1),
) -> Order:
    return Order(
        order_id=order_id,
        customer_id=customer_id,
        ordered_at=ordered_at,
        status="COMPLETED",
        currency="USD",
        total_minor=1250,
    )


def app_with_customer_and_service(user: User, service: Mock):
    app = create_app()
    app.dependency_overrides[require_customer] = lambda: user
    app.dependency_overrides[get_order_service] = lambda: service
    return app


def test_unauthenticated_order_request_returns_401() -> None:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: Mock()

    try:
        response = TestClient(app).get("/v1/customer/orders")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_customer_can_list_only_own_orders_with_default_limit() -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    service.list_customer_orders.return_value = [
        make_order("order-003", "cust-1", date(2025, 2, 1)),
        make_order("order-001", "cust-1", date(2025, 1, 1)),
        make_order("order-002", "cust-1", date(2025, 1, 1)),
    ]
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).get("/v1/customer/orders")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [item["order_id"] for item in response.json()["orders"]] == [
        "order-003",
        "order-001",
        "order-002",
    ]
    assert all(
        set(order) == {"order_id", "ordered_at", "status", "currency", "total_minor"}
        for order in response.json()["orders"]
    )
    service.list_customer_orders.assert_called_once_with("cust-1", 10)


def test_customer_can_use_maximum_limit() -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    service.list_customer_orders.return_value = []
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).get("/v1/customer/orders?limit=50")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"orders": []}
    service.list_customer_orders.assert_called_once_with("cust-1", 50)


@pytest.mark.parametrize("limit", [0, 51])
def test_order_list_rejects_invalid_limits(limit: int) -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).get(f"/v1/customer/orders?limit={limit}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    service.list_customer_orders.assert_not_called()


def test_customer_can_retrieve_own_order() -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    service.get_customer_order.return_value = make_order("order-001", "cust-1")
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).get("/v1/customer/orders/order-001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["order_id"] == "order-001"
    assert "customer_id" not in response.json()
    service.get_customer_order.assert_called_once_with("cust-1", "order-001")


@pytest.mark.parametrize("order_id", ["other-customer-order", "missing-order"])
def test_customer_cannot_retrieve_missing_or_unowned_order(order_id: str) -> None:
    user = make_user(UserRole.CUSTOMER, "cust-1")
    service = Mock()
    service.get_customer_order.return_value = None
    app = app_with_customer_and_service(user, service)

    try:
        response = TestClient(app).get(f"/v1/customer/orders/{order_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Order not found"}


def test_admin_cannot_access_customer_orders() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.ADMIN)

    try:
        response = TestClient(app).get("/v1/customer/orders")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_order_service_enforces_customer_ownership() -> None:
    repository = Mock(spec=OrderRepository)
    own_order = make_order("order-001", "cust-1")
    repository.get_by_id.side_effect = [own_order, make_order("order-002", "cust-2"), None]
    service = OrderService(repository)

    assert service.get_customer_order("cust-1", "order-001") is own_order
    assert service.get_customer_order("cust-1", "order-002") is None
    assert service.get_customer_order("cust-1", "missing") is None
