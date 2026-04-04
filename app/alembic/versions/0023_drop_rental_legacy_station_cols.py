"""Drop legacy station columns from rental tables."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_drop_rental_legacy"
down_revision: Union[str, None] = "0022_decouple_rental_consoles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("rental_orders_station_id_fkey", "rental_orders", type_="foreignkey")
    op.drop_index("ix_rental_orders_station_id", table_name="rental_orders")
    op.drop_column("rental_orders", "station_id")

    op.drop_constraint("rental_plans_station_id_fkey", "rental_plans", type_="foreignkey")
    op.drop_index("ix_rental_plans_station_id", table_name="rental_plans")
    op.drop_column("rental_plans", "station_id")


def downgrade() -> None:
    op.add_column("rental_plans", sa.Column("station_id", sa.Integer(), nullable=True))
    op.create_index("ix_rental_plans_station_id", "rental_plans", ["station_id"])
    op.create_foreign_key(
        "rental_plans_station_id_fkey", "rental_plans", "stations", ["station_id"], ["id"]
    )

    op.add_column("rental_orders", sa.Column("station_id", sa.Integer(), nullable=True))
    op.create_index("ix_rental_orders_station_id", "rental_orders", ["station_id"])
    op.create_foreign_key(
        "rental_orders_station_id_fkey", "rental_orders", "stations", ["station_id"], ["id"]
    )
