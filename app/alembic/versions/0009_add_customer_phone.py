"""Add customer_phone to game_sessions and session_extensions."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_add_customer_phone"
down_revision: Union[str, None] = "0008_payment_provider_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_sessions", sa.Column("customer_phone", sa.String(length=64), nullable=True))
    op.add_column(
        "session_extensions",
        sa.Column("customer_phone", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_extensions", "customer_phone")
    op.drop_column("game_sessions", "customer_phone")

