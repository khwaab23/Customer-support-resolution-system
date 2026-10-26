from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.customer import Customer
from app.repositories.order_repository import OrderRepository


def main() -> None:
    """Read one customer and their orders to verify the ORM mappings."""
    with get_session_factory()() as session:
        customer = session.scalar(
            select(Customer).order_by(Customer.customer_id.asc()).limit(1)
        )

        if customer is None:
            print("No customer records found.")
            return

        orders = OrderRepository(session).list_by_customer(customer.customer_id, limit=5)

        print(f"Customer ID: {customer.customer_id}")
        print(f"Orders returned by repository: {len(orders)}")
        for order in orders:
            print(
                f"- {order.order_id}: {order.status}, "
                f"{order.currency} {order.total_minor} minor units, "
                f"ordered {order.ordered_at.isoformat()}"
            )
        print(f"Orders available through relationship: {len(customer.orders)}")


if __name__ == "__main__":
    main()
