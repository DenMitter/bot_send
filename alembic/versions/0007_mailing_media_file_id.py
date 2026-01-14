"""mailing media file id

Revision ID: 0007_mailing_media_file_id
Revises: 0006_mailing_chat_id
Create Date: 2024-01-01 00:00:06.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_mailing_media_file_id"
down_revision = "0006_mailing_chat_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mailings", sa.Column("media_file_id", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("mailings", "media_file_id")
