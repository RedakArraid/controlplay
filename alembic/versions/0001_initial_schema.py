"""Initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-03-19 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price_xof", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_offers_id"), "offers", ["id"], unique=False)

    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("broadlink_ip", sa.String(length=64), nullable=False),
        sa.Column("ir_code_hdmi1", sa.Text(), nullable=True),
        sa.Column("ir_code_hdmi2", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stations_code"), "stations", ["code"], unique=True)
    op.create_index(op.f("ix_stations_id"), "stations", ["id"], unique=False)

    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("payment_provider", sa.String(length=32), nullable=False),
        sa.Column("payment_reference", sa.String(length=128), nullable=False),
        sa.Column("payment_status", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_reference"),
    )
    op.create_index(op.f("ix_game_sessions_id"), "game_sessions", ["id"], unique=False)

    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_event_logs_id"), "event_logs", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_event_logs_id"), table_name="event_logs")
    op.drop_table("event_logs")

    op.drop_index(op.f("ix_game_sessions_id"), table_name="game_sessions")
    op.drop_table("game_sessions")

    op.drop_index(op.f("ix_stations_id"), table_name="stations")
    op.drop_index(op.f("ix_stations_code"), table_name="stations")
    op.drop_table("stations")

    op.drop_index(op.f("ix_offers_id"), table_name="offers")
    op.drop_table("offers")
