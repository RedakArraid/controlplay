"""
API JSON pour la SPA React (auth, bootstrap, listes).
Les handlers importent `main` en différé pour éviter les imports circulaires.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import (
    FeedbackEntry,
    GameSession,
    Offer,
    PaymentProviderConfig,
    RentalPlan,
    RentalConsole,
    RentalGame,
    RentalConsoleGame,
    Salle,
    Role,
    SalleOffer,
    SalleUser,
    Station,
    StationOffer,
    User,
    UserRole,
    UserStaffPermission,
)

router = APIRouter(tags=["api"])


class LoginBody(BaseModel):
    identifier: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    next: str = "/admin"


class UserOut(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    is_active: bool


class AuthMeOut(BaseModel):
    user: UserOut
    is_super_admin: bool
    is_platform_staff: bool
    staff_permissions: list[str]
    is_global_salle_admin: bool
    is_gerant_only: bool


class SalleUpsertBody(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    latitude: float | None = None
    longitude: float | None = None


class StationUpsertBody(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    #: Requis : poste « salle de jeu » (Broadlink / sessions). La location se gère via ``/admin/rental-consoles``.
    broadlink_ip: str | None = None
    #: Toujours ``game_room`` pour une ligne ``stations`` (écriture refusée autrement).
    usage_kind: str = "game_room"
    salle_code: str | None = None
    tv_size_inches: int | None = None
    console_model: str | None = None
    vr_headset_model: str | None = None
    controller_count: int | None = Field(None, ge=0)
    bundled_games: str | None = None
    ir_code_hdmi1: str | None = None
    ir_code_hdmi2: str | None = None
    is_active: bool = True


def _station_usage_broadlink(body: StationUpsertBody) -> tuple[str, str | None]:
    usage_kind = (body.usage_kind or "game_room").strip().lower()
    if usage_kind != "game_room":
        raise HTTPException(
            status_code=400,
            detail="Les fiches location se gèrent dans Consoles location (API /admin/rental-consoles), pas comme station.",
        )
    ip = (body.broadlink_ip or "").strip() or None
    if not ip:
        raise HTTPException(
            status_code=400,
            detail="Broadlink IP obligatoire pour une station « salle de jeu ».",
        )
    return usage_kind, ip


class OfferUpsertBody(BaseModel):
    name: str = Field(..., min_length=1)
    duration_minutes: int
    price_xof: int
    is_active: bool = True


class RentalPlanUpsertBody(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    duration_label: str = Field(..., min_length=1)
    price_xof: int = Field(..., ge=0)
    provider: str = "paystack"
    rental_console_id: int | None = None
    is_active: bool = True


class RentalGameUpsertBody(BaseModel):
    name: str = Field(..., min_length=1)
    genre: str | None = None
    platform: str | None = None
    is_active: bool = True


class RentalConsoleGamesBody(BaseModel):
    game_ids: list[int] = Field(default_factory=list)


class RentalConsoleUpsertBody(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    tv_size_inches: int | None = None
    console_model: str | None = None
    controller_count: int | None = Field(None, ge=0)
    notes: str | None = None
    is_active: bool = True


class SalleOffersUpdateBody(BaseModel):
    offer_ids: list[int] = Field(default_factory=list)


class SalleUsersUpdateBody(BaseModel):
    manager_user_ids: list[int] = Field(default_factory=list)
    responsable_user_ids: list[int] = Field(default_factory=list)


class StaffPermissionsBody(BaseModel):
    keys: list[str] = Field(default_factory=list)


class SuperUserCreateBody(BaseModel):
    name: str = Field(..., min_length=1)
    email: str | None = None
    phone: str | None = None
    password: str = Field(..., min_length=1)
    is_active: bool = True
    global_roles: list[str] = Field(default_factory=list)


class SuperUserStatusBody(BaseModel):
    is_active: bool


class SuperUserUpdateBody(BaseModel):
    name: str = Field(..., min_length=1)
    email: str | None = None
    phone: str | None = None
    password: str | None = None
    is_active: bool = True


class SuperUsersBulkStatusBody(BaseModel):
    user_ids: list[int] = Field(default_factory=list)
    is_active: bool


class SuperUsersBulkPasswordBody(BaseModel):
    user_ids: list[int] = Field(default_factory=list)


class PublicFeedbackCreateBody(BaseModel):
    station_code: str | None = None
    session_reference: str | None = None
    rating: int = Field(..., ge=1, le=5)
    category: str = "general"
    comment: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class AdminFeedbackStatusBody(BaseModel):
    status: str = Field(..., min_length=1)


class SalleUserOut(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    is_active: bool
    is_manager: bool
    is_responsable: bool


class SalleUsersOut(BaseModel):
    salle: dict[str, Any]
    viewer: dict[str, Any]
    users: list[SalleUserOut]


def _lazy():
    import main as m

    return m



@router.get("/super-admin/users")
def api_super_admin_users(
    request: Request,
    q: str = Query("", alias="q"),
    status: str = Query("all", alias="status"),
    role: str = Query("all", alias="role"),
    creator: str = Query("all", alias="creator"),
    sort_by: str = Query("id", alias="sort_by"),
    sort_dir: str = Query("desc", alias="sort_dir"),
    page: int = Query(1, ge=1, alias="page"),
    page_size: int = Query(20, ge=1, le=200, alias="page_size"),
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    if not super_a and not m.has_staff_users_access(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")

    users = db.query(User).order_by(User.id.desc()).limit(5000).all()
    uids = [u.id for u in users]
    gmap, smap = m._batch_user_roles_maps(db, uids)
    if not super_a:
        users = [u for u in users if "super_admin" not in gmap.get(u.id, [])]
        uids = [u.id for u in users]
    creator_ids = {
        u.created_by_user_id for u in users if u.created_by_user_id is not None
    }
    creators: dict[int, User] = {}
    if creator_ids:
        creators = {
            c.id: c
            for c in db.query(User).filter(User.id.in_(list(creator_ids))).all()
        }

    row_by_id: dict[int, dict[str, Any]] = {}
    for u in users:
        cb = creators.get(u.created_by_user_id) if u.created_by_user_id else None
        row_by_id[u.id] = {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "phone": u.phone,
            "is_active": u.is_active,
            "created_by": (
                {
                    "id": cb.id,
                    "name": cb.name,
                    "email": cb.email,
                    "phone": cb.phone,
                }
                if cb
                else None
            ),
            "global_roles": sorted(set(gmap.get(u.id, []))),
            "salle_roles": [{"code": c, "role": r} for c, r in sorted(smap.get(u.id, []))],
        }

    status = (status or "all").strip().lower()
    role = (role or "all").strip()
    creator = (creator or "all").strip().lower()
    sort_by = (sort_by or "id").strip().lower()
    sort_dir = (sort_dir or "desc").strip().lower()
    needle = (q or "").strip().lower()

    rows = list(row_by_id.values())
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if status == "active" and not row["is_active"]:
            continue
        if status == "inactive" and row["is_active"]:
            continue
        if role != "all" and role not in row["global_roles"]:
            continue
        if creator == "none" and row["created_by"] is not None:
            continue
        if creator not in ("all", "none"):
            if row["created_by"] is None or str(row["created_by"]["id"]) != creator:
                continue
        if needle:
            bag = " ".join(
                [
                    str(row["id"]),
                    row["name"] or "",
                    row["email"] or "",
                    row["phone"] or "",
                    " ".join(row["global_roles"]),
                    " ".join(
                        [f"{s['code']}:{s['role']}" for s in row["salle_roles"]]
                    ),
                    row["created_by"]["name"] if row["created_by"] else "",
                ]
            ).lower()
            if needle not in bag:
                continue
        filtered.append(row)

    reverse = sort_dir != "asc"
    if sort_by == "name":
        filtered.sort(key=lambda r: (r["name"] or "").lower(), reverse=reverse)
    elif sort_by == "email":
        filtered.sort(key=lambda r: (r["email"] or "").lower(), reverse=reverse)
    elif sort_by == "creator":
        filtered.sort(
            key=lambda r: (
                (r["created_by"]["name"] if r["created_by"] else "").lower()
            ),
            reverse=reverse,
        )
    else:
        filtered.sort(key=lambda r: int(r["id"]), reverse=reverse)

    creator_map: dict[int, str] = {}
    for r in filtered:
        cb = r["created_by"]
        if cb is not None:
            creator_map[int(cb["id"])] = f"{cb['name']} (#{cb['id']})"
    creator_options = [
        {"id": cid, "label": label}
        for cid, label in sorted(creator_map.items(), key=lambda x: x[1].lower())
    ]

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "users": filtered[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "creator_options": creator_options,
    }

@router.post("/super-admin/users")
def api_super_admin_create_user(
    request: Request, body: SuperUserCreateBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    if not super_a and not m.has_staff_users_access(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")

    email = (body.email or "").strip() or None
    phone = (body.phone or "").strip() or None
    if email is None and phone is None:
        raise HTTPException(status_code=400, detail="Email ou téléphone requis")

    global_roles = sorted(set((body.global_roles or [])))
    if not super_a and "super_admin" in global_roles:
        raise HTTPException(
            status_code=403,
            detail="Seul le super administrateur peut accorder le rôle super_admin.",
        )

    user = User(
        name=body.name.strip(),
        email=email,
        phone=phone,
        password_hash=m.hash_password(body.password),
        is_active=bool(body.is_active),
        created_by_user_id=uid,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    if global_roles:
        roles = db.query(Role).filter(Role.key.in_(global_roles)).all()
        role_by_key = {r.key: r for r in roles}
        for key in global_roles:
            role = role_by_key.get(key)
            if role:
                db.add(UserRole(user_id=user.id, role_id=role.id))
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return {"ok": True, "user_id": user.id}

@router.put("/super-admin/users/{target_user_id}/status")
def api_super_admin_set_user_status(
    target_user_id: int,
    body: SuperUserStatusBody,
    request: Request,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    if not super_a and not m.has_staff_users_access(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")

    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    gmap, _ = m._batch_user_roles_maps(db, [target.id])
    if not super_a and "super_admin" in gmap.get(target.id, []):
        raise HTTPException(
            status_code=403,
            detail="Compte super administrateur : réservé au super administrateur.",
        )

    target.is_active = bool(body.is_active)
    db.commit()
    return {"ok": True}

@router.put("/super-admin/users/bulk-status")
def api_super_admin_bulk_set_user_status(
    body: SuperUsersBulkStatusBody,
    request: Request,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    if not super_a and not m.has_staff_users_access(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")

    ids = sorted({int(x) for x in body.user_ids if int(x) > 0})
    if not ids:
        return {"ok": True, "updated": 0}

    users = db.query(User).filter(User.id.in_(ids)).all()
    if not users:
        return {"ok": True, "updated": 0}

    if not super_a:
        gmap, _ = m._batch_user_roles_maps(db, [u.id for u in users])
        users = [u for u in users if "super_admin" not in gmap.get(u.id, [])]

    for u in users:
        u.is_active = bool(body.is_active)
        u.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True, "updated": len(users)}

@router.post("/super-admin/users/bulk-password-reset")
def api_super_admin_bulk_password_reset(
    body: SuperUsersBulkPasswordBody,
    request: Request,
    db: Session = Depends(get_db),
):
    """Génère un mot de passe aléatoire par compte ; réponse unique avec les mots de passe en clair."""
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    if not super_a and not m.has_staff_users_access(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")

    ids = sorted({int(x) for x in body.user_ids if int(x) > 0})
    if not ids:
        return {"ok": True, "results": []}

    users = db.query(User).filter(User.id.in_(ids)).all()
    if not users:
        return {"ok": True, "results": []}

    if not super_a:
        gmap, _ = m._batch_user_roles_maps(db, [u.id for u in users])
        users = [u for u in users if "super_admin" not in gmap.get(u.id, [])]

    results: list[dict[str, Any]] = []
    for u in users:
        plain = secrets.token_urlsafe(12)
        u.password_hash = m.hash_password(plain)
        u.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        results.append(
            {
                "user_id": u.id,
                "name": u.name,
                "email": u.email,
                "phone": u.phone,
                "password": plain,
            }
        )
    db.commit()
    return {"ok": True, "results": results}

@router.put("/super-admin/users/{target_user_id}")
def api_super_admin_update_user(
    target_user_id: int,
    body: SuperUserUpdateBody,
    request: Request,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    if not super_a and not m.has_staff_users_access(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")

    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    gmap, _ = m._batch_user_roles_maps(db, [target.id])
    if not super_a and "super_admin" in gmap.get(target.id, []):
        raise HTTPException(
            status_code=403,
            detail="Compte super administrateur : réservé au super administrateur.",
        )

    target.name = body.name.strip()
    target.email = (body.email or "").strip() or None
    target.phone = (body.phone or "").strip() or None
    target.is_active = bool(body.is_active)
    if body.password is not None and body.password.strip():
        target.password_hash = m.hash_password(body.password.strip())
    target.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")
    return {"ok": True}

@router.get("/super-admin/users/{target_user_id}/roles")
def api_super_admin_user_roles_detail(
    target_user_id: int, request: Request, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    if not super_a and not m.has_staff_users_access(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")
    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    gmap, smap = m._batch_user_roles_maps(db, [target.id])
    gk = sorted(set(gmap.get(target.id, [])))
    if not super_a and "super_admin" in gk:
        raise HTTPException(
            status_code=403,
            detail="Compte super administrateur : réservé au super administrateur.",
        )
    su_list = (
        db.query(SalleUser, Salle.code, Salle.name, Role.key)
        .join(Salle, Salle.id == SalleUser.salle_id)
        .join(Role, Role.id == SalleUser.role_id)
        .filter(SalleUser.user_id == target.id)
        .order_by(Salle.code, Role.key)
        .all()
    )
    salles = db.query(Salle).order_by(Salle.code).all()
    creator = None
    if target.created_by_user_id is not None:
        cb = db.query(User).filter(User.id == target.created_by_user_id).first()
        if cb:
            creator = {
                "id": cb.id,
                "name": cb.name,
                "email": cb.email,
                "phone": cb.phone,
            }

    return {
        "user": {
            "id": target.id,
            "name": target.name,
            "email": target.email,
            "phone": target.phone,
            "is_active": target.is_active,
            "created_by_user_id": target.created_by_user_id,
            "created_by": creator,
        },
        "global_roles": gk,
        "salle_assignments": [
            {"salle_id": su.salle_id, "code": scode, "name": sname, "role": rk}
            for su, scode, sname, rk in su_list
        ],
        "salles": [{"id": s.id, "code": s.code, "name": s.name} for s in salles],
        "editable_salle_roles": [
            {"key": "responsable", "label": "Responsable"},
            {"key": "manager", "label": "Gérant (manager)"},
        ],
        "removable_global_roles": (
            list(getattr(m, "_SUPER_ADMIN_REMOVABLE_GLOBAL_ROLE_KEYS", frozenset()))
            if super_a
            else []
        ),
        "viewer_can_manage_super_admins": super_a,
    }

@router.get("/super-admin/providers")
def api_super_admin_providers(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.is_global_super_admin(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")
    cfg = db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    if not cfg:
        return {"paystack_enabled": False, "cinetpay_enabled": False}
    return {
        "paystack_enabled": cfg.paystack_enabled,
        "cinetpay_enabled": cfg.cinetpay_enabled,
    }

@router.get("/super-admin/staff/{target_user_id}/permissions")
def api_super_admin_staff_permissions_get(
    target_user_id: int, request: Request, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.is_global_super_admin(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")
    rows = (
        db.query(UserStaffPermission.permission_key)
        .filter(UserStaffPermission.user_id == target_user_id)
        .all()
    )
    keys = sorted({r[0] for r in rows if r[0] in ("operations", "users")})
    return {"keys": keys}

@router.put("/super-admin/staff/{target_user_id}/permissions")
def api_super_admin_staff_permissions_put(
    target_user_id: int,
    body: StaffPermissionsBody,
    request: Request,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.is_global_super_admin(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")
    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    admin_role = db.query(Role).filter(Role.key == "admin").first()
    if not admin_role:
        raise HTTPException(status_code=500, detail="Rôle admin manquant")
    has_admin = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == admin_role.id)
        .first()
    )
    if not has_admin:
        raise HTTPException(
            status_code=400,
            detail="Le compte doit avoir le rôle global admin (équipe ControlPlay).",
        )
    valid = {"operations", "users"}
    keys = [k for k in body.keys if k in valid]
    db.query(UserStaffPermission).filter(UserStaffPermission.user_id == target_user_id).delete()
    for k in keys:
        db.add(
            UserStaffPermission(
                user_id=target_user_id,
                permission_key=k,
                granted_by_user_id=uid,
            )
        )
    db.commit()
    return {"ok": True, "keys": keys}
