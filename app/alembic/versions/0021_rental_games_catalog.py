"""Rental games catalog and console links."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_rental_games_catalog"
down_revision: Union[str, None] = "0020_station_usage_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rental_games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("genre", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rental_games_id", "rental_games", ["id"])
    op.create_index("ix_rental_games_name", "rental_games", ["name"], unique=True)

    op.create_table(
        "rental_console_games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("rental_game_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["rental_game_id"], ["rental_games.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("station_id", "rental_game_id", name="uq_rental_console_game"),
    )
    op.create_index("ix_rental_console_games_id", "rental_console_games", ["id"])
    op.create_index("ix_rental_console_games_station_id", "rental_console_games", ["station_id"])
    op.create_index(
        "ix_rental_console_games_rental_game_id", "rental_console_games", ["rental_game_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_rental_console_games_rental_game_id", table_name="rental_console_games")
    op.drop_index("ix_rental_console_games_station_id", table_name="rental_console_games")
    op.drop_index("ix_rental_console_games_id", table_name="rental_console_games")
    op.drop_table("rental_console_games")

    op.drop_index("ix_rental_games_name", table_name="rental_games")
    op.drop_index("ix_rental_games_id", table_name="rental_games")
    op.drop_table("rental_games")
