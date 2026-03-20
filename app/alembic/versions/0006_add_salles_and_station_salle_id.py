"""Add salles and link stations to salles

Revision ID: 0006_add_salles_and_station_salle_id
Revises: 0005_session_extensions
Create Date: 2026-03-20 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_salles_station"
down_revision: Union[str, None] = "0005_session_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_salles_code"), "salles", ["code"], unique=True)

    op.add_column("stations", sa.Column("salle_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_stations_salle_id"), "stations", ["salle_id"], unique=False)
    op.create_foreign_key(
        "fk_stations_salle_id_salles",
        "stations",
        "salles",
        ["salle_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_stations_salle_id_salles", "stations", type_="foreignkey")
    op.drop_index(op.f("ix_stations_salle_id"), table_name="stations")
    op.drop_column("stations", "salle_id")

    op.drop_index(op.f("ix_salles_code"), table_name="salles")
    op.drop_table("salles")

