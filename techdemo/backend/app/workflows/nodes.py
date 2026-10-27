"""Small deterministic nodes for the LangGraph support workflow."""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.types import interrupt

from app.agents.investigation_agent import InvestigationAgent
from app.repositories.ticket_repository import TicketRepository
from app.schemas.agent import AgentInvestigationStatus, InvestigationAgentResponse
from app.tools.context import CustomerInvestigationContext
from app.workflows.state import (
    HumanReviewPayload,
    ProposedResolution,
    ReviewOutcome,
    SafeReviewInput,
    SupportWorkflowState,
    WorkflowStatus,
    now_iso,
)


@dataclass(frozen=True, slots=True)
class WorkflowDependencies:
    ticket_repository: TicketRepository
    investigation_agent: InvestigationAgent


def _transition(state: SupportWorkflowState, step: str, **values: object) -> SupportWorkflowState:
    history = [*state.get("transition_history", []), step]
    return {
        "current_step": step,
        "updated_at": now_iso(),
        "transition_history": history,
        **values,
    }


def validate_ticket_node(deps: WorkflowDependencies):
    def validate_ticket(state: SupportWorkflowState) -> SupportWorkflowState:
        ticket = deps.ticket_repository.get_by_id(state["ticket_id"])
        if ticket is None or ticket.customer_id != state["customer_id"]:
            return _transition(
                state,
                "validate_ticket",
                workflow_status=WorkflowStatus.NOT_FOUND_OR_NOT_AUTHORIZED.value,
                error_code="TICKET_NOT_FOUND_OR_NOT_AUTHORIZED",
                requires_human_review=False,
            )
        return _transition(state, "validate_ticket", workflow_status=WorkflowStatus.RUNNING.value)

    return validate_ticket


def run_investigation_node(deps: WorkflowDependencies):
    def run_investigation(state: SupportWorkflowState) -> SupportWorkflowState:
        # This node is reached once for a new workflow. Resume paths begin at the
        # interrupt checkpoint and never revisit it.
        result = deps.investigation_agent.investigate(
            state["ticket_id"],
            CustomerInvestigationContext(customer_id=state["customer_id"]),
        )
        return _transition(
            state,
            "run_investigation",
            investigation_status=result.investigation_status.value,
            investigation_result=result.model_dump(mode="json"),
            missing_information=result.missing_information,
        )

    return run_investigation


def evaluate_investigation_node(state: SupportWorkflowState) -> SupportWorkflowState:
    raw = state.get("investigation_result")
    if not raw:
        return _transition(
            state,
            "evaluate_investigation",
            workflow_status=WorkflowStatus.FAILED.value,
            error_code="MISSING_INVESTIGATION_RESULT",
        )
    result = InvestigationAgentResponse.model_validate(raw)
    if result.investigation_status is AgentInvestigationStatus.COMPLETE:
        status = (
            WorkflowStatus.WAITING_HUMAN_REVIEW
            if result.requires_human_review
            else WorkflowStatus.PROPOSAL_READY
        )
    elif result.investigation_status is AgentInvestigationStatus.POLICY_REVIEW_REQUIRED:
        status = WorkflowStatus.WAITING_HUMAN_REVIEW
    elif result.investigation_status is AgentInvestigationStatus.INSUFFICIENT_EVIDENCE:
        status = WorkflowStatus.NEEDS_MORE_INFORMATION
    else:
        status = WorkflowStatus.NEEDS_MORE_INFORMATION
    return _transition(
        state,
        "evaluate_investigation",
        workflow_status=status.value,
        requires_human_review=status is WorkflowStatus.WAITING_HUMAN_REVIEW,
    )


def prepare_proposal_node(state: SupportWorkflowState) -> SupportWorkflowState:
    result = InvestigationAgentResponse.model_validate(state["investigation_result"])
    proposal = ProposedResolution(
        ticket_id=state["ticket_id"],
        issue_category=result.issue_type.value,
        verified_facts=result.verified_facts,
        policy_citations=result.policy_citations,
        missing_information=result.missing_information,
        suggested_next_action=(
            result.recommended_next_steps[0]
            if result.recommended_next_steps
            else "Request human review before taking further action."
        ),
        requires_human_review=result.requires_human_review,
    )
    return _transition(
        state,
        "prepare_proposal",
        proposed_resolution=proposal.model_dump(mode="json"),
        workflow_status=(
            WorkflowStatus.WAITING_HUMAN_REVIEW.value
            if result.requires_human_review
            else WorkflowStatus.PROPOSAL_READY.value
        ),
        human_review_reason=(
            "The grounded investigation requires a trusted human review."
            if result.requires_human_review
            else None
        ),
    )


def prepare_missing_information_node(state: SupportWorkflowState) -> SupportWorkflowState:
    result = InvestigationAgentResponse.model_validate(state["investigation_result"])
    proposal = ProposedResolution(
        ticket_id=state["ticket_id"],
        issue_category=result.issue_type.value,
        verified_facts=result.verified_facts,
        policy_citations=result.policy_citations,
        missing_information=result.missing_information,
        suggested_next_action="Request human review or the missing evidence before further action.",
        requires_human_review=True,
    )
    return _transition(
        state,
        "prepare_missing_information",
        workflow_status=WorkflowStatus.NEEDS_MORE_INFORMATION.value,
        proposed_resolution=proposal.model_dump(mode="json"),
        requires_human_review=True,
        human_review_reason="Verified investigation evidence is incomplete.",
    )


def human_review_interrupt_node(state: SupportWorkflowState) -> SupportWorkflowState:
    """Pause after all side-effect-free preparation; this node reruns on resume."""
    result = InvestigationAgentResponse.model_validate(state["investigation_result"])
    payload = HumanReviewPayload(
        workflow_id=state["workflow_id"],
        ticket_id=state["ticket_id"],
        reason=state.get("human_review_reason")
        or "Human review is required before any business decision.",
        evidence_summary=[fact.value for fact in result.verified_facts],
        policy_citations=result.policy_citations,
    )
    raw_review = interrupt(payload.model_dump(mode="json"))
    review = SafeReviewInput.model_validate(raw_review)
    status = (
        WorkflowStatus.COMPLETED
        if review.outcome is ReviewOutcome.ACKNOWLEDGED
        else WorkflowStatus.NEEDS_MORE_INFORMATION
    )
    return _transition(
        state,
        "human_review_interrupt",
        workflow_status=status.value,
        requires_human_review=False,
        human_review_reason=(
            "Trusted reviewer requested more information."
            if review.outcome is ReviewOutcome.REQUEST_MORE_INFORMATION
            else "Trusted reviewer acknowledged the proposed resolution."
        ),
    )
