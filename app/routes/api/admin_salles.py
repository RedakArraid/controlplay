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
from routes.api.common_models import OfferOut, SalleOffersOut
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



@router.get("/admin/salles")
def api_admin_salles(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)
    if full_ops:
        salles = db.query(Salle).order_by(Salle.id.desc()).all()
    else:
        allowed_salle_ids = m.get_scoped_salle_ids(db, uid)
        if allowed_salle_ids:
            salles = (
                db.query(Salle)
                .filter(Salle.id.in_(allowed_salle_ids))
                .order_by(Salle.id.desc())
                .all()
            )
        elif m.is_global_salle_admin(db, uid):
            salles = []
        else:
            raise HTTPException(status_code=403, detail="Accès refusé")
    return {
        "salles": [
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "latitude": s.latitude,
                "longitude": s.longitude,
            }
            for s in salles
        ]
    }

@router.post("/admin/salles")
def api_admin_create_salle(
    request: Request, body: SalleUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)
    has_cap = full_ops or m.is_global_salle_admin(db, uid) or (
        db.query(SalleUser)
        .join(Role, Role.id == SalleUser.role_id)
        .filter(SalleUser.user_id == uid, Role.key == "salle_admin")
        .first()
        is not None
    )
    if not has_cap:
        raise HTTPException(status_code=403, detail="Accès refusé")

    code = body.code.strip()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")
    if db.query(Salle).filter(Salle.code == code).first():
        raise HTTPException(status_code=400, detail="Code salle deja utilise")

    salle = Salle(
        code=code,
        name=name,
        latitude=body.latitude,
        longitude=body.longitude,
    )
    db.add(salle)
    try:
        db.flush()
        if not full_ops:
            salle_admin_role = db.query(Role).filter(Role.key == "salle_admin").first()
            if salle_admin_role:
                db.add(SalleUser(salle_id=salle.id, user_id=uid, role_id=salle_admin_role.id))
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return {
        "ok": True,
        "salle": {
            "id": salle.id,
            "code": salle.code,
            "name": salle.name,
            "latitude": salle.latitude,
            "longitude": salle.longitude,
        },
    }

@router.put("/admin/salles/{salle_id}")
def api_admin_update_salle(
    salle_id: int, request: Request, body: SalleUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")
    if not full_ops and not m.is_effective_salle_admin_for_salle(db, uid, salle_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    code = body.code.strip()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")

    exists = db.query(Salle).filter(Salle.code == code, Salle.id != salle_id).first()
    if exists:
        raise HTTPException(status_code=400, detail="Code salle deja utilise")

    salle.code = code
    salle.name = name
    salle.latitude = body.latitude
    salle.longitude = body.longitude
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return {
        "ok": True,
        "salle": {
            "id": salle.id,
            "code": salle.code,
            "name": salle.name,
            "latitude": salle.latitude,
            "longitude": salle.longitude,
        },
    }

@router.get("/admin/rental-plans")
def api_admin_rental_plans(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")

    full_ops = m.has_platform_operations_scope(db, uid)
    if not full_ops:
        raise HTTPException(
            status_code=403,
            detail="La location ControlPlay est gérée au niveau plateforme.",
        )
    consoles = (
        db.query(RentalConsole)
        .filter(RentalConsole.is_active.is_(True))
        .order_by(RentalConsole.code.asc())
        .all()
    )
    plans_q = db.query(RentalPlan)

    plans = plans_q.order_by(RentalPlan.id.desc()).all()
    console_by_id = {c.id: c for c in consoles}
    return {
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "duration_label": p.duration_label,
                "price_xof": p.price_xof,
                "provider": p.provider,
                "rental_console_id": p.rental_console_id,
                "rental_console_code": (
                    console_by_id.get(p.rental_console_id).code
                    if p.rental_console_id in console_by_id
                    else None
                ),
                "is_active": p.is_active,
            }
            for p in plans
        ],
        "consoles": [{"id": c.id, "code": c.code, "name": c.name} for c in consoles],
    }

@router.post("/admin/rental-plans")
def api_admin_create_rental_plan(
    request: Request, body: RentalPlanUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")
    full_ops = m.has_platform_operations_scope(db, uid)

    if not full_ops:
        raise HTTPException(
            status_code=403,
            detail="La location ControlPlay est gérée au niveau plateforme.",
        )

    rental_console_id = body.rental_console_id
    if rental_console_id is not None:
        rc = (
            db.query(RentalConsole)
            .filter(RentalConsole.id == rental_console_id, RentalConsole.is_active.is_(True))
            .first()
        )
        if not rc:
            raise HTTPException(status_code=400, detail="Console location introuvable/inactive")

    plan = RentalPlan(
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        duration_label=body.duration_label.strip(),
        price_xof=int(body.price_xof),
        provider="paystack",
        rental_console_id=rental_console_id,
        is_active=bool(body.is_active),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"ok": True, "id": plan.id}

@router.put("/admin/rental-plans/{plan_id}")
def api_admin_update_rental_plan(
    plan_id: int, request: Request, body: RentalPlanUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")
    full_ops = m.has_platform_operations_scope(db, uid)
    if not full_ops:
        raise HTTPException(
            status_code=403,
            detail="La location ControlPlay est gérée au niveau plateforme.",
        )

    plan = db.query(RentalPlan).filter(RentalPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Forfait introuvable")

    rental_console_id = body.rental_console_id
    if rental_console_id is not None:
        rc = (
            db.query(RentalConsole)
            .filter(RentalConsole.id == rental_console_id, RentalConsole.is_active.is_(True))
            .first()
        )
        if not rc:
            raise HTTPException(status_code=400, detail="Console location introuvable/inactive")

    plan.name = body.name.strip()
    plan.description = (body.description or "").strip() or None
    plan.duration_label = body.duration_label.strip()
    plan.price_xof = int(body.price_xof)
    plan.provider = "paystack"
    plan.rental_console_id = rental_console_id
    plan.is_active = bool(body.is_active)
    db.commit()
    return {"ok": True}

@router.post("/admin/rental-plans/{plan_id}/delete")
def api_admin_delete_rental_plan(
    plan_id: int, request: Request, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")
    full_ops = m.has_platform_operations_scope(db, uid)
    if not full_ops:
        raise HTTPException(
            status_code=403,
            detail="La location ControlPlay est gérée au niveau plateforme.",
        )

    plan = db.query(RentalPlan).filter(RentalPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Forfait introuvable")
    plan.is_active = False
    db.commit()
    return {"ok": True}

@router.get("/admin/salles/{salle_id}/offers", response_model=SalleOffersOut)
def api_admin_salle_offers_get(salle_id: int, request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    if not full_ops:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    attached_offer_ids = {
        so.offer_id
        for so in db.query(SalleOffer)
        .filter(SalleOffer.salle_id == salle_id, SalleOffer.is_active.is_(True))
        .all()
    }

    if full_ops:
        offers = (
            db.query(Offer)
            .filter(Offer.is_active.is_(True))
            .order_by(Offer.duration_minutes.asc(), Offer.price_xof.asc(), Offer.id.asc())
            .all()
        )
    else:
        allowed_offer_ids = m.get_allowed_offer_ids_for_user(db, uid)
        if not allowed_offer_ids:
            offers = []
        else:
            offers = (
                db.query(Offer)
                .filter(Offer.id.in_(list(allowed_offer_ids)))
                .filter(Offer.is_active.is_(True))
                .order_by(
                    Offer.duration_minutes.asc(),
                    Offer.price_xof.asc(),
                    Offer.id.asc(),
                )
                .all()
            )

    return {
        "salle": {"id": salle.id, "code": salle.code, "name": salle.name},
        "offers": [
            OfferOut(
                id=o.id,
                name=o.name,
                duration_minutes=o.duration_minutes,
                price_xof=o.price_xof,
                provider=o.provider,
                attached=o.id in attached_offer_ids,
            )
            for o in offers
        ],
    }

@router.put("/admin/salles/{salle_id}/offers")
def api_admin_salle_offers_put(
    salle_id: int,
    request: Request,
    body: SalleOffersUpdateBody,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    if not full_ops:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    offer_ids = [int(x) for x in body.offer_ids if isinstance(x, int) or str(x).isdigit()]
    if not full_ops:
        allowed_offer_ids = m.get_allowed_offer_ids_for_user(db, uid)
        offer_ids = [oid for oid in offer_ids if oid in allowed_offer_ids]

    active_ids = {
        o.id
        for o in db.query(Offer)
        .filter(Offer.id.in_(offer_ids), Offer.is_active.is_(True))
        .all()
    }

    db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id).delete()
    for oid in active_ids:
        db.add(SalleOffer(salle_id=salle_id, offer_id=oid, is_active=True))
    db.commit()

    return {"ok": True}

@router.get("/admin/salles/{salle_id}/users", response_model=SalleUsersOut)
def api_admin_salle_users_get(
    salle_id: int, request: Request, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    if not full_ops:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    pick_ids = m._user_ids_allowed_for_manager_responsable_form(
        db, uid, salle_id, super_admin=full_ops
    )

    if pick_ids is None:
        pool_users = (
            db.query(User).filter(User.is_active.is_(True)).order_by(User.id.desc()).all()
        )
    else:
        if not pick_ids:
            pool_users = []
        else:
            pool_users = (
                db.query(User)
                .filter(User.id.in_(list(pick_ids)), User.is_active.is_(True))
                .order_by(User.id.desc())
                .all()
            )

    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    resp_role = db.query(Role).filter(Role.key == "responsable").first()
    if not mgr_role or not resp_role:
        raise HTTPException(status_code=500, detail="Roles manager/responsable manquants")

    assignments = (
        db.query(SalleUser.user_id, Role.key)
        .join(Role, Role.id == SalleUser.role_id)
        .filter(SalleUser.salle_id == salle_id)
        .filter(Role.key.in_(("manager", "responsable")))
        .all()
    )
    assigned_mgr = {user_id for user_id, rk in assignments if rk == "manager"}
    assigned_resp = {user_id for user_id, rk in assignments if rk == "responsable"}

    users_out = [
        SalleUserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            phone=u.phone,
            is_active=u.is_active,
            is_manager=u.id in assigned_mgr,
            is_responsable=u.id in assigned_resp,
        )
        for u in pool_users
    ]

    can_assign_responsable = full_ops or m.is_effective_salle_admin_for_salle(
        db, uid, salle_id
    )

    return {
        "salle": {"id": salle.id, "code": salle.code, "name": salle.name},
        "viewer": {
            "is_super_admin": full_ops,
            "can_assign_responsable": can_assign_responsable,
        },
        "users": users_out,
    }

@router.put("/admin/salles/{salle_id}/users")
def api_admin_salle_users_put(
    salle_id: int,
    request: Request,
    body: SalleUsersUpdateBody,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")
    if not full_ops:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    manager_ids = list({int(x) for x in body.manager_user_ids if int(x) >= 0})
    responsable_ids = list({int(x) for x in body.responsable_user_ids if int(x) >= 0})

    can_assign_responsable = full_ops or m.is_effective_salle_admin_for_salle(
        db, uid, salle_id
    )
    if responsable_ids and not can_assign_responsable:
        raise HTTPException(status_code=403, detail="Accès refusé : responsable non autorisé")

    # Restreindre la liste (non super-admin) à ce que l'admin peut réellement assigner.
    if not full_ops:
        allowed = m._user_ids_allowed_for_manager_responsable_form(
            db, uid, salle_id, super_admin=False
        ) or set()
        for i in manager_ids + responsable_ids:
            if i not in allowed:
                raise HTTPException(status_code=403, detail="Accès refusé : user hors périmètre")

    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    resp_role = db.query(Role).filter(Role.key == "responsable").first()
    if not mgr_role or not resp_role:
        raise HTTPException(status_code=500, detail="Roles manager/responsable manquants")

    # Contrainte : un gérant est lié à une seule salle.
    for user_id in manager_ids:
        existing_other = (
            db.query(SalleUser)
            .filter(SalleUser.user_id == user_id)
            .filter(SalleUser.role_id == mgr_role.id)
            .filter(SalleUser.salle_id != salle_id)
            .first()
        )
        if existing_other:
            raise HTTPException(
                status_code=400,
                detail="Ce compte est déjà gérant d'une autre salle.",
            )

    user_ids = list({*manager_ids, *responsable_ids})
    if user_ids:
        valid = {
            r[0]
            for r in (
                db.query(User.id)
                .filter(User.id.in_(user_ids), User.is_active.is_(True))
                .all()
            )
        }
        missing = [i for i in user_ids if i not in valid]
        if missing:
            raise HTTPException(status_code=400, detail="Certains users sont introuvables/inactifs.")

    role_ids_to_manage = [mgr_role.id, resp_role.id]
    db.query(SalleUser).filter(
        SalleUser.salle_id == salle_id, SalleUser.role_id.in_(role_ids_to_manage)
    ).delete(synchronize_session=False)

    for user_id in manager_ids:
        db.add(SalleUser(salle_id=salle_id, user_id=user_id, role_id=mgr_role.id))
    for user_id in responsable_ids:
        db.add(
            SalleUser(
                salle_id=salle_id,
                user_id=user_id,
                role_id=resp_role.id,
            )
        )
    db.commit()
    return {"ok": True}
