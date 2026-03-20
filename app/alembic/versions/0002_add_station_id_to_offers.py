"""Add station_id to offers

Revision ID: 0002_add_station_id_to_offers
Revises: 0001_initial_schema
Create Date: 2026-03-19 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_add_station_id_to_offers"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("station_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_offers_station_id"), "offers", ["station_id"], unique=False)
    op.create_foreign_key(
        "fk_offers_station_id_stations",
        "offers",
        "stations",
        ["station_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_offers_station_id_stations", "offers", type_="foreignkey")
    op.drop_index(op.f("ix_offers_station_id"), table_name="offers")
    op.drop_column("offers", "station_id")

