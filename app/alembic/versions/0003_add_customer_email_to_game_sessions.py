"""Add customer_email to game_sessions

Revision ID: 0003_add_customer_email_to_game_sessions
Revises: 0002_add_station_id_to_offers
Create Date: 2026-03-19 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_add_customer_email"
down_revision: Union[str, None] = "0002_add_station_id_to_offers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_sessions", sa.Column("customer_email", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("game_sessions", "customer_email")

