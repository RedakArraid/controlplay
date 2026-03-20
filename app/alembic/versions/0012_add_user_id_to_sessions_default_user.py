"""Link sessions to a user (default_user for guests)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_sessions_user_default"
down_revision: Union[str, None] = "0011_users_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_USER_EMAIL = "default_user@controlplay.local"
DEFAULT_USER_NAME = "default_user"
DEFAULT_USER_PASSWORD_HASH = (
    "$2b$12$ghKTFw8fMiDR3pIDTTrJE.Z9D5RJfDAJGokirjqco065EcLFXXMWC"
)


def upgrade() -> None:
    # 1) Ajout colonnes (nullable pour backfill)
    op.add_column("game_sessions", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column(
        "session_extensions", sa.Column("user_id", sa.Integer(), nullable=True)
    )

    # 2) FK
    op.create_foreign_key(
        "fk_game_sessions_user_id_users",
        "game_sessions",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_session_extensions_user_id_users",
        "session_extensions",
        "users",
        ["user_id"],
        ["id"],
    )

    # 3) Insert user de secours (guest)
    name_sql = DEFAULT_USER_NAME.replace("'", "''")
    email_sql = DEFAULT_USER_EMAIL.replace("'", "''")
    password_hash_sql = DEFAULT_USER_PASSWORD_HASH.replace("'", "''")

    op.execute(
        f"""
        INSERT INTO users
            (name, email, phone, avatar, password_hash, is_active, created_at, updated_at)
        VALUES
            ('{name_sql}',
             '{email_sql}',
             NULL,
             NULL,
             '{password_hash_sql}',
             TRUE,
             now(),
             now())
        ON CONFLICT (email) DO NOTHING
        """
    )

    # 4) Backfill
    default_user_id_sql = (
        "SELECT id FROM users WHERE email = '"
        + DEFAULT_USER_EMAIL.replace("'", "''")
        + "' LIMIT 1"
    )
    op.execute(
        f"UPDATE game_sessions SET user_id = ({default_user_id_sql}) WHERE user_id IS NULL"
    )
    op.execute(
        "UPDATE session_extensions SET user_id = ({}) WHERE user_id IS NULL".format(
            default_user_id_sql
        )
    )

    # 5) Contraintes finales + index
    op.alter_column("game_sessions", "user_id", nullable=False)
    op.alter_column("session_extensions", "user_id", nullable=False)
    op.create_index("ix_game_sessions_user_id", "game_sessions", ["user_id"])
    op.create_index(
        "ix_session_extensions_user_id", "session_extensions", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_extensions_user_id", table_name="session_extensions")
    op.drop_index("ix_game_sessions_user_id", table_name="game_sessions")

    op.drop_constraint(
        "fk_session_extensions_user_id_users", "session_extensions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_game_sessions_user_id_users", "game_sessions", type_="foreignkey"
    )

    op.drop_column("session_extensions", "user_id")
    op.drop_column("game_sessions", "user_id")

