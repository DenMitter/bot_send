"""init

Revision ID: 0001_init
Revises: 
Create Date: 2024-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


class MailingStatus(str, sa.Enum):
    pass


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("phone", sa.String(length=32), nullable=False, unique=True),
        sa.Column("session_string", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "bot_subscribers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False, unique=True),
        sa.Column("username", sa.String(length=64)),
        sa.Column("first_name", sa.String(length=64)),
        sa.Column("last_name", sa.String(length=64)),
        sa.Column("language", sa.String(length=8)),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "parsed_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False, unique=True),
        sa.Column("username", sa.String(length=64)),
        sa.Column("first_name", sa.String(length=64)),
        sa.Column("last_name", sa.String(length=64)),
        sa.Column("source", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "mailings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id")),
        sa.Column("status", sa.Enum("pending", "running", "paused", "done", "failed", name="mailingstatus")),
        sa.Column(
            "message_type",
            sa.Enum("text", "photo", "video", "sticker", "document", "voice", "audio", name="messagetype"),
        ),
        sa.Column("text", sa.Text),
        sa.Column("media_path", sa.String(length=512)),
        sa.Column("mention", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("target_source", sa.Enum("subscribers", "parsed", name="targetsource")),
        sa.Column("delay_seconds", sa.Float, nullable=False, server_default="1"),
        sa.Column("limit_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "mailing_recipients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("mailing_id", sa.Integer, sa.ForeignKey("mailings.id")),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("username", sa.String(length=64)),
        sa.Column("status", sa.Enum("pending", "sent", "failed", name="recipientstatus")),
        sa.Column("sent_at", sa.DateTime),
        sa.Column("error", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("mailing_recipients")
    op.drop_table("mailings")
    op.drop_table("parsed_users")
    op.drop_table("bot_subscribers")
    op.drop_table("accounts")
