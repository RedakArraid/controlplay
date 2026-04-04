"""Decouple rental consoles from stations."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_decouple_rental_consoles"
down_revision: Union[str, None] = "0021_rental_games_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rental_consoles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("tv_size_inches", sa.Integer(), nullable=True),
        sa.Column("console_model", sa.String(length=64), nullable=True),
        sa.Column("controller_count", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rental_consoles_id", "rental_consoles", ["id"])
    op.create_index("ix_rental_consoles_code", "rental_consoles", ["code"], unique=True)

    op.add_column("rental_plans", sa.Column("rental_console_id", sa.Integer(), nullable=True))
    op.create_index("ix_rental_plans_rental_console_id", "rental_plans", ["rental_console_id"])
    op.create_foreign_key(
        "fk_rental_plans_rental_console_id",
        "rental_plans",
        "rental_consoles",
        ["rental_console_id"],
        ["id"],
    )

    op.add_column("rental_orders", sa.Column("rental_console_id", sa.Integer(), nullable=True))
    op.alter_column("rental_orders", "station_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_rental_orders_rental_console_id", "rental_orders", ["rental_console_id"])
    op.create_foreign_key(
        "fk_rental_orders_rental_console_id",
        "rental_orders",
        "rental_consoles",
        ["rental_console_id"],
        ["id"],
    )

    op.add_column("rental_console_games", sa.Column("rental_console_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_rental_console_games_rental_console_id", "rental_console_games", ["rental_console_id"]
    )
    op.create_foreign_key(
        "fk_rental_console_games_rental_console_id",
        "rental_console_games",
        "rental_consoles",
        ["rental_console_id"],
        ["id"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO rental_consoles (code, name, tv_size_inches, console_model, controller_count, notes, is_active)
            SELECT
              s.code,
              s.name,
              s.tv_size_inches,
              s.console_model,
              s.controller_count,
              s.bundled_games,
              s.is_active
            FROM stations s
            WHERE s.usage_kind = 'rental'
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE rental_plans rp
            SET rental_console_id = rc.id
            FROM stations s
            JOIN rental_consoles rc ON rc.code = s.code
            WHERE rp.station_id = s.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE rental_orders ro
            SET rental_console_id = rc.id
            FROM stations s
            JOIN rental_consoles rc ON rc.code = s.code
            WHERE ro.station_id = s.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE rental_console_games rcg
            SET rental_console_id = rc.id
            FROM stations s
            JOIN rental_consoles rc ON rc.code = s.code
            WHERE rcg.station_id = s.id
            """
        )
    )

    op.execute(sa.text("DELETE FROM rental_console_games WHERE rental_console_id IS NULL"))
    op.alter_column("rental_console_games", "rental_console_id", nullable=False)
    op.drop_constraint("uq_rental_console_game", "rental_console_games", type_="unique")
    op.create_unique_constraint(
        "uq_rental_console_game", "rental_console_games", ["rental_console_id", "rental_game_id"]
    )
    op.drop_column("rental_console_games", "station_id")


def downgrade() -> None:
    op.add_column("rental_console_games", sa.Column("station_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "rental_console_games_station_id_fkey",
        "rental_console_games",
        "stations",
        ["station_id"],
        ["id"],
    )
    op.execute(
        sa.text(
            """
            UPDATE rental_console_games rcg
            SET station_id = s.id
            FROM rental_consoles rc
            JOIN stations s ON s.code = rc.code
            WHERE rcg.rental_console_id = rc.id
            """
        )
    )
    op.execute(sa.text("DELETE FROM rental_console_games WHERE station_id IS NULL"))
    op.alter_column("rental_console_games", "station_id", nullable=False)
    op.drop_constraint("uq_rental_console_game", "rental_console_games", type_="unique")
    op.create_unique_constraint(
        "uq_rental_console_game", "rental_console_games", ["station_id", "rental_game_id"]
    )
    op.drop_constraint(
        "fk_rental_console_games_rental_console_id", "rental_console_games", type_="foreignkey"
    )
    op.drop_index("ix_rental_console_games_rental_console_id", table_name="rental_console_games")
    op.drop_column("rental_console_games", "rental_console_id")

    op.drop_constraint(
        "fk_rental_orders_rental_console_id", "rental_orders", type_="foreignkey"
    )
    op.drop_index("ix_rental_orders_rental_console_id", table_name="rental_orders")
    op.drop_column("rental_orders", "rental_console_id")
    op.alter_column("rental_orders", "station_id", existing_type=sa.Integer(), nullable=False)

    op.drop_constraint(
        "fk_rental_plans_rental_console_id", "rental_plans", type_="foreignkey"
    )
    op.drop_index("ix_rental_plans_rental_console_id", table_name="rental_plans")
    op.drop_column("rental_plans", "rental_console_id")

    op.drop_index("ix_rental_consoles_code", table_name="rental_consoles")
    op.drop_index("ix_rental_consoles_id", table_name="rental_consoles")
    op.drop_table("rental_consoles")
