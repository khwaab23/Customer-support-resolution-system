from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.models.ticket import Ticket
from app.schemas.agent import (
    AgentInvestigationStatus,
    AgentIssueType,
    AgentRecommendationType,
    InvestigationAgentResponse,
)
from app.services.support_workflow_service import (
    SupportWorkflowService,
    TrustedReviewerContext,
    WorkflowAccessError,
    WorkflowConflictError,
)
from app.tools.context import CustomerInvestigationContext
from app.workflows.nodes import WorkflowDependencies
from app.workflows.registry import WorkflowRegistryEntry
from app.workflows.state import ReviewOutcome, SafeReviewInput, WorkflowStatus
from app.workflows.support_graph import build_support_graph


def ticket(customer_id: str = "CUST-001") -> Ticket:
    return Ticket(
        ticket_id="TKT-201", customer_id=customer_id, order_id="ORD-1001", category="REFUND",
        subject="Refund", message="Missing refund", status="OPEN",
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        expected_resolution="PENDING", scenario_tag="test",
    )


def investigation(status: AgentInvestigationStatus, *, review: bool = False) -> InvestigationAgentResponse:
    return InvestigationAgentResponse(
        ticket_id="TKT-201", issue_type=AgentIssueType.REFUND,
        investigation_status=status, recommendation_type=AgentRecommendationType.HUMAN_REVIEW,
        customer_explanation="Verified facts are available.",
        missing_information=["Eligibility requires review."] if status is not AgentInvestigationStatus.COMPLETE else [],
        recommended_next_steps=["Request human review."], requires_human_review=review,
    )


class Tickets:
    def __init__(self, value: Ticket | None = None) -> None:
        self.value = value or ticket()
        self.calls = 0

    def get_by_id(self, ticket_id: str):
        self.calls += 1
        return self.value if self.value and self.value.ticket_id == ticket_id else None

    def is_owned_by_customer(self, customer_id: str, ticket_id: str) -> bool:
        return bool(self.value and self.value.customer_id == customer_id and self.value.ticket_id == ticket_id)


class Agent:
    def __init__(self, result: InvestigationAgentResponse) -> None:
        self.result = result
        self.calls = 0

    def investigate(self, ticket_id: str, context: CustomerInvestigationContext) -> InvestigationAgentResponse:
        self.calls += 1
        assert context.customer_id == "CUST-001"
        return self.result


class MemoryRegistry:
    def __init__(self) -> None:
        self.entries: dict[str, WorkflowRegistryEntry] = {}

    def create(self, entry: WorkflowRegistryEntry) -> None:
        self.entries[entry.workflow_id] = entry

    def get(self, workflow_id: str):
        return self.entries.get(workflow_id)

    def active_for_ticket(self, ticket_id: str, customer_id: str):
        return next((entry for entry in self.entries.values() if entry.ticket_id == ticket_id and entry.customer_id == customer_id and not entry.review_consumed), None)

    def consume_review(self, workflow_id: str) -> bool:
        entry = self.entries.get(workflow_id)
        if entry is None or entry.review_consumed:
            return False
        self.entries[workflow_id] = WorkflowRegistryEntry(
            entry.workflow_id, entry.thread_id, entry.ticket_id, entry.customer_id, True
        )
        return True


@contextmanager
def memory_checkpointer(_: object):
    yield SAVER


SAVER = InMemorySaver()


def graph_for(result: InvestigationAgentResponse, tickets: Tickets | None = None):
    return build_support_graph(WorkflowDependencies(tickets or Tickets(), Agent(result)), InMemorySaver())


def initial_state() -> dict[str, object]:
    return {"workflow_id": "workflow-1", "ticket_id": "TKT-201", "customer_id": "CUST-001", "workflow_status": "RUNNING", "transition_history": []}


def test_state_is_serializable_and_complete_without_review_prepares_nonapproval_proposal() -> None:
    graph = graph_for(investigation(AgentInvestigationStatus.COMPLETE, review=False))
    result = graph.invoke(initial_state(), config={"configurable": {"thread_id": "workflow-1"}})
    assert result["workflow_status"] == WorkflowStatus.PROPOSAL_READY.value
    assert result["proposed_resolution"]["is_approval"] is False
    assert result["proposed_resolution"]["will_execute"] is False


def test_unauthorized_ticket_stops_before_agent_invocation() -> None:
    tickets = Tickets(ticket("CUST-OTHER"))
    agent = Agent(investigation(AgentInvestigationStatus.COMPLETE))
    graph = build_support_graph(WorkflowDependencies(tickets, agent), InMemorySaver())
    result = graph.invoke(initial_state(), config={"configurable": {"thread_id": "no-access"}})
    assert result["workflow_status"] == WorkflowStatus.NOT_FOUND_OR_NOT_AUTHORIZED.value
    assert agent.calls == 0


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (AgentInvestigationStatus.INSUFFICIENT_EVIDENCE, WorkflowStatus.NEEDS_MORE_INFORMATION),
        (AgentInvestigationStatus.POLICY_REVIEW_REQUIRED, WorkflowStatus.WAITING_HUMAN_REVIEW),
    ],
)
def test_deterministic_investigation_routing(status, expected) -> None:
    graph = graph_for(investigation(status, review=status is AgentInvestigationStatus.POLICY_REVIEW_REQUIRED))
    result = graph.invoke(initial_state(), config={"configurable": {"thread_id": f"route-{status.value}"}})
    assert result["workflow_status"] == expected.value


def test_interrupt_checkpoint_restores_in_new_graph_and_resume_does_not_rerun_agent() -> None:
    saver = InMemorySaver()
    agent = Agent(investigation(AgentInvestigationStatus.COMPLETE, review=True))
    first = build_support_graph(WorkflowDependencies(Tickets(), agent), saver)
    config = {"configurable": {"thread_id": "resumable"}}
    paused = first.invoke(initial_state(), config=config)
    assert "__interrupt__" in paused
    assert agent.calls == 1
    second = build_support_graph(WorkflowDependencies(Tickets(), agent), saver)
    restored = second.get_state(config)
    assert restored.next == ("human_review_interrupt",)
    resumed = second.invoke(Command(resume={"outcome": "ACKNOWLEDGED"}), config=config)
    assert resumed["workflow_status"] == WorkflowStatus.COMPLETED.value
    assert agent.calls == 1


def test_service_status_does_not_invoke_agent_and_resume_is_authorized_and_once() -> None:
    global SAVER
    SAVER = InMemorySaver()
    tickets = Tickets()
    agent = Agent(investigation(AgentInvestigationStatus.COMPLETE, review=True))
    settings = SimpleNamespace(workflow_dev_review_simulation_enabled=True, workflow_recursion_limit=12)
    registry = MemoryRegistry()
    service = SupportWorkflowService(
        tickets, agent, settings=settings, registry=registry, checkpointer_factory=memory_checkpointer
    )
    context = CustomerInvestigationContext("CUST-001")
    started = service.start_workflow("TKT-201", context)
    workflow_id = started["workflow_id"]
    assert agent.calls == 1
    assert service.get_workflow_status(workflow_id, context)["workflow_id"] == workflow_id
    assert agent.calls == 1
    with pytest.raises(WorkflowAccessError):
        service.get_workflow_status(workflow_id, CustomerInvestigationContext("CUST-OTHER"))
    with pytest.raises(WorkflowAccessError):
        service.resume_workflow(workflow_id, TrustedReviewerContext("x", False), SafeReviewInput(outcome=ReviewOutcome.ACKNOWLEDGED))
    completed = service.resume_workflow(workflow_id, TrustedReviewerContext("admin", True), SafeReviewInput(outcome=ReviewOutcome.ACKNOWLEDGED))
    assert completed["workflow_status"] == WorkflowStatus.COMPLETED.value
    assert agent.calls == 1
    with pytest.raises(WorkflowConflictError):
        service.resume_workflow(workflow_id, TrustedReviewerContext("admin", True), SafeReviewInput(outcome=ReviewOutcome.ACKNOWLEDGED))


def test_service_rejects_duplicate_start_and_nonpaused_resume() -> None:
    global SAVER
    SAVER = InMemorySaver()
    service = SupportWorkflowService(
        Tickets(), Agent(investigation(AgentInvestigationStatus.COMPLETE)),
        settings=SimpleNamespace(workflow_dev_review_simulation_enabled=True, workflow_recursion_limit=12),
        registry=MemoryRegistry(), checkpointer_factory=memory_checkpointer,
    )
    context = CustomerInvestigationContext("CUST-001")
    started = service.start_workflow("TKT-201", context)
    with pytest.raises(WorkflowConflictError):
        service.start_workflow("TKT-201", context)
    with pytest.raises(WorkflowConflictError):
        service.resume_workflow(started["workflow_id"], TrustedReviewerContext("admin", True), SafeReviewInput(outcome=ReviewOutcome.ACKNOWLEDGED))
