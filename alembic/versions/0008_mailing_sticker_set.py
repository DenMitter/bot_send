"""mailing sticker set

Revision ID: 0008_mailing_sticker_set
Revises: 0007_mailing_media_file_id
Create Date: 2024-01-01 00:00:07.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_mailing_sticker_set"
down_revision = "0007_mailing_media_file_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mailings", sa.Column("sticker_set_name", sa.String(length=255), nullable=True))
    op.add_column("mailings", sa.Column("sticker_set_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("mailings", "sticker_set_index")
    op.drop_column("mailings", "sticker_set_name")
