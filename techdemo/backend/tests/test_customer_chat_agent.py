from types import SimpleNamespace
from unittest.mock import Mock

from app.agents.customer_chat_agent import CustomerChatAgent
from app.agents.tool_executor import ToolExecutionResult
from app.schemas.investigation import PolicyTopic
from app.tools.context import CustomerInvestigationContext


def _agent(executor: Mock) -> CustomerChatAgent:
    # The failed client proves deterministic safety fallback works without a
    # live OpenAI call in unit tests.
    client = SimpleNamespace(responses=SimpleNamespace(create=Mock(side_effect=RuntimeError("offline"))))
    settings = SimpleNamespace(openai_agent_model="test", agent_request_timeout_seconds=1)
    return CustomerChatAgent(executor, client=client, settings=settings)


def test_chat_asks_for_owned_order_before_running_order_tools() -> None:
    executor = Mock()
    result = _agent(executor).respond("Where is my package?", selected_order_id=None, history=[], context=CustomerInvestigationContext("CUST-1"))
    assert result.metadata["needs_order_selection"] is True
    executor.execute.assert_not_called()


def test_refund_chat_runs_only_allowlisted_tools_with_selected_order() -> None:
    executor = Mock()
    executor.execute.return_value = ToolExecutionResult(tool_name="get_order_details", ok=True, result={"order": {"order_id": "ORD-1", "status": "DELIVERED"}})
    result = _agent(executor).respond("Where is my refund?", selected_order_id="ORD-1", history=[], context=CustomerInvestigationContext("CUST-1"))
    names = [call.args[0] for call in executor.execute.call_args_list]
    arguments = [call.args[1] for call in executor.execute.call_args_list]
    assert names == ["get_order_details", "get_return_history", "get_refund_history", "lookup_policy"]
    assert all(value.get("order_id") == "ORD-1" for value in arguments if "order_id" in value)
    assert "cannot determine or promise a refund" in result.message_text


def test_escalation_requires_customer_confirmation_not_model_authority() -> None:
    executor = Mock()
    executor.execute.return_value = ToolExecutionResult(tool_name="get_order_details", ok=True, result={"order": {"order_id": "ORD-1", "status": "DELIVERED"}})
    result = _agent(executor).respond("Please escalate me to a human", selected_order_id="ORD-1", history=[], context=CustomerInvestigationContext("CUST-1"))
    assert result.requires_escalation_confirmation is True
