"""LangGraph composition for the bounded customer support workflow."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.workflows.nodes import (
    WorkflowDependencies,
    evaluate_investigation_node,
    human_review_interrupt_node,
    prepare_missing_information_node,
    prepare_proposal_node,
    run_investigation_node,
    validate_ticket_node,
)
from app.workflows.state import SupportWorkflowState, WorkflowStatus


def _after_validation(state: SupportWorkflowState) -> str:
    return "end" if state["workflow_status"] == WorkflowStatus.NOT_FOUND_OR_NOT_AUTHORIZED.value else "investigate"


def _after_evaluation(state: SupportWorkflowState) -> str:
    status = state["workflow_status"]
    if status == WorkflowStatus.NEEDS_MORE_INFORMATION.value:
        return "missing"
    return "proposal"


def _after_proposal(state: SupportWorkflowState) -> str:
    return "review" if state.get("requires_human_review") else "end"


def build_support_graph(deps: WorkflowDependencies, checkpointer: object):
    graph = StateGraph(SupportWorkflowState)
    graph.add_node("validate_ticket", validate_ticket_node(deps))
    graph.add_node("run_investigation", run_investigation_node(deps))
    graph.add_node("evaluate_investigation", evaluate_investigation_node)
    graph.add_node("prepare_proposal", prepare_proposal_node)
    graph.add_node("prepare_missing_information", prepare_missing_information_node)
    graph.add_node("human_review_interrupt", human_review_interrupt_node)
    graph.add_edge(START, "validate_ticket")
    graph.add_conditional_edges("validate_ticket", _after_validation, {"investigate": "run_investigation", "end": END})
    graph.add_edge("run_investigation", "evaluate_investigation")
    graph.add_conditional_edges("evaluate_investigation", _after_evaluation, {"proposal": "prepare_proposal", "missing": "prepare_missing_information"})
    graph.add_conditional_edges("prepare_proposal", _after_proposal, {"review": "human_review_interrupt", "end": END})
    graph.add_edge("prepare_missing_information", END)
    graph.add_edge("human_review_interrupt", END)
    return graph.compile(checkpointer=checkpointer)
