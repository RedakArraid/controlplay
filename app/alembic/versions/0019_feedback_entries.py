"""Feedback clients station/session."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_feedback_entries"
down_revision: Union[str, None] = "0018_user_staff_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=256), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("handled_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["handled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_entries_station_id", "feedback_entries", ["station_id"], unique=False)
    op.create_index("ix_feedback_entries_session_id", "feedback_entries", ["session_id"], unique=False)
    op.create_index("ix_feedback_entries_status", "feedback_entries", ["status"], unique=False)
    op.create_index("ix_feedback_entries_handled_by_user_id", "feedback_entries", ["handled_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_feedback_entries_handled_by_user_id", table_name="feedback_entries")
    op.drop_index("ix_feedback_entries_status", table_name="feedback_entries")
    op.drop_index("ix_feedback_entries_session_id", table_name="feedback_entries")
    op.drop_index("ix_feedback_entries_station_id", table_name="feedback_entries")
    op.drop_table("feedback_entries")
