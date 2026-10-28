"""Development-only CLI for safely starting, inspecting, and resuming workflows."""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.ticket import Ticket
from app.models.user import User, UserRole
from app.tools.context import CustomerInvestigationContext
from app.workflows.factory import build_support_workflow_service
from app.workflows.registry import PostgresWorkflowRegistry
from app.workflows.checkpoint import checkpoint_conninfo
from app.workflows.state import ReviewOutcome, SafeReviewInput
from app.services.support_workflow_service import TrustedReviewerContext


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Verify the durable support workflow safely.")
    commands = result.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Start a workflow; invokes the configured AI agent.")
    start.add_argument("--ticket-id", default="TKT-201")
    inspect = commands.add_parser("inspect", help="Inspect a checkpoint without invoking the AI agent.")
    inspect.add_argument("--workflow-id", required=True)
    resume = commands.add_parser("resume", help="Development-only simulated review resume.")
    resume.add_argument("--workflow-id", required=True)
    resume.add_argument("--outcome", choices=[item.value for item in ReviewOutcome], required=True)
    return result


def print_state(state: dict[str, object]) -> None:
    print(f"Workflow ID: {state.get('workflow_id')}")
    print(f"Ticket ID: {state.get('ticket_id')}")
    print(f"Thread ID: support-workflow:{state.get('workflow_id')}")
    print(f"Workflow status: {state.get('workflow_status')}")
    print(f"Investigation status: {state.get('investigation_status')}")
    print(f"Transitions: {', '.join(state.get('transition_history', [])) or 'none'}")
    print(f"Paused for human review: {state.get('workflow_status') == 'WAITING_HUMAN_REVIEW'}")
    for fact in (state.get("proposed_resolution") or {}).get("verified_facts", []):
        print(f"  Fact: {fact.get('tool_name')}{fact.get('json_pointer')}: {fact.get('value')}")
    for citation in (state.get("proposed_resolution") or {}).get("policy_citations", []):
        print(f"  Policy: {citation.get('policy_id')} v{citation.get('policy_version')}")
    proposal = state.get("proposed_resolution")
    if proposal:
        print(f"Proposed resolution: {proposal.get('suggested_next_action')}")


def main() -> int:
    args = parser().parse_args()
    settings = get_settings()
    if settings.app_environment != "development":
        print("FAIL: this script is development-only.", file=sys.stderr)
        return 1
    registry = PostgresWorkflowRegistry(checkpoint_conninfo(settings))
    try:
        with get_session_factory()() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            if args.command == "start":
                ticket = session.get(Ticket, args.ticket_id)
                if ticket is None:
                    print("FAIL: ticket not found.", file=sys.stderr)
                    return 1
                service = build_support_workflow_service(session, settings=settings)
                state = service.start_workflow(
                    ticket.ticket_id,
                    CustomerInvestigationContext(customer_id=ticket.customer_id),
                )
            else:
                entry = registry.get(args.workflow_id)
                if entry is None:
                    print("FAIL: workflow not found.", file=sys.stderr)
                    return 1
                ticket = session.get(Ticket, entry.ticket_id)
                if ticket is None or ticket.customer_id != entry.customer_id:
                    print("FAIL: workflow ticket is unavailable.", file=sys.stderr)
                    return 1
                service = build_support_workflow_service(session, settings=settings)
                context = CustomerInvestigationContext(customer_id=ticket.customer_id)
                if args.command == "inspect":
                    state = service.get_workflow_status(entry.workflow_id, context)
                else:
                    if not settings.workflow_dev_review_simulation_enabled:
                        print("FAIL: development review simulation is disabled.", file=sys.stderr)
                        return 1
                    admin = session.scalar(select(User).where(User.role == UserRole.ADMIN).limit(1))
                    if admin is None:
                        print("FAIL: no trusted development admin exists.", file=sys.stderr)
                        return 1
                    state = service.resume_workflow(
                        entry.workflow_id,
                        TrustedReviewerContext(user_id=str(admin.user_id), is_admin=True),
                        SafeReviewInput(outcome=ReviewOutcome(args.outcome)),
                    )
    except SQLAlchemyError:
        print("FAIL: database configuration or connectivity is unavailable.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
