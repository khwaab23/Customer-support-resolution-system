from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_session import UserSession


class SessionRepository:
    """Persistence operations for server-side sessions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, session_id: UUID) -> UserSession | None:
        return self._session.scalar(
            select(UserSession).where(UserSession.session_id == session_id)
        )

    def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        return self._session.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash)
        )

    def add(self, user_session: UserSession) -> None:
        self._session.add(user_session)

    def revoke(self, user_session: UserSession) -> None:
        if user_session.revoked_at is None:
            user_session.revoked_at = datetime.now(timezone.utc)

    @staticmethod
    def is_expired(user_session: UserSession) -> bool:
        return user_session.expires_at <= datetime.now(timezone.utc)
