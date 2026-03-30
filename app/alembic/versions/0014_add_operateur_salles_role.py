"""Add role operateur_salles (global): create first salle without prior salle_users."""

from typing import Sequence, Union

from alembic import op


revision: str = "0014_operateur_salles_role"
down_revision: Union[str, None] = "0013_super_salle_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO roles (key, name)
        VALUES (
          'operateur_salles',
          'Opérateur — peut créer des salles (sans salle préalable)'
        )
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE key = 'operateur_salles');"
    )
    op.execute("DELETE FROM roles WHERE key = 'operateur_salles';")
