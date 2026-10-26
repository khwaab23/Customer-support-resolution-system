from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """Persistence operations for login identities."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: UUID) -> User | None:
        return self._session.scalar(select(User).where(User.user_id == user_id))

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(func.lower(User.email) == email.strip().lower())
        return self._session.scalar(statement)

    def get_by_customer_id(self, customer_id: str) -> User | None:
        return self._session.scalar(
            select(User).where(User.customer_id == customer_id)
        )

    def add(self, user: User) -> None:
        self._session.add(user)
