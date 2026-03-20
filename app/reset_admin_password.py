#!/usr/bin/env python3
"""
Met à jour le mot de passe (bcrypt) de l'utilisateur identifié par ADMIN_USERNAME
(email ou téléphone) avec la valeur ADMIN_PASSWORD, lues depuis l'environnement
(typiquement le fichier .env du conteneur `app`).

Usage (depuis la racine du projet) :
  make reset-admin
  # ou
  docker compose exec app sh -lc "cd /app && python reset_admin_password.py"
"""
from __future__ import annotations

import os
import sys

import bcrypt
from sqlalchemy import or_

from database import SessionLocal
from models import User


def main() -> int:
    ident = (os.getenv("ADMIN_USERNAME") or "").strip()
    pwd = os.getenv("ADMIN_PASSWORD") or ""
    if not ident:
        print("ADMIN_USERNAME manquant dans l'environnement.", file=sys.stderr)
        return 1
    if not pwd:
        print("ADMIN_PASSWORD manquant dans l'environnement.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(or_(User.email == ident, User.phone == ident))
            .first()
        )
        if not user:
            print(f"Utilisateur introuvable (email ou phone): {ident!r}", file=sys.stderr)
            return 1
        user.password_hash = bcrypt.hashpw(
            pwd.encode("utf-8"), bcrypt.gensalt(rounds=12)
        ).decode()
        user.is_active = True
        db.commit()
        print(f"OK — mot de passe mis à jour pour {ident} (user id={user.id})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
