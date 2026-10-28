"""Transactional administration of human review decisions.

This service records a decision before attempting a LangGraph resume.  The two
systems are deliberately not presented as one distributed transaction: a failed
resume leaves an auditable decision with ``RESUME_FAILED`` for safe retry.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.admin_review import AdminReview
from app.models.audit_event import AuditEvent
from app.repositories.admin_review_repository import AdminReviewRepository
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.review import (
    AdminReviewDetail,
    AdminReviewSummary,
    EligibilityAssessment,
    EligibilityStatus,
    ReviewDecision,
    ReviewDecisionRequest,
    ReviewStatus,
)
from app.services.refund_eligibility_service import RefundEligibilityService
from app.services.support_workflow_service import (
    SupportWorkflowService,
    TrustedReviewerContext,
    WorkflowConflictError,
)
from app.tools.context import CustomerInvestigationContext


class ReviewNotFoundError(ValueError):
    pass


class ReviewConflictError(ValueError):
    pass


class ReviewValidationError(ValueError):
    pass


class AdminReviewService:
    def __init__(
        self,
        session: Session,
        reviews: AdminReviewRepository,
        tickets: TicketRepository,
        eligibility: RefundEligibilityService,
        workflows: SupportWorkflowService,
        audits: AuditEventRepository,
    ) -> None:
        self._session = session
        self._reviews = reviews
        self._tickets = tickets
        self._eligibility = eligibility
        self._workflows = workflows
        self._audits = audits

    def ensure_for_paused_workflow(self, workflow_id: str) -> AdminReview:
        """Create exactly one review only after a verified graph pause."""
        existing = self._reviews.get_by_workflow(workflow_id)
        if existing is not None:
            return existing
        entry = self._workflows.get_workflow_entry(workflow_id)
        if entry is None or not self._workflows.is_waiting_for_human_review(workflow_id):
            raise ReviewConflictError("Workflow is not waiting for human review.")
        ticket = self._tickets.get_by_id(entry.ticket_id)
        if ticket is None or ticket.customer_id != entry.customer_id:
            raise ReviewNotFoundError("Ticket not found.")
        assessment = self._eligibility.assess(
            ticket.ticket_id, CustomerInvestigationContext(customer_id=ticket.customer_id)
        )
        review = AdminReview(
            workflow_id=workflow_id,
            ticket_id=ticket.ticket_id,
            order_id=ticket.order_id,
            review_status=ReviewStatus.PENDING.value,
            eligibility_snapshot=assessment.model_dump(mode="json"),
            resume_state="PENDING",
        )
        try:
            # A unique workflow_id constraint is the final duplicate guard.
            self._reviews.add(review)
            self._session.commit()
        except Exception:
            self._session.rollback()
            winner = self._reviews.get_by_workflow(workflow_id)
            if winner is not None:
                return winner
            raise
        return review

    def list_reviews(self, status: ReviewStatus | None, offset: int, limit: int) -> list[AdminReviewSummary]:
        summaries: list[AdminReviewSummary] = []
        for review in self._reviews.list(status.value if status else None, offset, limit):
            ticket = self._tickets.get_by_id(review.ticket_id)
            summaries.append(self._summary(review, ticket.category if ticket else "UNKNOWN"))
        return summaries

    def get_detail(self, review_id: UUID) -> AdminReviewDetail:
        review = self._require_review(review_id)
        ticket = self._tickets.get_by_id(review.ticket_id)
        if ticket is None:
            raise ReviewNotFoundError("Review ticket not found.")
        workflow_status = self._workflows.get_workflow_status_for_admin(review.workflow_id)
        assessment = EligibilityAssessment.model_validate(review.eligibility_snapshot)
        events = self._audits.list_for_ticket(ticket.ticket_id)
        return AdminReviewDetail(
            **self._summary(review, ticket.category).model_dump(),
            ticket_message=ticket.message,
            assessment=assessment,
            decision=ReviewDecision(review.decision) if review.decision else None,
            decision_reason=review.decision_reason,
            decided_at=review.decided_at,
            decided_by=str(review.decided_by) if review.decided_by else None,
            investigation_status=(workflow_status or {}).get("investigation_status"),
            workflow_status=(workflow_status or {}).get("workflow_status"),
            audit_events=[event.event_type for event in events],
            version=review.version,
        )

    def submit_decision(
        self,
        review_id: UUID,
        request: ReviewDecisionRequest,
        reviewer: TrustedReviewerContext,
    ) -> AdminReview:
        if not reviewer.is_admin:
            raise ReviewNotFoundError("Review not found.")
        review = self._require_review(review_id)
        try:
            reason = request.validated_reason()
        except ValueError as exc:
            raise ReviewValidationError(str(exc)) from exc
        if review.decision is not None:
            if review.decision == request.decision.value and review.decision_reason == reason:
                return review  # idempotent replay; it cannot create another transition
            raise ReviewConflictError("Review has already been decided.")
        if review.version != request.version:
            raise ReviewConflictError("Review changed; refresh and try again.")
        assessment = EligibilityAssessment.model_validate(review.eligibility_snapshot)
        if request.decision is ReviewDecision.APPROVE:
            self._validate_approval(review, assessment)
            new_status = ReviewStatus.APPROVED_INTERNAL
        elif request.decision is ReviewDecision.REJECT:
            new_status = ReviewStatus.REJECTED
        else:
            new_status = ReviewStatus.INFORMATION_REQUESTED
        decided_at = datetime.now(timezone.utc)
        values: dict[str, object] = {
            "decision": request.decision.value,
            "decision_reason": reason,
            "decided_by": UUID(reviewer.user_id),
            "decided_at": decided_at,
            "review_status": new_status.value,
            "resume_state": "RESUME_PENDING",
        }
        try:
            if not self._reviews.decide(review.review_id, request.version, values):
                raise ReviewConflictError("Review changed; refresh and try again.")
            self._audits.add(
                AuditEvent(
                    event_id=f"review-{uuid4()}",
                    ticket_id=review.ticket_id,
                    event_type="ADMIN_REVIEW_DECISION_RECORDED",
                    actor=reviewer.user_id,
                    recorded_at=decided_at,
                    details=json.dumps({"review_id": str(review.review_id), "decision": request.decision.value}),
                )
            )
            self._session.commit()
        except ReviewConflictError:
            self._session.rollback()
            raise
        review = self._require_review(review_id)
        self._resume_durably_recorded(review, reviewer)
        return self._require_review(review_id)

    def retry_resume(self, review_id: UUID, reviewer: TrustedReviewerContext) -> AdminReview:
        review = self._require_review(review_id)
        if review.decision is None or review.resume_state not in {"RESUME_PENDING", "RESUME_FAILED"}:
            raise ReviewConflictError("Review has no recoverable pending resume.")
        self._resume_durably_recorded(review, reviewer)
        return self._require_review(review_id)

    def _resume_durably_recorded(self, review: AdminReview, reviewer: TrustedReviewerContext) -> None:
        try:
            self._workflows.resume_admin_decision(
                review.workflow_id, reviewer, review.decision or ""
            )
        except (WorkflowConflictError, Exception):
            # The decision remains durable.  A privileged retry can replay the
            # same persisted value; no new decision or refund is created.
            self._reviews.set_resume_state(review.review_id, "RESUME_FAILED")
            self._session.commit()
            raise ReviewConflictError("Decision was recorded, but workflow resumption failed.") from None
        self._reviews.set_resume_state(review.review_id, "COMPLETED")
        self._session.commit()

    def _validate_approval(self, review: AdminReview, assessment: EligibilityAssessment) -> None:
        if assessment.assessment_status is not EligibilityStatus.ELIGIBLE:
            raise ReviewValidationError("Approval requires a verified eligible assessment.")
        if assessment.proposed_refundable_amount_minor is None or review.order_id is None:
            raise ReviewValidationError("Approval requires a verified refundable amount and order.")
        if self._reviews.other_approved_review_exists(review.order_id, review.review_id):
            raise ReviewValidationError("An approval already exists for this order.")

    def _require_review(self, review_id: UUID) -> AdminReview:
        review = self._reviews.get(review_id)
        if review is None:
            raise ReviewNotFoundError("Review not found.")
        return review

    @staticmethod
    def _summary(review: AdminReview, issue_category: str) -> AdminReviewSummary:
        assessment = EligibilityAssessment.model_validate(review.eligibility_snapshot)
        # Category is deliberately derived from the persisted assessment surface;
        # the detail endpoint uses the actual ticket for free-text content.
        return AdminReviewSummary(
            review_id=str(review.review_id), ticket_id=review.ticket_id,
            workflow_id=review.workflow_id, issue_category=issue_category,
            review_status=ReviewStatus(review.review_status),
            eligibility_status=assessment.assessment_status,
            created_at=review.created_at, resume_state=review.resume_state,
        )
