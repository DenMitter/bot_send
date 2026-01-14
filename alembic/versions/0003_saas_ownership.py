"""saas ownership

Revision ID: 0003_saas_ownership
Revises: 0002_bigint_user_ids
Create Date: 2024-01-01 00:00:02.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_saas_ownership"
down_revision = "0002_bigint_user_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("owner_id", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("parsed_users", sa.Column("owner_id", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("mailings", sa.Column("owner_id", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_index("ix_accounts_owner_id", "accounts", ["owner_id"])
    op.create_index("ix_parsed_users_owner_id", "parsed_users", ["owner_id"])
    op.create_index("ix_mailings_owner_id", "mailings", ["owner_id"])
    op.alter_column("accounts", "owner_id", server_default=None)
    op.alter_column("parsed_users", "owner_id", server_default=None)
    op.alter_column("mailings", "owner_id", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_mailings_owner_id", table_name="mailings")
    op.drop_index("ix_parsed_users_owner_id", table_name="parsed_users")
    op.drop_index("ix_accounts_owner_id", table_name="accounts")
    op.drop_column("mailings", "owner_id")
    op.drop_column("parsed_users", "owner_id")
    op.drop_column("accounts", "owner_id")
