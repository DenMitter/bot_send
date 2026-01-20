"""mailing access hash

Revision ID: 0009_mailing_access_hash
Revises: 0008_mailing_sticker_set
Create Date: 2026-01-20 07:50:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_mailing_access_hash"
down_revision = "0008_mailing_sticker_set"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parsed_users", sa.Column("access_hash", sa.BigInteger(), nullable=True))
    op.add_column("mailing_recipients", sa.Column("access_hash", sa.BigInteger(), nullable=True))
    op.add_column("parsed_chats", sa.Column("access_hash", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("mailing_recipients", "access_hash")
    op.drop_column("parsed_users", "access_hash")
    op.drop_column("parsed_chats", "access_hash")
