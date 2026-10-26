from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer


class CustomerRepository:
    """Read-only customer queries backed by a caller-provided session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, customer_id: str) -> Customer | None:
        statement = select(Customer).where(Customer.customer_id == customer_id)
        return self._session.scalar(statement)

    def get_by_email(self, email: str) -> Customer | None:
        statement = select(Customer).where(Customer.email == email)
        return self._session.scalar(statement)
