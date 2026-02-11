"""billing tables

Revision ID: 0011_billing
Revises: 0010_mailing_repeats
Create Date: 2026-01-28 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_billing"
down_revision = "0010_mailing_repeats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_balances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, unique=True, index=True),
        sa.Column("balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "price_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.alter_column("user_balances", "balance", server_default=None)
    op.alter_column("price_config", "price", server_default=None)


def downgrade() -> None:
    op.drop_table("price_config")
    op.drop_table("user_balances")
