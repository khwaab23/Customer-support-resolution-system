from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class InvestigationOutcome(str, Enum):
    """Predictable states for a read-only order investigation."""

    COMPLETE = "COMPLETE"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    MISSING_ORDER_LINK = "MISSING_ORDER_LINK"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"


class PolicyTopic(str, Enum):
    """The only deterministic policy subjects a future LLM may request."""

    RETURN = "RETURN"
    REFUND = "REFUND"
    DAMAGED_ITEM = "DAMAGED_ITEM"


class PolicyLookupOutcome(str, Enum):
    """Predictable states for trusted local-policy lookup."""

    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


class MissingData(BaseModel):
    """A verified field that could not be supplied by the current data source."""

    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class InvestigationOrderDetails(BaseModel):
    """Verified order fields available to an investigation."""

    model_config = ConfigDict(from_attributes=True)

    order_id: str
    ordered_at: date
    status: str
    currency: str
    total_minor: int


class InvestigationShipmentDetails(BaseModel):
    """Verified shipment fields mapped directly from the shipments table."""

    model_config = ConfigDict(from_attributes=True)

    shipment_id: str
    order_id: str
    carrier: str
    tracking_number: str
    status: str
    shipped_at: date | None
    delivered_at: date | None
    expected_delivery_at: date
    last_updated_at: date
    service_available: bool


class OrderShipments(BaseModel):
    """All known shipments for one order; an empty list is valid."""

    order_id: str
    shipments: list[InvestigationShipmentDetails]


class InvestigationTicketDetails(BaseModel):
    """Customer-safe ticket facts used to scope a broader investigation."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    order_id: str | None
    category: str
    message: str


class InvestigationPaymentDetails(BaseModel):
    """Customer-safe payment facts; payment identifiers are intentionally omitted."""

    model_config = ConfigDict(from_attributes=True)

    amount_minor: int
    currency: str
    status: str
    captured_at: date
    provider: str


class OrderPayments(BaseModel):
    """All known payments for one order; an empty list is valid."""

    order_id: str
    payments: list[InvestigationPaymentDetails]


class InvestigationOrderItemDetails(BaseModel):
    """The verified order item associated with a return record."""

    model_config = ConfigDict(from_attributes=True)

    order_item_id: str
    product_id: str
    quantity: int
    unit_price_minor: int
    line_total_minor: int


class InvestigationReturnDetails(BaseModel):
    """Customer-safe return and damaged-product facts."""

    model_config = ConfigDict(from_attributes=True)

    return_id: str
    requested_at: date
    received_at: date | None
    inspection_status: str
    status: str
    reason: str
    order_item: InvestigationOrderItemDetails


class OrderReturns(BaseModel):
    """All known returns for one order; an empty list is valid."""

    order_id: str
    returns: list[InvestigationReturnDetails]


class InvestigationRefundDetails(BaseModel):
    """Customer-safe historical refund facts without approval or provider secrets."""

    model_config = ConfigDict(from_attributes=True)

    refund_id: str
    amount_minor: int
    status: str
    created_at: datetime


class OrderRefunds(BaseModel):
    """All known refunds for one order; an empty list is valid."""

    order_id: str
    refunds: list[InvestigationRefundDetails]


class PolicyReference(BaseModel):
    """A verbatim excerpt from one trusted local policy document."""

    topic: PolicyTopic
    source: str
    text: str = Field(min_length=1)


class PolicyLookupResult(BaseModel):
    """Structured documented-policy result, including missing/ambiguous states."""

    topic: PolicyTopic
    outcome: PolicyLookupOutcome
    policies: list[PolicyReference] = Field(default_factory=list)
    missing_data: list[MissingData] = Field(default_factory=list)


class InvestigationReport(BaseModel):
    """Combined, structured result returned by internal investigation tools."""

    outcome: InvestigationOutcome
    ticket_id: str | None = None
    ticket: InvestigationTicketDetails | None = None
    order: InvestigationOrderDetails | None = None
    shipments: OrderShipments | None = None
    payments: OrderPayments | None = None
    returns: OrderReturns | None = None
    refunds: OrderRefunds | None = None
    policies: list[PolicyReference] = Field(default_factory=list)
    missing_data: list[MissingData] = Field(default_factory=list)
