#!/usr/bin/env python3
"""
Crée ou met à jour un utilisateur super administrateur global (rôles super_admin + admin legacy).

Variables d'environnement :
  SUPER_ADMIN_EMAIL    (défaut: superadmin@controlplay.com)
  SUPER_ADMIN_PASSWORD (défaut: admin123)
  SUPER_ADMIN_NAME     (défaut: Super admin)

Usage :
  docker compose exec app sh -lc 'cd /app && python ensure_super_admin.py'
  # ou avec variables :
  docker compose exec app sh -lc 'cd /app && SUPER_ADMIN_PASSWORD=secret python ensure_super_admin.py'
"""
from __future__ import annotations

import os
import sys

import bcrypt

from database import SessionLocal
from models import Role, User, UserRole


def main() -> int:
    email = (os.getenv("SUPER_ADMIN_EMAIL") or "superadmin@controlplay.com").strip()
    password = os.getenv("SUPER_ADMIN_PASSWORD") or "admin123"
    name = (os.getenv("SUPER_ADMIN_NAME") or "Super admin").strip()

    if not email or "@" not in email:
        print("SUPER_ADMIN_EMAIL invalide.", file=sys.stderr)
        return 1
    if not password:
        print("SUPER_ADMIN_PASSWORD vide.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        pwd_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt(rounds=12)
        ).decode()

        if not user:
            user = User(
                name=name,
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
            user.name = name
            user.password_hash = pwd_hash
            user.is_active = True
            db.flush()
            created = False

        super_r = db.query(Role).filter(Role.key == "super_admin").first()
        legacy_r = db.query(Role).filter(Role.key == "admin").first()
        if not super_r:
            print("Rôle super_admin introuvable. Lance les migrations / seed.", file=sys.stderr)
            return 1

        for role in (super_r, legacy_r):
            if not role:
                continue
            exists = (
                db.query(UserRole)
                .filter(
                    UserRole.user_id == user.id,
                    UserRole.role_id == role.id,
                )
                .first()
            )
            if not exists:
                db.add(UserRole(user_id=user.id, role_id=role.id))

        db.commit()
        action = "Créé" if created else "Mis à jour"
        print(f"{action} — {email} (id={user.id}) avec rôles super_admin" + (" + admin" if legacy_r else ""))
        return 0
    except Exception as e:
        db.rollback()
        print(e, file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
