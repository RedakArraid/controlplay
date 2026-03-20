"""Add roles: super_admin (global) and salle_admin (scoped per salle)."""

from typing import Sequence, Union

from alembic import op


revision: str = "0013_super_salle_roles"
down_revision: Union[str, None] = "0012_sessions_user_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert roles if not exist.
    op.execute(
        """
        INSERT INTO roles (key, name)
        VALUES
          ('super_admin', 'Super admin (global)'),
          ('salle_admin', 'Admin de salle (scopé)')
        ON CONFLICT (key) DO NOTHING;
        """
    )

    # Bootstrap compatibility:
    # If a user has global role `admin` but not `super_admin`, grant `super_admin` as well.
    op.execute(
        """
        INSERT INTO user_roles (user_id, role_id)
        SELECT ur.user_id, rs.id
        FROM user_roles ur
        JOIN roles ra ON ra.id = ur.role_id
        JOIN roles rs ON rs.key = 'super_admin'
        WHERE ra.key = 'admin'
        ON CONFLICT (user_id, role_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE key IN ('salle_admin','super_admin'));")
    op.execute("DELETE FROM roles WHERE key IN ('salle_admin','super_admin');")

