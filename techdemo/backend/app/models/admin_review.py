from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminReview(Base):
    """Durable human-review decision record; it is not a payment or refund."""
    __tablename__ = "admin_reviews"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('PENDING', 'INFORMATION_REQUESTED', 'APPROVED_INTERNAL', 'REJECTED')",
            name="admin_reviews_status_check",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('APPROVE', 'REJECT', 'REQUEST_MORE_INFORMATION')",
            name="admin_reviews_decision_check",
        ),
        CheckConstraint("version > 0", name="admin_reviews_version_check"),
    )
    review_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id"), nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False)
    eligibility_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_state: Mapped[str] = mapped_column(String(40), nullable=False, server_default="PENDING")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=lambda: datetime.now().astimezone())
