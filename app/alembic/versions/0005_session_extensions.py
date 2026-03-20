"""Add session extensions (extra time payments)

Revision ID: 0005_session_extensions
Revises: 0004_station_session
Create Date: 2026-03-20 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_session_extensions"
down_revision: Union[str, None] = "0004_station_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_extensions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("extra_minutes", sa.Integer(), nullable=False),
        sa.Column("payment_provider", sa.String(length=32), nullable=False),
        sa.Column("payment_reference", sa.String(length=128), nullable=False),
        sa.Column("payment_status", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_reference"),
    )
    op.create_index("ix_session_extensions_session_id", "session_extensions", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_session_extensions_session_id", table_name="session_extensions")
    op.drop_table("session_extensions")

