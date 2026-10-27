"""Serializable state and trusted boundary contracts for support workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agent import AgentPolicyCitation, VerifiedFact


class WorkflowStatus(str, Enum):
    RUNNING = "RUNNING"
    PROPOSAL_READY = "PROPOSAL_READY"
    WAITING_HUMAN_REVIEW = "WAITING_HUMAN_REVIEW"
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"
    COMPLETED = "COMPLETED"
    NOT_FOUND_OR_NOT_AUTHORIZED = "NOT_FOUND_OR_NOT_AUTHORIZED"
    FAILED = "FAILED"


class ReviewOutcome(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REQUEST_MORE_INFORMATION = "REQUEST_MORE_INFORMATION"


class SafeReviewInput(BaseModel):
    """Development-only input shape; it cannot approve or execute anything."""

    model_config = ConfigDict(extra="forbid")

    outcome: ReviewOutcome


class ProposedResolution(BaseModel):
    """A factual proposal, never a mutable business decision or refund command."""

    ticket_id: str
    issue_category: str
    verified_facts: list[VerifiedFact] = Field(default_factory=list)
    policy_citations: list[AgentPolicyCitation] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    suggested_next_action: str
    requires_human_review: bool
    is_approval: bool = False
    will_execute: bool = False


class HumanReviewPayload(BaseModel):
    """The safe, minimal payload persisted before a LangGraph interrupt."""

    workflow_id: str
    ticket_id: str
    reason: str
    evidence_summary: list[str] = Field(default_factory=list)
    policy_citations: list[AgentPolicyCitation] = Field(default_factory=list)


class SupportWorkflowState(TypedDict, total=False):
    workflow_id: str
    ticket_id: str
    customer_id: str
    workflow_status: str
    current_step: str
    investigation_status: str | None
    investigation_result: dict[str, Any] | None
    proposed_resolution: dict[str, Any] | None
    requires_human_review: bool
    human_review_reason: str | None
    missing_information: list[str]
    error_code: str | None
    created_at: str
    updated_at: str
    transition_history: list[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
