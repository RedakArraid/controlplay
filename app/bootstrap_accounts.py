"""
Logique partagée pour créer ou mettre à jour un compte super administrateur global
(rôle `super_admin` dans `user_roles`).

Utilisé par `ensure_dev_admin.py`, `ensure_super_admin.py` et évite la duplication.
"""
from __future__ import annotations

import bcrypt
from sqlalchemy.orm import Session

from models import Role, User, UserRole


def upsert_global_super_user(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
) -> tuple[bool, User]:
    """
    Crée ou met à jour l'utilisateur (email, mot de passe hashé, nom), rattache
    le rôle global ``super_admin`` s'il existe.

    Ne fait pas ``commit``. Retourne ``(created, user)``.
    """
    email = email.strip()
    display_name = display_name.strip()
    if not email or "@" not in email:
        raise ValueError("Email invalide (attendu une adresse avec @).")
    if not password:
        raise ValueError("Mot de passe vide.")

    user = db.query(User).filter(User.email == email).first()
    pwd_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode()

    if not user:
        user = User(
            name=display_name,
            email=email,
            phone=None,
            avatar=None,
            password_hash=pwd_hash,
            is_active=True,
        )
        db.add(user)
        db.flush()
        created = True
    else:
        user.name = display_name
        user.password_hash = pwd_hash
        user.is_active = True
        db.flush()
        created = False

    super_r = db.query(Role).filter(Role.key == "super_admin").first()
    if not super_r:
        raise RuntimeError("Rôle super_admin introuvable. Lance les migrations.")

    exists = (
        db.query(UserRole)
        .filter(
            UserRole.user_id == user.id,
            UserRole.role_id == super_r.id,
        )
        .first()
    )
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=super_r.id))

    return created, user
