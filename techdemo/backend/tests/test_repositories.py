from datetime import date
from unittest.mock import Mock

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.repositories.customer_repository import CustomerRepository
from app.repositories.order_repository import OrderRepository


def render_postgresql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_customer_repository_returns_existing_customer() -> None:
    session = Mock(spec=Session)
    expected = Customer(
        customer_id="cust-1",
        name="First Customer",
        email="first@example.test",
        region="NA",
        currency="USD",
        account_status="active",
    )
    session.scalar.return_value = expected

    customer = CustomerRepository(session).get_by_id("cust-1")

    assert customer is expected
    statement = session.scalar.call_args.args[0]
    assert "WHERE customers.customer_id = 'cust-1'" in render_postgresql(statement)


def test_customer_repository_returns_none_for_missing_customer() -> None:
    session = Mock(spec=Session)
    session.scalar.return_value = None

    customer = CustomerRepository(session).get_by_email("missing@example.test")

    assert customer is None
    statement = session.scalar.call_args.args[0]
    assert "WHERE customers.email = 'missing@example.test'" in render_postgresql(statement)


def test_order_repository_filters_and_sorts_customer_orders() -> None:
    session = Mock(spec=Session)
    session.scalars.return_value = [
        Order(
            order_id="order-003",
            customer_id="cust-1",
            ordered_at=date(2025, 2, 1),
            status="pending",
            currency="USD",
            total_minor=3000,
        ),
        Order(
            order_id="order-001",
            customer_id="cust-1",
            ordered_at=date(2025, 1, 1),
            status="completed",
            currency="USD",
            total_minor=1000,
        ),
        Order(
            order_id="order-002",
            customer_id="cust-1",
            ordered_at=date(2025, 1, 1),
            status="completed",
            currency="USD",
            total_minor=2000,
        ),
    ]

    orders = OrderRepository(session).list_by_customer("cust-1")

    assert [order.order_id for order in orders] == [
        "order-003",
        "order-001",
        "order-002",
    ]
    statement = session.scalars.call_args.args[0]
    query = render_postgresql(statement)
    assert "WHERE orders.customer_id = 'cust-1'" in query
    assert "ORDER BY orders.ordered_at DESC, orders.order_id ASC" in query
    assert "LIMIT 10" in query


def test_order_repository_returns_empty_list_for_missing_customer() -> None:
    session = Mock(spec=Session)
    session.scalars.return_value = []

    repository = OrderRepository(session)

    assert repository.list_by_customer("missing") == []
    assert repository.list_by_customer("cust-1", limit=0) == []
    session.scalars.assert_called_once()


def test_order_repository_returns_order_by_id_or_none() -> None:
    session = Mock(spec=Session)
    expected = Order(
        order_id="order-004",
        customer_id="cust-2",
        ordered_at=date(2025, 3, 1),
        status="completed",
        currency="EUR",
        total_minor=4000,
    )
    session.scalar.side_effect = [expected, None]
    repository = OrderRepository(session)

    assert repository.get_by_id("order-004") is expected
    assert repository.get_by_id("missing") is None
