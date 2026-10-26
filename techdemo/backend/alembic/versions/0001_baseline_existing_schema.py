"""Baseline the pre-existing manually created business tables.

Revision ID: 0001_baseline_existing_schema
Revises:
Create Date: 2026-10-25
"""

# revision identifiers, used by Alembic.
revision = "0001_baseline_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """The 11 business tables already exist and are intentionally untouched."""


def downgrade() -> None:
    """The baseline has no database objects to remove."""
