"""Validated contracts for the customer-facing AI investigation result."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AgentIssueType(str, Enum):
    ORDER_STATUS = "ORDER_STATUS"
    SHIPPING = "SHIPPING"
    PAYMENT = "PAYMENT"
    RETURN = "RETURN"
    REFUND = "REFUND"
    DAMAGED_ITEM = "DAMAGED_ITEM"
    GENERAL_SUPPORT = "GENERAL_SUPPORT"
    UNKNOWN = "UNKNOWN"


class AgentInvestigationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    POLICY_REVIEW_REQUIRED = "POLICY_REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    TOOL_LIMIT_REACHED = "TOOL_LIMIT_REACHED"
    MODEL_ERROR = "MODEL_ERROR"
    NOT_FOUND_OR_NOT_AUTHORIZED = "NOT_FOUND_OR_NOT_AUTHORIZED"


class AgentRecommendationType(str, Enum):
    """Bounded recommendation intents; none can authorize a business action."""

    INFORMATIONAL = "INFORMATIONAL"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class EvidenceReference(BaseModel):
    """A model-selected path to a value returned by an executed tool."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(
        min_length=1,
        max_length=64,
        description="Name of a successfully executed tool.",
    )
    json_pointer: str = Field(
        pattern=r"^/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])+)*$",
        description=(
            "RFC 6901 pointer rooted at the successful tool result itself, not a wrapper. "
            "Example: /returns/returns/0/status."
        ),
    )


class VerifiedFact(BaseModel):
    """A server-resolved fact that the model cannot fabricate directly."""

    tool_name: str
    json_pointer: str
    value: str


class AgentPolicyCitation(BaseModel):
    """An exact reference to a passage returned by policy lookup in this run."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    source: str = Field(min_length=1)
    section_heading: str = Field(min_length=1)
    effective_date: date | None


class AgentDraftResponse(BaseModel):
    """Strict model output, validated and resolved by trusted application code."""

    model_config = ConfigDict(extra="forbid")

    issue_type: AgentIssueType
    recommendation_type: AgentRecommendationType
    customer_explanation: str = Field(min_length=1, max_length=2_000)
    evidence_references: list[EvidenceReference] = Field(max_length=12)
    policy_citations: list[AgentPolicyCitation] = Field(max_length=12)
    missing_information: list[str] = Field(max_length=12)
    recommended_next_steps: list[str] = Field(max_length=8)
    requires_human_review: bool


class InvestigationAgentResponse(BaseModel):
    """Safe final response after citations and factual values are validated."""

    ticket_id: str
    issue_type: AgentIssueType
    investigation_status: AgentInvestigationStatus
    recommendation_type: AgentRecommendationType = AgentRecommendationType.HUMAN_REVIEW
    customer_explanation: str
    verified_facts: list[VerifiedFact] = Field(default_factory=list)
    policy_citations: list[AgentPolicyCitation] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    requires_human_review: bool
    tools_executed: list[str] = Field(default_factory=list)
