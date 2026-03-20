"""Concurrency guards for sessions per station

Ensure at most one session per station is in `pending` or `active` state.
This prevents double activation when webhooks are replayed or processed concurrently.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_station_session"
down_revision: Union[str, None] = "0003_add_customer_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "ux_game_sessions_station_pending_active"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "game_sessions",
        ["station_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','active')"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="game_sessions")

