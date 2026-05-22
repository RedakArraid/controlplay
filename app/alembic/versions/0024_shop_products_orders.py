"""Boutique: produits et commandes (vente physique / démat hors temps de jeu)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_shop_products"
down_revision: Union[str, None] = "0023_drop_rental_legacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shop_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_xof", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shop_products_is_active_sort", "shop_products", ["is_active", "sort_order"])

    op.create_table(
        "shop_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_product_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("payment_provider", sa.String(length=32), nullable=False),
        sa.Column("payment_reference", sa.String(length=128), nullable=False),
        sa.Column("payment_status", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("customer_email", sa.String(length=256), nullable=True),
        sa.Column("customer_phone", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["shop_product_id"], ["shop_products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_reference"),
    )
    op.create_index("ix_shop_orders_shop_product_id", "shop_orders", ["shop_product_id"])
    op.create_index("ix_shop_orders_user_id", "shop_orders", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_shop_orders_user_id", table_name="shop_orders")
    op.drop_index("ix_shop_orders_shop_product_id", table_name="shop_orders")
    op.drop_table("shop_orders")
    op.drop_index("ix_shop_products_is_active_sort", table_name="shop_products")
    op.drop_table("shop_products")
