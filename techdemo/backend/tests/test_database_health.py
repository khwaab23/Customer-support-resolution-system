from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.main import create_app


def test_database_health_returns_connected_with_overridden_session() -> None:
    app = create_app()
    database_session = Mock()
    app.dependency_overrides[get_db] = lambda: database_session

    try:
        response = TestClient(app).get("/v1/health/db")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
    database_session.execute.assert_called_once()


def test_database_health_returns_503_when_query_fails() -> None:
    app = create_app()
    database_session = Mock()
    database_session.execute.side_effect = SQLAlchemyError("connection unavailable")
    app.dependency_overrides[get_db] = lambda: database_session

    try:
        response = TestClient(app).get("/v1/health/db")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
