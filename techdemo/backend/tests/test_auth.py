from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.auth.dependencies import (
    get_current_auth_context,
    require_admin,
    require_csrf,
)
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import create_app
from app.models.user import User, UserRole
from app.models.user_session import UserSession
from app.services.auth_service import (
    AuthContext,
    AuthService,
    InvalidCredentialsError,
    InvalidSessionError,
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
        password_hash="not-exposed",
        role=role,
        customer_id=customer_id,
        is_active=True,
    )


@pytest.mark.parametrize(
    ("role", "customer_id"),
    [(UserRole.CUSTOMER, "cust-1"), (UserRole.ADMIN, None)],
)
def test_login_sets_http_only_cookie_and_returns_safe_identity(
    monkeypatch: pytest.MonkeyPatch,
    role: UserRole,
    customer_id: str | None,
) -> None:
    app = create_app()
    user = make_user(role, customer_id)
    service = Mock()
    service.authenticate.return_value = user
    service.create_session.return_value = (Mock(), "raw-session-token")
    database_session = Mock()
    app.dependency_overrides[get_db] = lambda: database_session
    app.dependency_overrides[get_settings] = make_settings
    monkeypatch.setattr("app.api.auth.routes.AuthService", lambda _: service)

    try:
        response = TestClient(app).post(
            "/v1/auth/login",
            headers={"Origin": LOCAL_API_ORIGIN},
            json={"email": user.email, "password": "correct-password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user.user_id),
        "role": role.value,
        "customer_id": customer_id,
    }
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "password_hash" not in response.text
    assert "raw-session-token" not in response.text


@pytest.mark.parametrize("email", ["unknown@example.test", "disabled@example.test"])
def test_login_returns_generic_error_for_invalid_credentials(
    monkeypatch: pytest.MonkeyPatch, email: str
) -> None:
    app = create_app()
    service = Mock()
    service.authenticate.side_effect = InvalidCredentialsError()
    app.dependency_overrides[get_db] = lambda: Mock()
    app.dependency_overrides[get_settings] = make_settings
    monkeypatch.setattr("app.api.auth.routes.AuthService", lambda _: service)

    try:
        response = TestClient(app).post(
            "/v1/auth/login",
            headers={"Origin": LOCAL_API_ORIGIN},
            json={"email": email, "password": "wrong"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_login_rejects_untrusted_browser_origin() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_db] = lambda: Mock()

    try:
        response = TestClient(app).post(
            "/v1/auth/login",
            headers={"Origin": "https://untrusted.example"},
            json={"email": "admin@example.test", "password": "password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Request origin is not allowed"}


@pytest.mark.parametrize(
    "origin", ["http://localhost:8001", "http://127.0.0.1:8001"]
)
def test_csrf_endpoint_accepts_explicit_local_api_origins(origin: str) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = make_settings

    try:
        response = TestClient(app).get("/v1/auth/csrf", headers={"Origin": origin})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert "techdemo_csrf=" in response.headers["set-cookie"]
    assert "httponly" not in response.headers["set-cookie"].lower()


def test_login_allows_a_trusted_referer_when_origin_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    user = make_user(UserRole.ADMIN)
    service = Mock()
    service.authenticate.return_value = user
    service.create_session.return_value = (Mock(), "raw-session-token")
    app.dependency_overrides[get_db] = lambda: Mock()
    app.dependency_overrides[get_settings] = make_settings
    monkeypatch.setattr("app.api.auth.routes.AuthService", lambda _: service)

    try:
        response = TestClient(app).post(
            "/v1/auth/login",
            headers={"Referer": f"{LOCAL_API_ORIGIN}/docs"},
            json={"email": user.email, "password": "correct-password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_login_rejects_missing_origin_and_referer() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_db] = lambda: Mock()

    try:
        response = TestClient(app).post(
            "/v1/auth/login",
            json={"email": "admin@example.test", "password": "password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Request origin is required"}


def test_auth_service_rejects_incorrect_password() -> None:
    service = AuthService(Mock())
    user = make_user(UserRole.ADMIN)
    user.password_hash = AuthService.hash_password("correct-password")
    service._users.get_by_email = Mock(return_value=user)

    with pytest.raises(InvalidCredentialsError):
        service.authenticate(user.email, "wrong-password")


def test_auth_service_rejects_disabled_account() -> None:
    service = AuthService(Mock())
    user = make_user(UserRole.ADMIN)
    user.is_active = False
    service._users.get_by_email = Mock(return_value=user)

    with pytest.raises(InvalidCredentialsError):
        service.authenticate(user.email, "any-password")


def test_auth_service_rejects_unknown_session() -> None:
    service = AuthService(Mock())
    service._sessions.get_by_token_hash = Mock(return_value=None)

    with pytest.raises(InvalidSessionError):
        service.get_auth_context("unknown-token")


@pytest.mark.parametrize(
    "revoked_at,expires_at",
    [
        (datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=1)),
        (None, datetime.now(timezone.utc) - timedelta(minutes=1)),
    ],
)
def test_auth_service_rejects_revoked_or_expired_session(
    revoked_at: datetime | None, expires_at: datetime
) -> None:
    service = AuthService(Mock())
    user = make_user(UserRole.ADMIN)
    user_session = UserSession(
        session_id=uuid4(),
        user_id=user.user_id,
        token_hash="hash",
        expires_at=expires_at,
        revoked_at=revoked_at,
    )
    user_session.user = user
    service._sessions.get_by_token_hash = Mock(return_value=user_session)

    with pytest.raises(InvalidSessionError):
        service.get_auth_context("invalid-or-expired-token")


def test_customer_cannot_satisfy_admin_dependency() -> None:
    with pytest.raises(HTTPException) as error:
        require_admin(make_user(UserRole.CUSTOMER, "cust-1"))

    assert error.value.status_code == 403


def test_logout_rejects_missing_csrf_token() -> None:
    app = create_app()
    user = make_user(UserRole.ADMIN)
    context = AuthContext(
        user=user,
        user_session=UserSession(
            session_id=uuid4(),
            user_id=user.user_id,
            token_hash="hash",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_current_auth_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: Mock()

    try:
        response = TestClient(app).post(
            "/v1/auth/logout", headers={"Origin": LOCAL_API_ORIGIN}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF validation failed"}


def test_logout_revokes_session_and_clears_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    user = make_user(UserRole.ADMIN)
    context = AuthContext(
        user=user,
        user_session=UserSession(
            session_id=uuid4(),
            user_id=user.user_id,
            token_hash="hash",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    service = Mock()
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_current_auth_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: Mock()
    app.dependency_overrides[require_csrf] = lambda: None
    monkeypatch.setattr("app.api.auth.routes.AuthService", lambda _: service)

    try:
        response = TestClient(app).post("/v1/auth/logout")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    service.logout.assert_called_once_with(context.user_session)
    assert "max-age=0" in response.headers["set-cookie"].lower()
