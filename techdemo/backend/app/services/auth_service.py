from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User, UserRole
from app.models.user_session import UserSession
from app.repositories.customer_repository import CustomerRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository


class InvalidCredentialsError(Exception):
    """Raised when authentication must fail without revealing the reason."""


class InvalidSessionError(Exception):
    """Raised when a session cannot authenticate a request."""


@dataclass(frozen=True)
class AuthContext:
    user: User
    user_session: UserSession


password_hasher = PasswordHasher(type=Type.ID)


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """Authentication policy and session lifecycle operations."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._sessions = SessionRepository(session)
        self._customers = CustomerRepository(session)

    @staticmethod
    def hash_password(password: str) -> str:
        return password_hasher.hash(password)

    def authenticate(self, email: str, password: str) -> User:
        user = self._users.get_by_email(email)
        if user is None or not self._is_user_active(user):
            raise InvalidCredentialsError()

        try:
            password_matches = password_hasher.verify(user.password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            raise InvalidCredentialsError() from None

        if not password_matches:
            raise InvalidCredentialsError()

        if password_hasher.check_needs_rehash(user.password_hash):
            user.password_hash = self.hash_password(password)

        return user

    def create_session(self, user: User) -> tuple[UserSession, str]:
        raw_token = token_urlsafe(32)
        now = datetime.now(timezone.utc)
        user_session = UserSession(
            user_id=user.user_id,
            token_hash=hash_session_token(raw_token),
            expires_at=now + timedelta(minutes=get_settings().session_ttl_minutes),
        )
        self._sessions.add(user_session)
        self._session.commit()
        self._session.refresh(user_session)
        return user_session, raw_token

    def get_auth_context(self, raw_token: str) -> AuthContext:
        user_session = self._sessions.get_by_token_hash(hash_session_token(raw_token))
        if (
            user_session is None
            or user_session.revoked_at is not None
            or self._sessions.is_expired(user_session)
            or not self._is_user_active(user_session.user)
        ):
            raise InvalidSessionError()

        return AuthContext(user=user_session.user, user_session=user_session)

    def logout(self, user_session: UserSession) -> None:
        self._sessions.revoke(user_session)
        self._session.commit()

    def _is_user_active(self, user: User) -> bool:
        if not user.is_active:
            return False
        if user.role == UserRole.ADMIN:
            return user.customer_id is None
        if user.role != UserRole.CUSTOMER or user.customer_id is None:
            return False

        customer = self._customers.get_by_id(user.customer_id)
        return customer is not None and customer.account_status.casefold() == "active"
