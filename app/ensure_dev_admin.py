#!/usr/bin/env python3
"""
Crée ou met à jour le compte de développement documenté dans les tests (super_admin).

Par défaut : admin@test.com / testpass123
(surcharge possible avec DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD, DEV_ADMIN_NAME)

Usage :
  cd app && python ensure_dev_admin.py
  docker compose exec app sh -lc 'cd /app && python ensure_dev_admin.py'
"""
from __future__ import annotations

import os
import sys

from sqlalchemy.orm import Session

from bootstrap_accounts import upsert_global_super_user
from database import SessionLocal


def apply_dev_admin_to_db(db: Session) -> tuple[bool, str]:
    """
    Crée ou met à jour le compte dev (super_admin) dans la session donnée.
    Ne fait pas commit. Retourne (created, email).
    """
    email = (os.getenv("DEV_ADMIN_EMAIL") or "admin@test.com").strip()
    password = os.getenv("DEV_ADMIN_PASSWORD") or "testpass123"
    name = (os.getenv("DEV_ADMIN_NAME") or "Admin dev").strip()

    if not email or "@" not in email:
        raise ValueError("DEV_ADMIN_EMAIL invalide.")
    if not password:
        raise ValueError("DEV_ADMIN_PASSWORD vide.")

    created, user = upsert_global_super_user(
        db,
        email=email,
        password=password,
        display_name=name,
    )
    return created, user.email


def main() -> int:
    db = SessionLocal()
    try:
        created, email = apply_dev_admin_to_db(db)
        db.commit()
        action = "Créé" if created else "Mis à jour"
        print(
            f"{action} — {email} / (mot de passe depuis DEV_ADMIN_PASSWORD ou défaut testpass123) "
            f"(super_admin)"
        )
        return 0
    except Exception as e:
        db.rollback()
        print(e, file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
