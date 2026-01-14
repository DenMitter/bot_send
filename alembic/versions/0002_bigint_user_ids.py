"""bigint user ids

Revision ID: 0002_bigint_user_ids
Revises: 0001_init
Create Date: 2024-01-01 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_bigint_user_ids"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("bot_subscribers", "user_id", type_=sa.BigInteger())
    op.alter_column("parsed_users", "user_id", type_=sa.BigInteger())
    op.alter_column("mailing_recipients", "user_id", type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("mailing_recipients", "user_id", type_=sa.Integer())
    op.alter_column("parsed_users", "user_id", type_=sa.Integer())
    op.alter_column("bot_subscribers", "user_id", type_=sa.Integer())
