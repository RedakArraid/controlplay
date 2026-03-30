"""Station composition (TV size + console/VR model)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016_station_composition_fields"
down_revision: Union[str, None] = "0015_user_created_by_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stations", sa.Column("tv_size_inches", sa.Integer(), nullable=True))
    op.add_column("stations", sa.Column("console_model", sa.String(length=64), nullable=True))
    op.add_column(
        "stations", sa.Column("vr_headset_model", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("stations", "vr_headset_model")
    op.drop_column("stations", "console_model")
    op.drop_column("stations", "tv_size_inches")

