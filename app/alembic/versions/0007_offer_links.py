"""Offer links: offres templates + liaisons vers salles/stations

Revision ID: 0007_offer_links
Revises: 0006_salles_station
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_offer_links"
down_revision: Union[str, None] = "0006_salles_station"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "station_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("station_id", "offer_id", name="ux_station_offer"),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"]),
    )
    op.create_index("ix_station_offers_station_id", "station_offers", ["station_id"], unique=False)
    op.create_index("ix_station_offers_offer_id", "station_offers", ["offer_id"], unique=False)

    op.create_table(
        "salle_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("salle_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("salle_id", "offer_id", name="ux_salle_offer"),
        sa.ForeignKeyConstraint(["salle_id"], ["salles.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"]),
    )
    op.create_index("ix_salle_offers_salle_id", "salle_offers", ["salle_id"], unique=False)
    op.create_index("ix_salle_offers_offer_id", "salle_offers", ["offer_id"], unique=False)

    # Migration des données existantes:
    # - offers.station_id != NULL => station_offers
    # - offers.station_id IS NULL => salle_offers pour toutes les salles + station_offers
    #   pour les stations sans salle.
    op.execute(
        """
        INSERT INTO station_offers (station_id, offer_id, is_active)
        SELECT o.station_id, o.id, true
        FROM offers o
        WHERE o.station_id IS NOT NULL
        ON CONFLICT (station_id, offer_id) DO NOTHING;
        """
    )

    op.execute(
        """
        INSERT INTO salle_offers (salle_id, offer_id, is_active)
        SELECT sl.id, o.id, true
        FROM salles sl
        CROSS JOIN offers o
        WHERE o.station_id IS NULL
        ON CONFLICT (salle_id, offer_id) DO NOTHING;
        """
    )

    op.execute(
        """
        INSERT INTO station_offers (station_id, offer_id, is_active)
        SELECT st.id, o.id, true
        FROM stations st
        CROSS JOIN offers o
        WHERE st.salle_id IS NULL AND o.station_id IS NULL
        ON CONFLICT (station_id, offer_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_salle_offers_offer_id", table_name="salle_offers")
    op.drop_index("ix_salle_offers_salle_id", table_name="salle_offers")
    op.drop_table("salle_offers")

    op.drop_index("ix_station_offers_offer_id", table_name="station_offers")
    op.drop_index("ix_station_offers_station_id", table_name="station_offers")
    op.drop_table("station_offers")

