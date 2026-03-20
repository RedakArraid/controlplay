"""Add manager/responsible and GPS coords to salles."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_add_salle_manager_coords"
down_revision: Union[str, None] = "0009_add_customer_phone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("salles", sa.Column("gerant", sa.String(length=120), nullable=True))
    op.add_column("salles", sa.Column("responsable", sa.String(length=120), nullable=True))
    op.add_column("salles", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("salles", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("salles", "longitude")
    op.drop_column("salles", "latitude")
    op.drop_column("salles", "responsable")
    op.drop_column("salles", "gerant")

