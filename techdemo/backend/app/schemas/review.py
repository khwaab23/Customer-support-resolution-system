from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.agent import AgentPolicyCitation, VerifiedFact


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_MORE_INFORMATION = "REQUEST_MORE_INFORMATION"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    INFORMATION_REQUESTED = "INFORMATION_REQUESTED"
    APPROVED_INTERNAL = "APPROVED_INTERNAL"
    REJECTED = "REJECTED"
    RESUME_PENDING = "RESUME_PENDING"
    RESUME_FAILED = "RESUME_FAILED"
    COMPLETED = "COMPLETED"


class EligibilityAssessment(BaseModel):
    assessment_status: EligibilityStatus
    reasons: list[str] = Field(default_factory=list)
    verified_facts: list[VerifiedFact] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    policy_references: list[AgentPolicyCitation] = Field(default_factory=list)
    evaluated_at: datetime
    applicable_policy_version: str | None = None
    proposed_refundable_amount_minor: int | None = Field(default=None, ge=1)


class ReviewDecisionRequest(BaseModel):
    decision: ReviewDecision
    reason: str | None = Field(default=None, max_length=2000)
    version: int = Field(ge=1)

    def validated_reason(self) -> str | None:
        value = self.reason.strip() if self.reason else None
        if self.decision in {ReviewDecision.REJECT, ReviewDecision.REQUEST_MORE_INFORMATION} and not value:
            raise ValueError("A reason is required for this decision.")
        return value


class AdminReviewSummary(BaseModel):
    review_id: str
    ticket_id: str
    workflow_id: str
    issue_category: str
    review_status: ReviewStatus
    eligibility_status: EligibilityStatus
    created_at: datetime
    resume_state: str


class AdminReviewDetail(AdminReviewSummary):
    ticket_message: str
    assessment: EligibilityAssessment
    decision: ReviewDecision | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    investigation_status: str | None = None
    workflow_status: str | None = None
    audit_events: list[str] = Field(default_factory=list)
    version: int


class AdminReviewListResponse(BaseModel):
    reviews: list[AdminReviewSummary]
    offset: int
    limit: int
