"""Permissions déléguées pour le rôle global admin (équipe ControlPlay)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0018_user_staff_permissions"
down_revision: Union[str, None] = "0017_rental_console"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_staff_permissions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission_key", sa.String(length=64), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "permission_key"),
    )
    op.create_index(
        "ix_user_staff_permissions_granted_by",
        "user_staff_permissions",
        ["granted_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_staff_permissions_granted_by", table_name="user_staff_permissions")
    op.drop_table("user_staff_permissions")
