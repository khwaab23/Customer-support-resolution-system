"""Route-level access checks with overridden services; no live database/workflow."""

from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.admin.routes import get_admin_review_service
from app.api.auth.dependencies import require_admin, require_csrf
from app.main import create_app
from app.models.user import User, UserRole
from app.schemas.review import AdminReviewDetail, EligibilityAssessment, EligibilityStatus, ReviewStatus


def _admin() -> User:
    return User(user_id=uuid4(), email="admin@example.test", password_hash="x", role=UserRole.ADMIN, customer_id=None, is_active=True)


def _detail() -> AdminReviewDetail:
    return AdminReviewDetail(
        review_id=str(uuid4()), ticket_id="TKT-1", workflow_id="workflow-1", issue_category="REFUND",
        review_status=ReviewStatus.PENDING, eligibility_status=EligibilityStatus.NEEDS_REVIEW,
        created_at=datetime.now(timezone.utc), resume_state="PENDING", ticket_message="Need help",
        assessment=EligibilityAssessment(assessment_status=EligibilityStatus.NEEDS_REVIEW, evaluated_at=datetime.now(timezone.utc)),
        version=1,
    )


def test_customer_is_denied_admin_queue() -> None:
    app = create_app()
    app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(HTTPException(403, "Administrator role required"))
    try:
        response = TestClient(app).get("/v1/admin/reviews")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_decision_requires_csrf_before_service_is_called() -> None:
    app, service, detail = create_app(), Mock(), _detail()
    app.dependency_overrides[require_admin] = _admin
    app.dependency_overrides[require_csrf] = lambda: (_ for _ in ()).throw(HTTPException(403, "CSRF validation failed"))
    app.dependency_overrides[get_admin_review_service] = lambda: service
    try:
        response = TestClient(app).post(f"/v1/admin/reviews/{detail.review_id}/decision", json={"decision": "REJECT", "reason": "Not eligible", "version": 1})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == status.HTTP_403_FORBIDDEN
    service.submit_decision.assert_not_called()


def test_admin_decision_uses_authenticated_identity_not_request_identity() -> None:
    app, service, detail, admin = create_app(), Mock(), _detail(), _admin()
    service.get_detail.return_value = detail
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[require_csrf] = lambda: None
    app.dependency_overrides[get_admin_review_service] = lambda: service
    try:
        response = TestClient(app).post(f"/v1/admin/reviews/{detail.review_id}/decision", json={"decision": "REQUEST_MORE_INFORMATION", "reason": "Need inspection evidence", "version": 3})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == status.HTTP_200_OK
    reviewer = service.submit_decision.call_args.args[2]
    assert reviewer.user_id == str(admin.user_id)
