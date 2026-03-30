"""User.created_by_user_id + retrait operateur_salles + admin global -> salle_admin par salle."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0015_user_created_by_rbac"
down_revision: Union[str, None] = "0014_operateur_salles_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_users_created_by_user_id", "users", ["created_by_user_id"])
    op.create_foreign_key(
        "fk_users_created_by_user_id",
        "users",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Retrait rôle global operateur_salles
    op.execute(
        "DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE key = 'operateur_salles');"
    )
    op.execute("DELETE FROM roles WHERE key = 'operateur_salles';")

    # Ancien rôle global `admin` (hors super_admin) -> salle_admin sur chaque salle existante
    op.execute(
        """
        INSERT INTO salle_users (salle_id, user_id, role_id)
        SELECT s.id, ur.user_id, (SELECT id FROM roles WHERE key = 'salle_admin' LIMIT 1)
        FROM user_roles ur
        INNER JOIN roles r ON r.id = ur.role_id AND r.key = 'admin'
        CROSS JOIN salles s
        WHERE ur.user_id NOT IN (
            SELECT ur2.user_id FROM user_roles ur2
            INNER JOIN roles r2 ON r2.id = ur2.role_id AND r2.key = 'super_admin'
        )
        ON CONFLICT (salle_id, user_id, role_id) DO NOTHING;
        """
    )
    op.execute(
        """
        DELETE FROM user_roles ur
        USING roles r
        WHERE ur.role_id = r.id AND r.key = 'admin';
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_created_by_user_id", "users", type_="foreignkey")
    op.drop_index("ix_users_created_by_user_id", table_name="users")
    op.drop_column("users", "created_by_user_id")
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
