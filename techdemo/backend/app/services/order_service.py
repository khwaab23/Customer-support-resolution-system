from app.models.order import Order
from app.repositories.order_repository import OrderRepository


class OrderService:
    """Customer-owned order retrieval policy."""

    def __init__(self, order_repository: OrderRepository) -> None:
        self._order_repository = order_repository

    def list_customer_orders(self, customer_id: str, limit: int = 10) -> list[Order]:
        return self._order_repository.list_by_customer(customer_id, limit)

    def get_customer_order(self, customer_id: str, order_id: str) -> Order | None:
        order = self._order_repository.get_by_id(order_id)
        if order is None or order.customer_id != customer_id:
            return None
        return order
