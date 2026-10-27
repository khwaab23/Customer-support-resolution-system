"""Trusted dispatch from model tool calls to allowlisted read-only operations."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.tool_definitions import TOOL_NAMES
from app.schemas.investigation import PolicyTopic
from app.tools.context import CustomerInvestigationContext
from app.tools.order_tools import OrderInvestigationTool
from app.tools.payment_tools import PaymentInvestigationTool
from app.tools.policy_tools import PolicyLookupTool
from app.tools.refund_tools import RefundHistoryInvestigationTool
from app.tools.return_tools import ReturnInvestigationTool
from app.tools.shipment_tools import ShipmentInvestigationTool


class _OrderArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1, max_length=30)


class _PolicyArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: PolicyTopic


class ToolExecutionError(BaseModel):
    code: str
    message: str


class ToolExecutionResult(BaseModel):
    """Bounded JSON-safe output sent back through the Responses API."""

    tool_name: str
    ok: bool
    result: dict[str, Any] | None = None
    error: ToolExecutionError | None = None

    def as_json(self) -> str:
        return self.model_dump_json(exclude_none=True)


class ToolExecutor:
    """Execute only fixed customer-scoped read tools with trusted identity."""

    def __init__(
        self,
        order_tool: OrderInvestigationTool,
        shipment_tool: ShipmentInvestigationTool,
        payment_tool: PaymentInvestigationTool,
        return_tool: ReturnInvestigationTool,
        refund_tool: RefundHistoryInvestigationTool,
        policy_tool: PolicyLookupTool,
        *,
        max_output_chars: int = 12_000,
    ) -> None:
        self._order_tool = order_tool
        self._shipment_tool = shipment_tool
        self._payment_tool = payment_tool
        self._return_tool = return_tool
        self._refund_tool = refund_tool
        self._policy_tool = policy_tool
        self._max_output_chars = max_output_chars

    def execute(
        self,
        tool_name: str,
        raw_arguments: str | dict[str, object],
        context: CustomerInvestigationContext,
    ) -> ToolExecutionResult:
        """Validate and execute one allowlisted call without exposing identity control."""
        if tool_name not in TOOL_NAMES:
            return self._error(tool_name, "UNKNOWN_TOOL", "This tool is not available.")
        try:
            arguments = self._parse_arguments(raw_arguments)
            if tool_name == "lookup_policy":
                parsed = _PolicyArguments.model_validate(arguments)
                result = self._policy_tool.lookup(parsed.topic, context)
            else:
                parsed = _OrderArguments.model_validate(arguments)
                result = {
                    "get_order_details": self._order_tool.get_order_details,
                    "get_shipment_status": self._shipment_tool.get_shipment_status,
                    "get_payment_history": self._payment_tool.get_payment_history,
                    "get_return_history": self._return_tool.get_return_history,
                    "get_refund_history": self._refund_tool.get_refund_history,
                }[tool_name](parsed.order_id, context)
            payload = result.model_dump(mode="json")
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            return self._error(tool_name, "INVALID_ARGUMENTS", "Tool arguments are invalid.")
        except Exception:
            # Do not disclose database, embedding, or implementation detail to the model.
            return self._error(tool_name, "TOOL_UNAVAILABLE", "The requested evidence is unavailable.")

        execution = ToolExecutionResult(tool_name=tool_name, ok=True, result=payload)
        if len(execution.as_json()) > self._max_output_chars:
            return self._error(
                tool_name,
                "TOOL_OUTPUT_TOO_LARGE",
                "The requested evidence exceeds the safe tool-output limit.",
            )
        return execution

    @staticmethod
    def _parse_arguments(raw_arguments: str | dict[str, object]) -> dict[str, object]:
        if isinstance(raw_arguments, str):
            parsed = json.loads(raw_arguments)
        else:
            parsed = raw_arguments
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object.")
        return parsed

    @staticmethod
    def _error(tool_name: str, code: str, message: str) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name,
            ok=False,
            error=ToolExecutionError(code=code, message=message),
        )
