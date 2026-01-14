"""parsed users unique owner

Revision ID: 0004_parsed_users_unique
Revises: 0003_saas_ownership
Create Date: 2024-01-01 00:00:03.000000
"""

from alembic import op


revision = "0004_parsed_users_unique"
down_revision = "0003_saas_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    try:
        op.drop_index("user_id", table_name="parsed_users")
    except Exception:
        pass
    op.create_index(
        "ux_parsed_users_owner_user",
        "parsed_users",
        ["owner_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_parsed_users_owner_user", table_name="parsed_users")
    op.create_index("user_id", "parsed_users", ["user_id"], unique=True)
