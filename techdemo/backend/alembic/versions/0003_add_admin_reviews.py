"""Add durable human review records without altering business refunds.

Revision ID: 0003_add_admin_reviews
Revises: 0002_add_auth_tables
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_add_admin_reviews"
down_revision = "0002_add_auth_tables"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "admin_reviews",
        sa.Column("review_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", sa.String(80), nullable=False, unique=True),
        sa.Column("ticket_id", sa.String(30), sa.ForeignKey("tickets.ticket_id"), nullable=False),
        sa.Column("order_id", sa.String(30), nullable=True),
        sa.Column("review_status", sa.String(40), nullable=False),
        sa.Column("eligibility_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("decision", sa.String(40), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_state", sa.String(40), nullable=False, server_default="PENDING"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("review_status IN ('PENDING', 'INFORMATION_REQUESTED', 'APPROVED_INTERNAL', 'REJECTED')", name="admin_reviews_status_check"),
        sa.CheckConstraint("decision IS NULL OR decision IN ('APPROVE', 'REJECT', 'REQUEST_MORE_INFORMATION')", name="admin_reviews_decision_check"),
        sa.CheckConstraint("version > 0", name="admin_reviews_version_check"),
    )
    op.create_index("ix_admin_reviews_status_created", "admin_reviews", ["review_status", "created_at"])

def downgrade() -> None:
    op.drop_index("ix_admin_reviews_status_created", table_name="admin_reviews")
    op.drop_table("admin_reviews")
