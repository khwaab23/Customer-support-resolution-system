"""Authorization-aware service facade for durable support workflows."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from langgraph.types import Command

from app.agents.investigation_agent import InvestigationAgent
from app.core.config import Settings, get_settings
from app.repositories.ticket_repository import TicketRepository
from app.tools.context import CustomerInvestigationContext
from app.workflows.checkpoint import checkpoint_conninfo, postgres_checkpointer
from app.workflows.nodes import WorkflowDependencies
from app.workflows.registry import (
    PostgresWorkflowRegistry,
    WorkflowRegistry,
    WorkflowRegistryEntry,
)
from app.workflows.state import SafeReviewInput, SupportWorkflowState, WorkflowStatus, now_iso
from app.workflows.support_graph import build_support_graph


class WorkflowAccessError(ValueError):
    """Workflow ID is unknown or does not belong to the trusted caller."""


class WorkflowConflictError(ValueError):
    """The operation is not valid for the workflow's current checkpoint."""


@dataclass(frozen=True, slots=True)
class TrustedReviewerContext:
    """Trusted server-side admin identity; never created from CLI/user text."""

    user_id: str
    is_admin: bool


class SupportWorkflowService:
    """Starts, inspects, and safely resumes graph executions without HTTP routes."""

    def __init__(
        self,
        ticket_repository: TicketRepository,
        investigation_agent: InvestigationAgent,
        *,
        settings: Settings | None = None,
        registry: WorkflowRegistry | None = None,
        checkpointer_factory=postgres_checkpointer,
    ) -> None:
        self._tickets = ticket_repository
        self._agent = investigation_agent
        self._settings = settings or get_settings()
        self._registry = registry or PostgresWorkflowRegistry(checkpoint_conninfo(self._settings))
        self._checkpointer_factory = checkpointer_factory

    def start_workflow(
        self,
        ticket_id: str,
        context: CustomerInvestigationContext,
    ) -> SupportWorkflowState:
        ticket = self._tickets.get_by_id(ticket_id)
        if ticket is None or ticket.customer_id != context.customer_id:
            raise WorkflowAccessError("Ticket not found.")
        if self._registry.active_for_ticket(ticket_id, context.customer_id) is not None:
            raise WorkflowConflictError("An existing workflow already covers this ticket.")
        workflow_id = str(uuid4())
        thread_id = f"support-workflow:{workflow_id}"
        entry = WorkflowRegistryEntry(workflow_id, thread_id, ticket_id, context.customer_id)
        self._registry.create(entry)
        initial: SupportWorkflowState = {
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "customer_id": context.customer_id,
            "workflow_status": WorkflowStatus.RUNNING.value,
            "current_step": "start",
            "requires_human_review": False,
            "missing_information": [],
            "error_code": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "transition_history": ["start"],
        }
        return self._invoke(entry, initial)

    def get_workflow_status(
        self,
        workflow_id: str,
        context: CustomerInvestigationContext,
    ) -> SupportWorkflowState:
        entry = self._customer_entry(workflow_id, context)
        with self._checkpointer_factory(self._settings) as checkpointer:
            graph = build_support_graph(self._dependencies(), checkpointer)
            snapshot = graph.get_state(self._config(entry))
        if not snapshot.values:
            raise WorkflowConflictError("Workflow has no checkpoint.")
        return dict(snapshot.values)

    def resume_workflow(
        self,
        workflow_id: str,
        reviewer: TrustedReviewerContext,
        review_input: SafeReviewInput,
    ) -> SupportWorkflowState:
        if not reviewer.is_admin:
            raise WorkflowAccessError("Administrator authority is required.")
        entry = self._registry.get(workflow_id)
        if entry is None:
            raise WorkflowAccessError("Workflow not found.")
        if not self._settings.workflow_dev_review_simulation_enabled:
            raise WorkflowConflictError("Development review simulation is disabled.")
        with self._checkpointer_factory(self._settings) as checkpointer:
            graph = build_support_graph(self._dependencies(), checkpointer)
            snapshot = graph.get_state(self._config(entry))
            if not snapshot.next or "human_review_interrupt" not in snapshot.next:
                raise WorkflowConflictError("Workflow is not waiting for human review.")
            # A conditional registry update prevents two reviewers from resuming
            # the same interrupt. Nodes before interrupt have no side effects.
            if not self._registry.consume_review(workflow_id):
                raise WorkflowConflictError("This workflow review was already consumed.")
            result = graph.invoke(
                Command(resume=review_input.model_dump(mode="json")),
                config=self._config(entry),
            )
        return dict(result)

    def get_workflow_entry(self, workflow_id: str) -> WorkflowRegistryEntry | None:
        """Routing lookup for trusted services; it is never caller authentication."""
        return self._registry.get(workflow_id)

    def is_waiting_for_human_review(self, workflow_id: str) -> bool:
        entry = self._registry.get(workflow_id)
        if entry is None:
            return False
        with self._checkpointer_factory(self._settings) as checkpointer:
            graph = build_support_graph(self._dependencies(), checkpointer)
            snapshot = graph.get_state(self._config(entry))
        return bool(snapshot.next and "human_review_interrupt" in snapshot.next)

    def get_workflow_status_for_admin(self, workflow_id: str) -> SupportWorkflowState | None:
        """Inspection used after role validation by the admin API."""
        entry = self._registry.get(workflow_id)
        if entry is None:
            return None
        with self._checkpointer_factory(self._settings) as checkpointer:
            graph = build_support_graph(self._dependencies(), checkpointer)
            snapshot = graph.get_state(self._config(entry))
        return dict(snapshot.values) if snapshot.values else None

    def resume_admin_decision(
        self,
        workflow_id: str,
        reviewer: TrustedReviewerContext,
        decision: str,
    ) -> SupportWorkflowState:
        """Resume exactly the paused review node using a durable admin decision.

        This intentionally does not use the development simulation switch or
        registry consume flag. The durable review record serializes production
        retries and retains a recoverable resume state if checkpoint I/O fails.
        """
        if not reviewer.is_admin:
            raise WorkflowAccessError("Administrator authority is required.")
        if decision not in {"APPROVE", "REJECT", "REQUEST_MORE_INFORMATION"}:
            raise WorkflowConflictError("Invalid review decision.")
        entry = self._registry.get(workflow_id)
        if entry is None:
            raise WorkflowAccessError("Workflow not found.")
        with self._checkpointer_factory(self._settings) as checkpointer:
            graph = build_support_graph(self._dependencies(), checkpointer)
            snapshot = graph.get_state(self._config(entry))
            if not snapshot.next or "human_review_interrupt" not in snapshot.next:
                raise WorkflowConflictError("Workflow is not waiting for human review.")
            result = graph.invoke(Command(resume={"decision": decision}), config=self._config(entry))
        return dict(result)

    def _invoke(self, entry: WorkflowRegistryEntry, state: SupportWorkflowState) -> SupportWorkflowState:
        with self._checkpointer_factory(self._settings) as checkpointer:
            graph = build_support_graph(self._dependencies(), checkpointer)
            result = graph.invoke(
                state,
                config={**self._config(entry), "recursion_limit": self._settings.workflow_recursion_limit},
            )
        return dict(result)

    def _customer_entry(
        self,
        workflow_id: str,
        context: CustomerInvestigationContext,
    ) -> WorkflowRegistryEntry:
        entry = self._registry.get(workflow_id)
        if entry is None or entry.customer_id != context.customer_id:
            raise WorkflowAccessError("Workflow not found.")
        # Freshly check business ownership; registry and checkpoint identity are
        # routing data only, never evidence that a caller is authenticated.
        if not self._tickets.is_owned_by_customer(context.customer_id, entry.ticket_id):
            raise WorkflowAccessError("Workflow not found.")
        return entry

    def _dependencies(self) -> WorkflowDependencies:
        return WorkflowDependencies(self._tickets, self._agent)

    @staticmethod
    def _config(entry: WorkflowRegistryEntry) -> dict[str, object]:
        return {"configurable": {"thread_id": entry.thread_id}}
