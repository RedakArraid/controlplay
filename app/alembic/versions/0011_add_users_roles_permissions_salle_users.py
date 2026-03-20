"""Add users/roles model and salle pivot, remove legacy salle manager columns."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_users_rbac"
down_revision: Union[str, None] = "0010_add_salle_manager_coords"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Roles (admin/manager/responsable/joueur)
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("key", name="ux_roles_key"),
    )
    op.create_index("ix_roles_key", "roles", ["key"], unique=True)

    # Permissions (optionnel mais prévu pour évoluer)
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=256), nullable=True),
        sa.UniqueConstraint("key", name="ux_permissions_key"),
    )
    op.create_index("ix_permissions_key", "permissions", ["key"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column(
            "permission_id", sa.Integer(), sa.ForeignKey("permissions.id"), primary_key=True
        ),
    )

    # Users (identité + mot de passe hashé)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("avatar", sa.String(length=512), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="ux_users_email"),
        sa.UniqueConstraint("phone", name="ux_users_phone"),
        sa.CheckConstraint(
            "(email IS NOT NULL) OR (phone IS NOT NULL)", name="ck_users_email_or_phone"
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    # Rôles globaux
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), primary_key=True),
    )

    # Rôles par salle (pivot)
    op.create_table(
        "salle_users",
        sa.Column("salle_id", sa.Integer(), sa.ForeignKey("salles.id"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), primary_key=True),
    )
    op.create_index("ix_salle_users_salle_id", "salle_users", ["salle_id"])
    op.create_index("ix_salle_users_user_id", "salle_users", ["user_id"])
    op.create_index("ix_salle_users_role_id", "salle_users", ["role_id"])

    # Suppression legacy colonnes
    op.drop_column("salles", "gerant")
    op.drop_column("salles", "responsable")


def downgrade() -> None:
    op.add_column("salles", sa.Column("responsable", sa.String(length=120), nullable=True))
    op.add_column("salles", sa.Column("gerant", sa.String(length=120), nullable=True))

    op.drop_index("ix_salle_users_role_id", table_name="salle_users")
    op.drop_index("ix_salle_users_user_id", table_name="salle_users")
    op.drop_index("ix_salle_users_salle_id", table_name="salle_users")
    op.drop_table("salle_users")

    op.drop_table("user_roles")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_table("role_permissions")
    op.drop_index("ix_permissions_key", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("ix_roles_key", table_name="roles")
    op.drop_table("roles")

