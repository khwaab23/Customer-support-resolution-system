"""Bounded customer chat orchestration separate from ticket investigations.

The agent receives only trusted customer context.  It can read evidence through
the established allowlisted executor; it cannot create tickets, change orders,
approve refunds, or control identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.tool_executor import ToolExecutionResult, ToolExecutor
from app.core.config import Settings, get_settings
from app.tools.context import CustomerInvestigationContext
from app.schemas.investigation import PolicyTopic


@dataclass(frozen=True, slots=True)
class CustomerChatResult:
    message_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_escalation_confirmation: bool = False


class _ChatIntent(BaseModel):
    """Model output is limited to routing, never facts or an action decision."""
    model_config = ConfigDict(extra="forbid")
    needs_order: bool
    policy_topic: PolicyTopic | None = None
    wants_human_help: bool = False


class CustomerChatAgent:
    """Produce grounded chat replies from a deliberately small evidence surface."""

    def __init__(self, executor: ToolExecutor, *, max_history_messages: int = 16, settings: Settings | None = None, client: object | None = None) -> None:
        self._executor = executor
        self._max_history_messages = max_history_messages
        self._settings, self._client = settings or get_settings(), client

    def respond(
        self,
        message: str,
        *,
        selected_order_id: str | None,
        history: list[dict[str, str]],
        context: CustomerInvestigationContext,
    ) -> CustomerChatResult:
        # History is intentionally bounded by the caller and only used for the
        # immediately preceding confirmation, never as authority or evidence.
        del history[self._max_history_messages :]
        lowered = message.lower()
        intent = self._model_intent(message, selected_order_id, history)
        topic = intent.policy_topic if intent else self._topic(lowered)
        needs_order = intent.needs_order if intent else topic is not None or any(word in lowered for word in ("order", "package", "delivery", "where is"))
        if needs_order and selected_order_id is None:
            return CustomerChatResult(
                "I can help with that. Please select one of your orders so I can check the right records.",
                {"needs_order_selection": True, "verified_facts": [], "policy_citations": []},
            )
        if selected_order_id is None:
            return CustomerChatResult(
                "I can answer general support questions. For order, delivery, return, payment, or refund details, please select an order first.",
                {"needs_order_selection": False, "verified_facts": [], "policy_citations": []},
            )

        tools = self._tools_for(lowered, topic, selected_order_id)
        executions = [self._executor.execute(name, arguments, context) for name, arguments in tools]
        successful = [execution for execution in executions if execution.ok]
        if not successful:
            return CustomerChatResult(
                "I could not verify the requested order information right now. Please try again later or ask to create a support case.",
                {"needs_order_selection": False, "verified_facts": [], "policy_citations": [], "missing_information": ["Verified order evidence is temporarily unavailable."]},
            )
        facts = self._facts(successful)
        citations = self._citations(successful)
        wants_human = intent.wants_human_help if intent else self._asks_for_human(lowered)
        explanation = self._explanation(lowered, facts, citations)
        if wants_human:
            explanation += " Would you like me to create a support case for human review?"
        return CustomerChatResult(
            explanation,
            {
                "needs_order_selection": False,
                "verified_facts": facts,
                "policy_citations": citations,
                "missing_information": self._missing(successful),
                "tools_executed": [execution.tool_name for execution in successful],
            },
            requires_escalation_confirmation=wants_human,
        )

    def _model_intent(self, message: str, selected_order_id: str | None, history: list[dict[str, str]]) -> _ChatIntent | None:
        """Use the Responses API for bounded intent routing, with safe fallback.

        This request includes no authentication/session data and the output
        cannot create a ticket, choose a customer, or state transaction facts.
        """
        try:
            response = self._get_client().responses.create(
                model=self._settings.openai_agent_model,
                instructions=("Classify customer support intent only. Do not answer, invent facts, "
                              "make eligibility decisions, or request tools. Return JSON matching the schema."),
                input=json.dumps({
                    "message": message,
                    "selected_order_present": selected_order_id is not None,
                    # Continuity is bounded and contains only previously
                    # persisted customer/assistant text, never session data,
                    # tool payloads, or hidden instructions.
                    "recent_messages": [
                        {"role": item.get("role"), "content": str(item.get("content", ""))[:1_000]}
                        for item in history[-self._max_history_messages:]
                    ],
                }),
                text={"format": {"type": "json_schema", "name": "customer_chat_intent", "strict": True, "schema": _ChatIntent.model_json_schema()}},
                max_output_tokens=120,
                timeout=self._settings.agent_request_timeout_seconds,
            )
            return _ChatIntent.model_validate(json.loads(str(getattr(response, "output_text", ""))))
        except (Exception, ValidationError, ValueError, json.JSONDecodeError):
            return None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    @staticmethod
    def _topic(lowered: str) -> PolicyTopic | None:
        if "refund" in lowered:
            return PolicyTopic.REFUND
        if "return" in lowered:
            return PolicyTopic.RETURN
        if "damag" in lowered or "broken" in lowered:
            return PolicyTopic.DAMAGED_ITEM
        return None

    @staticmethod
    def _tools_for(lowered: str, topic: PolicyTopic | None, order_id: str) -> list[tuple[str, dict[str, str]]]:
        # The executor validates the actual order ID and customer ownership.
        result: list[tuple[str, dict[str, str]]] = [("get_order_details", {"order_id": order_id})]
        if topic is None and any(word in lowered for word in ("ship", "delivery", "package", "where is")):
            result.append(("get_shipment_status", {"order_id": order_id}))
        if topic is PolicyTopic.REFUND:
            result.extend([("get_return_history", {"order_id": order_id}), ("get_refund_history", {"order_id": order_id}), ("lookup_policy", {"topic": topic.value})])
        elif topic is PolicyTopic.RETURN:
            result.extend([("get_return_history", {"order_id": order_id}), ("lookup_policy", {"topic": topic.value})])
        elif topic is PolicyTopic.DAMAGED_ITEM:
            result.append(("lookup_policy", {"topic": topic.value}))
        return result

    def _facts(self, executions: list[ToolExecutionResult]) -> list[str]:
        facts: list[str] = []
        for execution in executions:
            payload = execution.result or {}
            order = payload.get("order")
            if isinstance(order, dict):
                facts.append(f"Order {order.get('order_id', 'selected')} status: {order.get('status', 'unknown')}.")
            shipments = payload.get("shipments")
            if isinstance(shipments, dict):
                values = shipments.get("shipments", [])
                if isinstance(values, list) and values:
                    facts.extend(f"Shipment status: {item.get('status', 'unknown')}." for item in values[:3] if isinstance(item, dict))
            returns = payload.get("returns")
            if isinstance(returns, dict):
                values = returns.get("returns", [])
                if isinstance(values, list):
                    facts.extend(f"Return status: {item.get('status', 'unknown')}." for item in values[:3] if isinstance(item, dict))
            refunds = payload.get("refunds")
            if isinstance(refunds, dict):
                values = refunds.get("refunds", [])
                facts.append("No refund records were found." if values == [] else f"Refund records found: {len(values) if isinstance(values, list) else 'unknown'}.")
        return list(dict.fromkeys(facts))[:8]

    @staticmethod
    def _citations(executions: list[ToolExecutionResult]) -> list[dict[str, str | None]]:
        citations: list[dict[str, str | None]] = []
        for execution in executions:
            payload = execution.result or {}
            for item in payload.get("policies", []) if isinstance(payload.get("policies"), list) else []:
                if isinstance(item, dict) and item.get("policy_id"):
                    citations.append({key: item.get(key) for key in ("policy_id", "policy_version", "source", "section_heading", "effective_date")})
        return citations[:6]

    @staticmethod
    def _missing(executions: list[ToolExecutionResult]) -> list[str]:
        missing: list[str] = []
        for execution in executions:
            for item in (execution.result or {}).get("missing_data", []):
                if isinstance(item, dict) and isinstance(item.get("reason"), str):
                    missing.append(item["reason"])
        return list(dict.fromkeys(missing))[:6]

    @staticmethod
    def _explanation(lowered: str, facts: list[str], citations: list[dict[str, str | None]]) -> str:
        facts_text = " ".join(facts) if facts else "I found limited verified information for the selected order."
        if "refund" in lowered:
            suffix = " I can explain the available policy evidence, but I cannot determine or promise a refund outcome here."
        elif "return" in lowered or "damag" in lowered:
            suffix = " Any policy-dependent outcome still needs the applicable evidence and, where required, human review."
        else:
            suffix = ""
        if citations:
            suffix += " I found relevant policy evidence for this question."
        return facts_text + suffix + " If you need a person to take action, tell me and I can ask for confirmation to open a support case."

    @staticmethod
    def _asks_for_human(lowered: str) -> bool:
        return any(phrase in lowered for phrase in ("human", "representative", "support case", "open a ticket", "escalate"))
