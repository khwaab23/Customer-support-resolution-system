from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SqlEnum, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.user_session import UserSession


class UserRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"


class User(Base):
    """Login identity for a customer or administrator."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role = 'CUSTOMER' AND customer_id IS NOT NULL) "
            "OR (role = 'ADMIN' AND customer_id IS NULL)",
            name="users_role_customer_check",
        ),
        UniqueConstraint("customer_id", name="users_customer_id_key"),
        Index("users_email_lower_unique", text("lower(email)"), unique=True),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(
            UserRole,
            name="users_role_check",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
    )
    customer_id: Mapped[str | None] = mapped_column(
        ForeignKey("customers.customer_id", name="users_customer_id_fkey"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    customer: Mapped["Customer | None"] = relationship()
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user")
