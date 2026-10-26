"""Add server-side authentication tables.

Revision ID: 0002_add_auth_tables
Revises: 0001_baseline_existing_schema
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_add_auth_tables"
down_revision = "0001_baseline_existing_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("customer_id", sa.String(length=30), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('CUSTOMER', 'ADMIN')", name="users_role_check"
        ),
        sa.CheckConstraint(
            "(role = 'CUSTOMER' AND customer_id IS NOT NULL) "
            "OR (role = 'ADMIN' AND customer_id IS NULL)",
            name="users_role_customer_check",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.customer_id"], name="users_customer_id_fkey"
        ),
        sa.PrimaryKeyConstraint("user_id", name="users_pkey"),
        sa.UniqueConstraint("customer_id", name="users_customer_id_key"),
    )
    op.create_index(
        "users_email_lower_unique", "users", [sa.text("lower(email)")], unique=True
    )

    op.create_table(
        "user_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="user_sessions_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", name="user_sessions_pkey"),
        sa.UniqueConstraint("token_hash", name="user_sessions_token_hash_key"),
    )
    op.create_index(
        "ix_user_sessions_user_id_expires_at",
        "user_sessions",
        ["user_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_user_id_expires_at", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("users_email_lower_unique", table_name="users")
    op.drop_table("users")
