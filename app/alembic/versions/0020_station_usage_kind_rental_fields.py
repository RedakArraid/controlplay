"""Station: usage_kind (jeu vs location), champs location, broadlink optionnel."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_station_usage_kind"
down_revision: Union[str, None] = "0019_feedback_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stations",
        sa.Column(
            "usage_kind",
            sa.String(length=20),
            nullable=False,
            server_default="game_room",
        ),
    )
    op.add_column("stations", sa.Column("controller_count", sa.Integer(), nullable=True))
    op.add_column("stations", sa.Column("bundled_games", sa.Text(), nullable=True))
    op.alter_column(
        "stations",
        "broadlink_ip",
        existing_type=sa.String(length=64),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE stations SET broadlink_ip = '192.168.1.250' WHERE broadlink_ip IS NULL OR broadlink_ip = ''"
        )
    )
    op.alter_column(
        "stations",
        "broadlink_ip",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.drop_column("stations", "bundled_games")
    op.drop_column("stations", "controller_count")
    op.drop_column("stations", "usage_kind")
