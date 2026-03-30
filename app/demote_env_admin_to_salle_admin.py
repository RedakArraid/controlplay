#!/usr/bin/env python3
"""
Retire les rôles globaux super_admin / admin de l'utilisateur identifié par
ADMIN_USERNAME (email ou téléphone), supprime ses anciennes lignes salle_users,
puis l'affecte comme `salle_admin` sur **toutes** les salles existantes.

À utiliser quand le compte défini dans .env doit être un admin de salle uniquement
(plus d'accès /admin/users, /admin/providers, etc.).

Usage :
  docker compose exec app sh -lc "cd /app && python demote_env_admin_to_salle_admin.py"
  # ou
  make admin-salle-only
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import or_

from database import SessionLocal
from models import Role, Salle, SalleUser, User, UserRole


def main() -> int:
    ident = (os.getenv("ADMIN_USERNAME") or "").strip()
    if not ident:
        print("ADMIN_USERNAME manquant.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(or_(User.email == ident, User.phone == ident))
            .first()
        )
        if not user:
            print(f"Utilisateur introuvable: {ident!r}", file=sys.stderr)
            return 1

        super_r = db.query(Role).filter(Role.key == "super_admin").first()
        legacy_r = db.query(Role).filter(Role.key == "admin").first()
        salle_admin_r = db.query(Role).filter(Role.key == "salle_admin").first()
        if not salle_admin_r:
            print("Rôle salle_admin introuvable en base.", file=sys.stderr)
            return 1

        for r in (super_r, legacy_r):
            if r:
                db.query(UserRole).filter(
                    UserRole.user_id == user.id, UserRole.role_id == r.id
                ).delete(synchronize_session=False)

        # Retirer un éventuel `salle_admin` **global** (user_roles) : le cible est uniquement `salle_users`.
        if salle_admin_r:
            db.query(UserRole).filter(
                UserRole.user_id == user.id, UserRole.role_id == salle_admin_r.id
            ).delete(synchronize_session=False)

        db.query(SalleUser).filter(SalleUser.user_id == user.id).delete(
            synchronize_session=False
        )

        salles = db.query(Salle).all()
        for sl in salles:
            exists = (
                db.query(SalleUser)
                .filter(
                    SalleUser.salle_id == sl.id,
                    SalleUser.user_id == user.id,
                    SalleUser.role_id == salle_admin_r.id,
                )
                .first()
            )
            if not exists:
                db.add(
                    SalleUser(
                        salle_id=sl.id,
                        user_id=user.id,
                        role_id=salle_admin_r.id,
                    )
                )

        db.commit()
        print(
            f"OK — {ident} (id={user.id}) est maintenant salle_admin sur "
            f"{len(salles)} salle(s), sans rôles globaux super_admin/admin/salle_admin."
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
