"""Rental plans and rental orders (location console, separate from game offers)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0017_rental_console"
down_revision: Union[str, None] = "0016_station_composition_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rental_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_label", sa.String(length=64), nullable=False),
        sa.Column("price_xof", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rental_plans_station_id", "rental_plans", ["station_id"])

    op.create_table(
        "rental_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rental_plan_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("payment_provider", sa.String(length=32), nullable=False),
        sa.Column("payment_reference", sa.String(length=128), nullable=False),
        sa.Column("payment_status", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("customer_email", sa.String(length=256), nullable=True),
        sa.Column("customer_phone", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["rental_plan_id"], ["rental_plans.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_reference"),
    )
    op.create_index("ix_rental_orders_rental_plan_id", "rental_orders", ["rental_plan_id"])
    op.create_index("ix_rental_orders_station_id", "rental_orders", ["station_id"])
    op.create_index("ix_rental_orders_user_id", "rental_orders", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_rental_orders_user_id", table_name="rental_orders")
    op.drop_index("ix_rental_orders_station_id", table_name="rental_orders")
    op.drop_index("ix_rental_orders_rental_plan_id", table_name="rental_orders")
    op.drop_table("rental_orders")
    op.drop_index("ix_rental_plans_station_id", table_name="rental_plans")
    op.drop_table("rental_plans")
