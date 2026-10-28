"""Add customer-owned persistent chat conversations and bounded message history.

Revision ID: 0004_add_support_conversations
Revises: 0003_add_admin_reviews
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_add_support_conversations"
down_revision = "0003_add_admin_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_conversations",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", sa.String(30), sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("selected_order_id", sa.String(30), sa.ForeignKey("orders.order_id"), nullable=True),
        sa.Column("linked_ticket_id", sa.String(30), sa.ForeignKey("tickets.ticket_id"), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="OPEN"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("version > 0", name="support_conversations_version_check"),
    )
    op.create_index("ix_support_conversations_customer_updated", "support_conversations", ["customer_id", "updated_at"])
    op.create_table(
        "support_messages",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("support_conversations.conversation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_role", sa.String(20), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("client_request_id", sa.String(80), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("sender_role IN ('CUSTOMER', 'ASSISTANT', 'SYSTEM_EVENT')", name="support_messages_sender_role_check"),
        sa.UniqueConstraint("conversation_id", "client_request_id", name="support_messages_conversation_request_key"),
    )
    op.create_index("ix_support_messages_conversation_created", "support_messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_support_messages_conversation_created", table_name="support_messages")
    op.drop_table("support_messages")
    op.drop_index("ix_support_conversations_customer_updated", table_name="support_conversations")
    op.drop_table("support_conversations")
