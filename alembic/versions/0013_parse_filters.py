"""parse filters

Revision ID: 0013_parse_filters
Revises: 0012_balance_transactions
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0013_parse_filters"
down_revision = "0012_balance_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parse_filters",
        sa.Column("owner_id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="all"),
        sa.Column("gender", sa.String(length=16), nullable=False, server_default="any"),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="any"),
        sa.Column("activity", sa.String(length=16), nullable=False, server_default="any"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("parse_filters")
