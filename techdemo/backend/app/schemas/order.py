from datetime import date

from pydantic import BaseModel, ConfigDict


class CustomerOrderResponse(BaseModel):
    """Safe order fields visible to the authenticated customer."""

    model_config = ConfigDict(from_attributes=True)

    order_id: str
    ordered_at: date
    status: str
    currency: str
    total_minor: int


class CustomerOrderListResponse(BaseModel):
    orders: list[CustomerOrderResponse]
