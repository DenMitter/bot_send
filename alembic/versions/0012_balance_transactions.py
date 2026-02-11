"""balance transactions

Revision ID: 0012_balance_transactions
Revises: 0011_billing
Create Date: 2026-01-28 16:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_balance_transactions"
down_revision = "0011_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "balance_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("tx_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("balance_transactions")
