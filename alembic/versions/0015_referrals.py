"""referrals

Revision ID: 0015_referrals
Revises: 0014_app_settings
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "0015_referrals"
down_revision = "0014_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("bot_subscribers")}
    indexes = {idx["name"] for idx in inspector.get_indexes("bot_subscribers")}

    if "referrer_id" not in columns:
        op.add_column("bot_subscribers", sa.Column("referrer_id", sa.BigInteger(), nullable=True))
    if "referred_at" not in columns:
        op.add_column("bot_subscribers", sa.Column("referred_at", sa.DateTime(), nullable=True))
    if "ix_bot_subscribers_referrer_id" not in indexes:
        op.create_index("ix_bot_subscribers_referrer_id", "bot_subscribers", ["referrer_id"])

    tables = set(inspector.get_table_names())
    if "referral_rewards" not in tables:
        op.create_table(
            "referral_rewards",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("referrer_id", sa.BigInteger(), nullable=False),
            sa.Column("referral_id", sa.BigInteger(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("source_tx_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    reward_indexes = {idx["name"] for idx in inspector.get_indexes("referral_rewards")}
    if "ix_referral_rewards_referrer_id" not in reward_indexes:
        op.create_index("ix_referral_rewards_referrer_id", "referral_rewards", ["referrer_id"])
    if "ix_referral_rewards_referral_id" not in reward_indexes:
        op.create_index("ix_referral_rewards_referral_id", "referral_rewards", ["referral_id"])


def downgrade() -> None:
    op.drop_index("ix_referral_rewards_referral_id", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_referrer_id", table_name="referral_rewards")
    op.drop_table("referral_rewards")

    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("bot_subscribers")}
    indexes = {idx["name"] for idx in inspector.get_indexes("bot_subscribers")}

    if "ix_bot_subscribers_referrer_id" in indexes:
        op.drop_index("ix_bot_subscribers_referrer_id", table_name="bot_subscribers")
    if "referred_at" in columns:
        op.drop_column("bot_subscribers", "referred_at")
    if "referrer_id" in columns:
        op.drop_column("bot_subscribers", "referrer_id")
