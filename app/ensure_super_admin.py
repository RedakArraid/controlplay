#!/usr/bin/env python3
"""
Crée ou met à jour un utilisateur super administrateur global (rôle super_admin).

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

from bootstrap_accounts import upsert_global_super_user
from database import SessionLocal


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
        created, user = upsert_global_super_user(
            db,
            email=email,
            password=password,
            display_name=name,
        )
        db.commit()
        action = "Créé" if created else "Mis à jour"
        print(f"{action} — {user.email} (id={user.id}) avec rôle super_admin")
        return 0
    except Exception as e:
        db.rollback()
        print(e, file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
