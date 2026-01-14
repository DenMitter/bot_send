"""mailing chat id

Revision ID: 0006_mailing_chat_id
Revises: 0005_parsed_chats
Create Date: 2024-01-01 00:00:05.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_mailing_chat_id"
down_revision = "0005_parsed_chats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mailings", sa.Column("chat_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("mailings", "chat_id")
