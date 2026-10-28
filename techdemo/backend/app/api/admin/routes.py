"""Authenticated, CSRF-protected administrative review endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth.dependencies import require_admin, require_csrf
from app.core.database import get_db
from app.models.user import User
from app.repositories.admin_review_repository import AdminReviewRepository
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.review import (
    AdminReviewDetail, AdminReviewListResponse, ReviewDecisionRequest, ReviewStatus,
)
from app.services.admin_review_service import (
    AdminReviewService, ReviewConflictError, ReviewNotFoundError, ReviewValidationError,
)
from app.services.support_workflow_service import TrustedReviewerContext
from app.workflows.factory import build_refund_eligibility_service, build_support_workflow_service

router = APIRouter()


def get_admin_review_service(db: Annotated[Session, Depends(get_db)]) -> AdminReviewService:
    return AdminReviewService(
        db, AdminReviewRepository(db), TicketRepository(db),
        build_refund_eligibility_service(db), build_support_workflow_service(db),
        AuditEventRepository(db),
    )


def reviewer_for(user: User) -> TrustedReviewerContext:
    return TrustedReviewerContext(user_id=str(user.user_id), is_admin=True)


@router.get("/reviews", response_model=AdminReviewListResponse)
def list_reviews(
    _: Annotated[User, Depends(require_admin)],
    service: Annotated[AdminReviewService, Depends(get_admin_review_service)],
    review_status: Annotated[ReviewStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminReviewListResponse:
    return AdminReviewListResponse(
        reviews=service.list_reviews(review_status, offset, limit), offset=offset, limit=limit
    )


@router.get("/reviews/{review_id}", response_model=AdminReviewDetail)
def get_review(
    review_id: UUID,
    _: Annotated[User, Depends(require_admin)],
    service: Annotated[AdminReviewService, Depends(get_admin_review_service)],
) -> AdminReviewDetail:
    try:
        return service.get_detail(review_id)
    except ReviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found") from None


@router.post("/reviews/{review_id}/decision", response_model=AdminReviewDetail)
def decide_review(
    review_id: UUID,
    payload: ReviewDecisionRequest,
    user: Annotated[User, Depends(require_admin)],
    _: Annotated[None, Depends(require_csrf)],
    service: Annotated[AdminReviewService, Depends(get_admin_review_service)],
) -> AdminReviewDetail:
    try:
        service.submit_decision(review_id, payload, reviewer_for(user))
        return service.get_detail(review_id)
    except ReviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found") from None
    except ReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    except ReviewConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None


@router.post("/reviews/{review_id}/retry-resume", response_model=AdminReviewDetail)
def retry_review_resume(
    review_id: UUID,
    user: Annotated[User, Depends(require_admin)],
    _: Annotated[None, Depends(require_csrf)],
    service: Annotated[AdminReviewService, Depends(get_admin_review_service)],
) -> AdminReviewDetail:
    try:
        service.retry_resume(review_id, reviewer_for(user))
        return service.get_detail(review_id)
    except ReviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found") from None
    except ReviewConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
