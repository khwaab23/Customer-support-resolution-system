"""Strict OpenAI function definitions for the read-only investigation surface."""

from app.schemas.investigation import PolicyTopic


def _order_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"order_id": {"type": "string", "minLength": 1, "maxLength": 30}},
        "required": ["order_id"],
        "additionalProperties": False,
    }


MODEL_TOOLS: tuple[dict[str, object], ...] = (
    {
        "type": "function",
        "name": "get_order_details",
        "description": "Get verified details for a customer-owned order.",
        "parameters": _order_schema(),
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_shipment_status",
        "description": "Get verified shipment status records for a customer-owned order.",
        "parameters": _order_schema(),
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_payment_history",
        "description": "Get customer-safe payment history for a customer-owned order.",
        "parameters": _order_schema(),
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_return_history",
        "description": "Get verified returns and associated order items for a customer-owned order.",
        "parameters": _order_schema(),
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_refund_history",
        "description": "Get historical refunds only; it cannot approve or execute refunds.",
        "parameters": _order_schema(),
        "strict": True,
    },
    {
        "type": "function",
        "name": "lookup_policy",
        "description": "Retrieve source-backed policy evidence for one permitted topic.",
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string", "enum": [topic.value for topic in PolicyTopic]}},
            "required": ["topic"],
            "additionalProperties": False,
        },
        "strict": True,
    },
)

TOOL_NAMES = frozenset(tool["name"] for tool in MODEL_TOOLS)
