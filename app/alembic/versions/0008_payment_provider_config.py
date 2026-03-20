"""Payment provider enable/disable flags (admin toggle)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_payment_provider_config"
down_revision: Union[str, None] = "0007_offer_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_provider_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paystack_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("cinetpay_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO payment_provider_config (paystack_enabled, cinetpay_enabled) VALUES (true, true);")


def downgrade() -> None:
    op.drop_table("payment_provider_config")

