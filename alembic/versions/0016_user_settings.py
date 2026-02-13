"""Add user_id to app_settings

Revision ID: 0016_user_settings
Revises: 0015_referrals
Create Date: 2026-02-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision = "0016_user_settings"
down_revision = "0015_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("app_settings")}

    # Add user_id column if it doesn't exist (nullable initially)
    if "user_id" not in columns:
        op.add_column("app_settings", sa.Column("user_id", sa.BigInteger(), nullable=True))

    # Update all NULL user_id values to 0 (global settings)
    op.execute(text("UPDATE app_settings SET user_id = 0 WHERE user_id IS NULL"))

    # Alter column to NOT NULL with default 0
    op.alter_column("app_settings", "user_id", nullable=False, existing_type=sa.BigInteger())

    # Drop old primary key constraint
    try:
        op.drop_constraint("app_settings_pkey", "app_settings", type_="primary")
    except Exception:
        pass

    # Create new primary key with (user_id, key)
    op.create_primary_key("app_settings_pkey", "app_settings", ["user_id", "key"])

    # Create index on user_id for queries
    indexes = {idx["name"] for idx in inspector.get_indexes("app_settings")}
    if "ix_app_settings_user_id" not in indexes:
        op.create_index("ix_app_settings_user_id", "app_settings", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("app_settings")}

    # Remove index
    if "ix_app_settings_user_id" in indexes:
        op.drop_index("ix_app_settings_user_id", "app_settings")

    # Restore old primary key
    try:
        op.drop_constraint("app_settings_pkey", "app_settings", type_="primary")
    except Exception:
        pass

    op.create_primary_key("app_settings_pkey", "app_settings", ["key"])

    # Drop user_id column
    try:
        op.drop_column("app_settings", "user_id")
    except Exception:
        pass
