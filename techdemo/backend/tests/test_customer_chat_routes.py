from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.auth.dependencies import require_csrf, require_customer
from app.api.customer.chat_routes import get_chat_service
from app.main import create_app
from app.models.user import User, UserRole


def _customer() -> User:
    return User(user_id=uuid4(), email="customer@example.test", password_hash="x", role=UserRole.CUSTOMER, customer_id="CUST-1", is_active=True)


def _conversation():
    now = datetime.now(timezone.utc)
    return SimpleNamespace(conversation_id=uuid4(), selected_order_id=None, linked_ticket_id=None, status="OPEN", version=1, created_at=now, updated_at=now, review_status=None)


def test_customer_chat_creation_uses_authenticated_customer_and_csrf() -> None:
    app, service, user = create_app(), Mock(), _customer()
    service.create.return_value = _conversation()
    app.dependency_overrides[require_customer] = lambda: user
    app.dependency_overrides[require_csrf] = lambda: None
    app.dependency_overrides[get_chat_service] = lambda: service
    try:
        response = TestClient(app).post("/v1/customer/chat/conversations", json={})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    assert service.create.call_args.args[0] == "CUST-1"


def test_customer_denied_before_chat_service_runs() -> None:
    app, service = create_app(), Mock()
    app.dependency_overrides[require_customer] = lambda: (_ for _ in ()).throw(HTTPException(403, "Customer role required"))
    app.dependency_overrides[get_chat_service] = lambda: service
    try:
        response = TestClient(app).get("/v1/customer/chat/conversations")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    service.list.assert_not_called()
