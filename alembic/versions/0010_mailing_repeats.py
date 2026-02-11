"""mailing repeat settings

Revision ID: 0010_mailing_repeats
Revises: 0009_mailing_access_hash
Create Date: 2026-01-28 16:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_mailing_repeats"
down_revision = "0009_mailing_access_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mailings", sa.Column("repeat_delay_seconds", sa.Float(), nullable=False, server_default="0"))
    op.add_column("mailings", sa.Column("repeat_count", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("mailings", "repeat_delay_seconds", server_default=None)
    op.alter_column("mailings", "repeat_count", server_default=None)


def downgrade() -> None:
    op.drop_column("mailings", "repeat_count")
    op.drop_column("mailings", "repeat_delay_seconds")
