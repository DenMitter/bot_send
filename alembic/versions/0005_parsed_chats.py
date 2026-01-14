"""parsed chats

Revision ID: 0005_parsed_chats
Revises: 0004_parsed_users_unique
Create Date: 2024-01-01 00:00:04.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_parsed_chats"
down_revision = "0004_parsed_users_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "parsed_chats" not in tables:
        op.create_table(
            "parsed_chats",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("owner_id", sa.BigInteger, nullable=False),
            sa.Column("chat_id", sa.BigInteger, nullable=False),
            sa.Column("title", sa.String(length=255)),
            sa.Column("username", sa.String(length=64)),
            sa.Column("chat_type", sa.String(length=32)),
            sa.Column("created_at", sa.DateTime, nullable=False),
        )
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("parsed_chats")}
    if "ix_parsed_chats_owner_id" not in existing_indexes:
        op.create_index("ix_parsed_chats_owner_id", "parsed_chats", ["owner_id"])
    if "ux_parsed_chats_owner_chat" not in existing_indexes:
        op.create_index("ux_parsed_chats_owner_chat", "parsed_chats", ["owner_id", "chat_id"], unique=True)

    op.alter_column(
        "mailings",
        "target_source",
        type_=sa.Enum("subscribers", "parsed", "chats", name="targetsource"),
        existing_type=sa.Enum("subscribers", "parsed", name="targetsource"),
    )


def downgrade() -> None:
    op.alter_column(
        "mailings",
        "target_source",
        type_=sa.Enum("subscribers", "parsed", name="targetsource"),
        existing_type=sa.Enum("subscribers", "parsed", "chats", name="targetsource"),
    )
    op.drop_index("ux_parsed_chats_owner_chat", table_name="parsed_chats")
    op.drop_index("ix_parsed_chats_owner_id", table_name="parsed_chats")
    op.drop_table("parsed_chats")
