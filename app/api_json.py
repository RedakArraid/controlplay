"""
API JSON pour la SPA React (auth, bootstrap, listes).
Les handlers importent `main` en différé pour éviter les imports circulaires.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import (
    GameSession,
    Offer,
    PaymentProviderConfig,
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
    broadlink_ip: str = Field(..., min_length=1)
    salle_code: str | None = None
    tv_size_inches: int | None = None
    console_model: str | None = None
    vr_headset_model: str | None = None
    ir_code_hdmi1: str | None = None
    ir_code_hdmi2: str | None = None
    is_active: bool = True


class OfferUpsertBody(BaseModel):
    name: str = Field(..., min_length=1)
    duration_minutes: int
    price_xof: int
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


@router.post("/auth/login")
def api_login(request: Request, body: LoginBody, db: Session = Depends(get_db)):
    m = _lazy()
    u = m._find_user_for_login(db, body.identifier.strip())
    if not u or not m.verify_password(body.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    if not m.user_can_access_admin(db, u):
        raise HTTPException(
            status_code=403,
            detail="Ce compte n’a pas accès à l’administration.",
        )
    request.session["user_id"] = u.id
    next_url = m._login_next_safe(body.next or "/admin")
    return {"ok": True, "redirect": next_url}


@router.post("/auth/logout")
def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/auth/me", response_model=AuthMeOut)
def api_me(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(status_code=401, detail="Non connecté")
    perms = sorted(m.staff_permission_keys(db, uid))
    return AuthMeOut(
        user=UserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            phone=u.phone,
            is_active=u.is_active,
        ),
        is_super_admin=m.is_global_super_admin(db, uid),
        is_platform_staff=m.is_global_platform_staff(db, uid),
        staff_permissions=perms,
        is_global_salle_admin=m.is_global_salle_admin(db, uid),
        is_gerant_only=m.is_session_gerant_only(db, uid),
    )


@router.get("/public/salles")
def api_public_salles(db: Session = Depends(get_db)):
    salles = db.query(Salle).order_by(Salle.id.desc()).all()
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


@router.get("/public/jeux")
def api_public_jeux(db: Session = Depends(get_db)):
    # Pour cette phase, le catalogue marketing est construit à partir des offres
    # (templates de durée/prix) configurées dans l’admin.
    attached_offer_ids = {
        oid
        for (oid,) in db.query(SalleOffer.offer_id)
        .filter(SalleOffer.is_active.is_(True))
        .all()
    } | {
        oid
        for (oid,) in db.query(StationOffer.offer_id)
        .filter(StationOffer.is_active.is_(True))
        .all()
    }

    offers = (
        db.query(Offer)
        .filter(Offer.is_active.is_(True))
        .order_by(Offer.duration_minutes.asc(), Offer.price_xof.asc(), Offer.id.asc())
        .all()
    )

    return {
        "jeux": [
            {
                "id": o.id,
                "name": o.name,
                "duration_minutes": o.duration_minutes,
                "price_xof": o.price_xof,
                "provider": o.provider,
                "attached": o.id in attached_offer_ids,
            }
            for o in offers
        ]
    }


@router.get("/public/stations")
def api_public_stations(db: Session = Depends(get_db)):
    m = _lazy()
    paystack_flag = m.paystack_enabled()
    provider_priority = {"paystack": 0, "cinetpay": 1} if paystack_flag else {"paystack": 1, "cinetpay": 0}

    stations = (
        db.query(Station)
        .filter(Station.is_active.is_(True))
        .order_by(Station.id.desc())
        .limit(200)
        .all()
    )

    rows: list[dict[str, Any]] = []
    for st in stations:
        station_offers = (
            db.query(Offer)
            .join(StationOffer, StationOffer.offer_id == Offer.id)
            .filter(
                StationOffer.station_id == st.id,
                StationOffer.is_active.is_(True),
                Offer.is_active.is_(True),
            )
            .all()
        )

        salle_offers: list[Offer] = []
        if st.salle_id is not None:
            salle_offers = (
                db.query(Offer)
                .join(SalleOffer, SalleOffer.offer_id == Offer.id)
                .filter(
                    SalleOffer.salle_id == st.salle_id,
                    SalleOffer.is_active.is_(True),
                    Offer.is_active.is_(True),
                )
                .all()
            )

        offers_by_duration_price: dict[tuple[int, int], Offer] = {}
        for offer in [*station_offers, *salle_offers]:
            key = (offer.duration_minutes, offer.price_xof)
            current = offers_by_duration_price.get(key)
            if current is None or provider_priority.get(offer.provider, 99) < provider_priority.get(
                current.provider, 99
            ):
                offers_by_duration_price[key] = offer

        offers_sorted = sorted(offers_by_duration_price.values(), key=lambda o: (o.duration_minutes, o.price_xof))

        rows.append(
            {
                "id": st.id,
                "code": st.code,
                "name": st.name,
                "tv_size_inches": st.tv_size_inches,
                "console_model": st.console_model,
                "vr_headset_model": st.vr_headset_model,
                "salle_id": st.salle_id,
                "games": [
                    {
                        "id": o.id,
                        "name": o.name,
                        "duration_minutes": o.duration_minutes,
                        "price_xof": o.price_xof,
                        "provider": o.provider,
                    }
                    for o in offers_sorted
                ],
            }
        )

    return {"stations": rows}


@router.get("/public/stations/{station_code}")
def api_public_station_detail(station_code: str, db: Session = Depends(get_db)):
    m = _lazy()
    paystack_flag = m.paystack_enabled()
    provider_priority = {"paystack": 0, "cinetpay": 1} if paystack_flag else {"paystack": 1, "cinetpay": 0}

    st = db.query(Station).filter(Station.code == station_code, Station.is_active.is_(True)).first()
    if not st:
        raise HTTPException(status_code=404, detail="Station introuvable")

    station_offers = (
        db.query(Offer)
        .join(StationOffer, StationOffer.offer_id == Offer.id)
        .filter(
            StationOffer.station_id == st.id,
            StationOffer.is_active.is_(True),
            Offer.is_active.is_(True),
        )
        .all()
    )

    salle_offers: list[Offer] = []
    if st.salle_id is not None:
        salle_offers = (
            db.query(Offer)
            .join(SalleOffer, SalleOffer.offer_id == Offer.id)
            .filter(
                SalleOffer.salle_id == st.salle_id,
                SalleOffer.is_active.is_(True),
                Offer.is_active.is_(True),
            )
            .all()
        )

    offers_by_duration_price: dict[tuple[int, int], Offer] = {}
    for offer in [*station_offers, *salle_offers]:
        key = (offer.duration_minutes, offer.price_xof)
        current = offers_by_duration_price.get(key)
        if current is None or provider_priority.get(offer.provider, 99) < provider_priority.get(
            current.provider, 99
        ):
            offers_by_duration_price[key] = offer

    offers_sorted = sorted(offers_by_duration_price.values(), key=lambda o: (o.duration_minutes, o.price_xof))
    has_active_session = (
        db.query(GameSession.id)
        .filter(GameSession.station_id == st.id, GameSession.status.in_(["paid", "active", "extended"]))
        .first()
        is not None
    )

    composition: list[str] = []
    if st.tv_size_inches is not None:
        composition.append(f"TV {st.tv_size_inches} pouces")
    if st.console_model:
        composition.append(f"Console {st.console_model}")
    if st.vr_headset_model:
        composition.append(f"VR {st.vr_headset_model}")

    return {
        "station": {
            "id": st.id,
            "code": st.code,
            "name": st.name,
            "salle_id": st.salle_id,
            "composition": composition,
            "has_active_session": has_active_session,
            "offers": [
                {
                    "id": o.id,
                    "name": o.name,
                    "duration_minutes": o.duration_minutes,
                    "price_xof": o.price_xof,
                    "provider": o.provider,
                }
                for o in offers_sorted
            ],
        }
    }


@router.get("/admin/bootstrap")
def api_admin_bootstrap(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    staff_users = m.has_staff_users_access(db, uid)
    staff_ops = m.has_staff_operations_access(db, uid)
    staff_zone = m.can_use_super_admin_zone(db, uid)
    gerant_only = m.is_session_gerant_only(db, uid)
    items: list[dict[str, str]] = []
    if gerant_only:
        items = [
            {"label": "Sessions", "to": "/admin/sessions"},
            {"label": "Session manuelle", "to": "/admin/manual-session"},
        ]
    else:
        items = [
            {"label": "Tableau de bord", "to": "/admin"},
            {"label": "Salles", "to": "/admin/salles"},
            {"label": "Offres", "to": "/admin/offers"},
            {"label": "Stations", "to": "/admin/stations"},
            {"label": "Sessions", "to": "/admin/sessions"},
            {"label": "Dashboard stations", "to": "/admin/dashboard"},
        ]
        if m.can_use_mes_utilisateurs_page(db, uid):
            items.insert(2, {"label": "Mes utilisateurs", "to": "/admin/mes-utilisateurs"})
    if not gerant_only:
        if super_a:
            items.insert(1, {"label": "Utilisateurs globaux", "to": "/super-admin/users"})
            items.append({"label": "Providers PSP", "to": "/super-admin/providers"})
            items.append({"label": "Super admin", "to": "/super-admin"})
        elif staff_zone:
            if staff_users:
                items.insert(1, {"label": "Utilisateurs globaux", "to": "/super-admin/users"})
            items.append({"label": "Équipe ControlPlay", "to": "/super-admin"})
    return {
        "nav": items,
        "is_super_admin": super_a,
        "is_gerant_only": gerant_only,
        "can_manage_providers": super_a,
        "staff_permissions": sorted(m.staff_permission_keys(db, uid)),
    }


@router.get("/admin/dashboard/summary")
def api_dashboard_summary(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)
    now = datetime.utcnow().replace(microsecond=0)
    paystack_flag = m.paystack_enabled()
    cinetpay_flag = m.cinetpay_enabled()

    stations_q = db.query(Station).filter(Station.is_active.is_(True))
    if not full_ops:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if not allowed_salles:
            return {
                "paystack": paystack_flag,
                "cinetpay": cinetpay_flag,
                "stations": [],
                "empty": True,
            }
        stations_q = stations_q.filter(Station.salle_id.in_(allowed_salles))
    stations = stations_q.order_by(Station.id.desc()).limit(200).all()
    rows: list[dict[str, Any]] = []
    for st in stations:
        active_session = (
            db.query(GameSession)
            .filter(GameSession.station_id == st.id, GameSession.status == "active")
            .first()
        )
        pending_session = (
            db.query(GameSession)
            .filter(GameSession.station_id == st.id, GameSession.status == "pending")
            .first()
        )
        paused_session = (
            db.query(GameSession)
            .filter(GameSession.station_id == st.id, GameSession.status == "paused")
            .first()
        )
        remaining_s = ""
        sess_for_timer = active_session or paused_session
        if sess_for_timer and sess_for_timer.end_at:
            remaining_s = f"{max(0, int((sess_for_timer.end_at - now).total_seconds()))}s"
        if active_session:
            state = "ACTIVE"
        elif paused_session:
            state = "PAUSE"
        elif pending_session:
            state = "PENDING"
        else:
            state = "OK"
        rows.append(
            {
                "code": st.code,
                "name": st.name,
                "state": state,
                "remaining_s": remaining_s,
                "duration_min": sess_for_timer.offer.duration_minutes
                if sess_for_timer and sess_for_timer.offer
                else None,
                "price_xof": sess_for_timer.offer.price_xof
                if sess_for_timer and sess_for_timer.offer
                else None,
                "provider": sess_for_timer.payment_provider if sess_for_timer else "",
            }
        )
    return {
        "paystack": paystack_flag,
        "cinetpay": cinetpay_flag,
        "stations": rows,
        "empty": False,
    }


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


@router.post("/admin/stations")
def api_admin_create_station(
    request: Request, body: StationUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    salle_id: int | None = None
    if body.salle_code is not None:
        salle_code = body.salle_code.strip()
        if salle_code:
            salle = db.query(Salle).filter(Salle.code == salle_code).first()
            if not salle:
                raise HTTPException(status_code=400, detail="salle_code introuvable")
            salle_id = salle.id
            if not (full_ops or m.is_effective_salle_admin_for_salle(db, uid, salle_id)):
                raise HTTPException(status_code=403, detail="Accès refusé")
    if salle_id is None and not full_ops:
        # Station non rattachée à une salle : uniquement super admin pour éviter les trous de périmètre.
        raise HTTPException(status_code=403, detail="Accès refusé")

    code = body.code.strip()
    name = body.name.strip()
    ip = body.broadlink_ip.strip()
    if not code or not name or not ip:
        raise HTTPException(status_code=400, detail="Code, nom et broadlink_ip requis")
    if db.query(Station).filter(Station.code == code).first():
        raise HTTPException(status_code=400, detail="Code station deja utilise")

    st = Station(
        code=code,
        name=name,
        broadlink_ip=ip,
        salle_id=salle_id,
        tv_size_inches=body.tv_size_inches,
        console_model=(body.console_model.strip() if body.console_model else None),
        vr_headset_model=(body.vr_headset_model.strip() if body.vr_headset_model else None),
        ir_code_hdmi1=(body.ir_code_hdmi1.strip() if body.ir_code_hdmi1 else None),
        ir_code_hdmi2=(body.ir_code_hdmi2.strip() if body.ir_code_hdmi2 else None),
        is_active=bool(body.is_active),
    )
    db.add(st)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    salle_code = ""
    if st.salle_id is not None:
        salle = db.query(Salle).filter(Salle.id == st.salle_id).first()
        salle_code = salle.code if salle else ""

    return {
        "ok": True,
        "station": {
            "id": st.id,
            "code": st.code,
            "name": st.name,
            "broadlink_ip": st.broadlink_ip,
            "tv_size_inches": st.tv_size_inches,
            "console_model": st.console_model,
            "vr_headset_model": st.vr_headset_model,
            "salle_code": salle_code,
            "is_active": st.is_active,
        },
    }


@router.put("/admin/stations/{station_id}")
def api_admin_update_station(
    station_id: int,
    request: Request,
    body: StationUpsertBody,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    st = db.query(Station).filter(Station.id == station_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Station introuvable")

    # Autorisation : si station rattachée à une salle, l'admin doit être effectif sur cette salle.
    if not full_ops:
        if st.salle_id is None or not m.is_effective_salle_admin_for_salle(db, uid, st.salle_id):
            raise HTTPException(status_code=403, detail="Accès refusé")

    salle_id: int | None = None
    if body.salle_code is not None:
        salle_code = body.salle_code.strip()
        if salle_code:
            salle = db.query(Salle).filter(Salle.code == salle_code).first()
            if not salle:
                raise HTTPException(status_code=400, detail="salle_code introuvable")
            salle_id = salle.id
            if not full_ops and not m.is_effective_salle_admin_for_salle(db, uid, salle_id):
                raise HTTPException(status_code=403, detail="Accès refusé")

    # Changement de rattachement salle (optionnel). Si on enlève salle_id, on force uniquement super admin.
    if st.salle_id is not None and salle_id is None and not full_ops:
        raise HTTPException(status_code=403, detail="Accès refusé")

    code = body.code.strip()
    name = body.name.strip()
    ip = body.broadlink_ip.strip()
    if not code or not name or not ip:
        raise HTTPException(status_code=400, detail="Code, nom et broadlink_ip requis")

    if (
        code != st.code
        and db.query(Station).filter(Station.code == code, Station.id != station_id).first()
    ):
        raise HTTPException(status_code=400, detail="Code station deja utilise")

    st.code = code
    st.name = name
    st.broadlink_ip = ip
    st.salle_id = salle_id
    st.tv_size_inches = body.tv_size_inches
    st.console_model = (body.console_model.strip() if body.console_model else None)
    st.vr_headset_model = (
        body.vr_headset_model.strip() if body.vr_headset_model else None
    )
    st.ir_code_hdmi1 = (body.ir_code_hdmi1.strip() if body.ir_code_hdmi1 else None)
    st.ir_code_hdmi2 = (body.ir_code_hdmi2.strip() if body.ir_code_hdmi2 else None)
    st.is_active = bool(body.is_active)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    salle_code = ""
    if st.salle_id is not None:
        salle = db.query(Salle).filter(Salle.id == st.salle_id).first()
        salle_code = salle.code if salle else ""

    return {
        "ok": True,
        "station": {
            "id": st.id,
            "code": st.code,
            "name": st.name,
            "broadlink_ip": st.broadlink_ip,
            "tv_size_inches": st.tv_size_inches,
            "console_model": st.console_model,
            "vr_headset_model": st.vr_headset_model,
            "salle_code": salle_code,
            "is_active": st.is_active,
        },
    }


@router.get("/admin/stations")
def api_admin_stations(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)
    if full_ops:
        stations = db.query(Station).order_by(Station.id.desc()).all()
        salles = db.query(Salle).order_by(Salle.id.desc()).all()
    else:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if not allowed_salles:
            return {"stations": []}
        stations = (
            db.query(Station)
            .filter(Station.salle_id.in_(allowed_salles))
            .order_by(Station.id.desc())
            .all()
        )
        salles = (
            db.query(Salle)
            .filter(Salle.id.in_(allowed_salles))
            .order_by(Salle.id.desc())
            .all()
        )
    salle_by_id = {sl.id: sl.code for sl in salles}
    return {
        "stations": [
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "broadlink_ip": s.broadlink_ip,
                "tv_size_inches": s.tv_size_inches,
                "console_model": s.console_model,
                "vr_headset_model": s.vr_headset_model,
                "salle_code": salle_by_id.get(s.salle_id, ""),
                "is_active": s.is_active,
            }
            for s in stations
        ]
    }


@router.get("/admin/offers")
def api_admin_offers(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)
    if not full_ops:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        allowed_stations = m.get_allowed_station_ids(db, uid)
        if not allowed_salles or not allowed_stations:
            return {"offers": []}
        used_station_offer_ids = (
            db.query(StationOffer.offer_id)
            .filter(StationOffer.is_active.is_(True))
            .filter(StationOffer.station_id.in_(allowed_stations))
            .distinct()
            .subquery()
        )
        used_salle_offer_ids = (
            db.query(SalleOffer.offer_id)
            .filter(SalleOffer.is_active.is_(True))
            .filter(SalleOffer.salle_id.in_(allowed_salles))
            .distinct()
            .subquery()
        )
    else:
        used_station_offer_ids = (
            db.query(StationOffer.offer_id)
            .filter(StationOffer.is_active.is_(True))
            .distinct()
            .subquery()
        )
        used_salle_offer_ids = (
            db.query(SalleOffer.offer_id)
            .filter(SalleOffer.is_active.is_(True))
            .distinct()
            .subquery()
        )

    offers_filter = or_(
        Offer.id.in_(used_station_offer_ids),
        Offer.id.in_(used_salle_offer_ids),
    )
    if full_ops:
        offers_filter = or_(
            Offer.station_id.is_(None),
            Offer.id.in_(used_station_offer_ids),
            Offer.id.in_(used_salle_offer_ids),
        )

    offers = (
        db.query(Offer)
        .filter(Offer.is_active.is_(True))
        .filter(offers_filter)
        .order_by(Offer.id.desc())
        .all()
    )
    station_offer_counts = dict(
        db.query(StationOffer.offer_id, func.count(StationOffer.station_id))
        .filter(StationOffer.is_active.is_(True))
        .group_by(StationOffer.offer_id)
        .all()
    )
    salle_offer_counts = dict(
        db.query(SalleOffer.offer_id, func.count(SalleOffer.salle_id))
        .filter(SalleOffer.is_active.is_(True))
        .group_by(SalleOffer.offer_id)
        .all()
    )
    return {
        "offers": [
            {
                "id": o.id,
                "name": o.name,
                "duration_minutes": o.duration_minutes,
                "price_xof": o.price_xof,
                "provider": o.provider,
                "stations_n": station_offer_counts.get(o.id, 0),
                "salles_n": salle_offer_counts.get(o.id, 0),
            }
            for o in offers
        ]
    }


@router.post("/admin/offers")
def api_admin_create_offer(
    request: Request, body: OfferUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")

    offer = Offer(
        name=body.name.strip(),
        duration_minutes=body.duration_minutes,
        price_xof=body.price_xof,
        provider="paystack",
        station_id=None,
        is_active=bool(body.is_active),
    )
    db.add(offer)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    db.refresh(offer)
    return {
        "ok": True,
        "offer": {
            "id": offer.id,
            "name": offer.name,
            "duration_minutes": offer.duration_minutes,
            "price_xof": offer.price_xof,
            "provider": offer.provider,
            "is_active": offer.is_active,
        },
    }


@router.put("/admin/offers/{offer_id}")
def api_admin_update_offer(
    offer_id: int,
    request: Request,
    body: OfferUpsertBody,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")

    full_ops = m.has_platform_operations_scope(db, uid)
    if not full_ops:
        allowed_offer_ids = m.get_allowed_offer_ids_for_user(db, uid)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")

    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    offer.name = body.name.strip()
    offer.duration_minutes = body.duration_minutes
    offer.price_xof = body.price_xof
    offer.provider = "paystack"
    offer.station_id = None
    offer.is_active = bool(body.is_active)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return {
        "ok": True,
        "offer": {
            "id": offer.id,
            "name": offer.name,
            "duration_minutes": offer.duration_minutes,
            "price_xof": offer.price_xof,
            "provider": offer.provider,
            "is_active": offer.is_active,
        },
    }


@router.post("/admin/offers/{offer_id}/delete")
def api_admin_delete_offer(
    offer_id: int, request: Request, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")

    full_ops = m.has_platform_operations_scope(db, uid)
    if not full_ops:
        allowed_offer_ids = m.get_allowed_offer_ids_for_user(db, uid)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")

    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    # Soft delete identique au POST legacy :
    # - on supprime les liaisons StationOffer/SalleOffer
    # - on met is_active=False pour retirer l'offre des listes
    db.query(StationOffer).filter(StationOffer.offer_id == offer_id).delete()
    db.query(SalleOffer).filter(SalleOffer.offer_id == offer_id).delete()
    offer.is_active = False

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return {"ok": True}


class OfferOut(BaseModel):
    id: int
    name: str
    duration_minutes: int
    price_xof: int
    provider: str
    attached: bool


class SalleOffersOut(BaseModel):
    salle: dict[str, Any]
    offers: list[OfferOut]


class StationOffersOut(BaseModel):
    station: dict[str, Any]
    offers: list[OfferOut]


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


@router.get("/admin/stations/{station_id}/offers", response_model=StationOffersOut)
def api_admin_station_offers_get(
    station_id: int, request: Request, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    if not full_ops:
        if station.salle_id is None:
            raise HTTPException(status_code=403, detail="Accès refusé")
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if not allowed_salles or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    attached_offer_ids = {
        so.offer_id
        for so in db.query(StationOffer)
        .filter(StationOffer.station_id == station_id, StationOffer.is_active.is_(True))
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
        "station": {
            "id": station.id,
            "code": station.code,
            "name": station.name,
        },
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


@router.put("/admin/stations/{station_id}/offers")
def api_admin_station_offers_put(
    station_id: int,
    request: Request,
    body: SalleOffersUpdateBody,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    if not full_ops:
        if station.salle_id is None:
            raise HTTPException(status_code=403, detail="Accès refusé")
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if not allowed_salles or station.salle_id not in allowed_salles:
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

    db.query(StationOffer).filter(StationOffer.station_id == station_id).delete()
    for oid in active_ids:
        db.add(StationOffer(station_id=station_id, offer_id=oid, is_active=True))
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


@router.get("/admin/sessions")
def api_admin_sessions(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)
    if full_ops:
        sessions = (
            db.query(GameSession).order_by(GameSession.id.desc()).limit(100).all()
        )
    else:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if not allowed_salles:
            return {"sessions": []}
        sessions = (
            db.query(GameSession)
            .join(Station, Station.id == GameSession.station_id)
            .filter(Station.salle_id.in_(allowed_salles))
            .order_by(GameSession.id.desc())
            .limit(100)
            .all()
        )
    return {
        "sessions": [
            {
                "id": s.id,
                "payment_reference": s.payment_reference,
                "payment_provider": s.payment_provider,
                "payment_status": s.payment_status,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "end_at": s.end_at.isoformat() if s.end_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/admin/mes-utilisateurs")
def api_mes_utilisateurs(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.can_use_mes_utilisateurs_page(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")
    owned = (
        db.query(User)
        .filter(User.created_by_user_id == uid)
        .order_by(User.id.desc())
        .all()
    )
    return {
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "phone": u.phone,
                "is_active": u.is_active,
            }
            for u in owned
        ]
    }


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
        u.updated_at = datetime.utcnow()
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
        u.updated_at = datetime.utcnow()
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
    target.updated_at = datetime.utcnow()
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


@router.get("/admin/manual-session-options")
def api_admin_manual_session_options(request: Request, db: Session = Depends(get_db)):
    """Options station/offre pour la page « session manuelle » (même logique que l’ancien GET HTML)."""
    m = _lazy()
    user_id = m.get_authenticated_admin_user_id(request, db)
    if m.has_platform_operations_scope(db, user_id):
        stations = (
            db.query(Station)
            .filter(Station.is_active.is_(True))
            .order_by(Station.id)
            .all()
        )
    else:
        ids = m.get_allowed_station_ids(db, user_id)
        if not ids:
            return {
                "options": [],
                "empty": True,
                "hint_html": m.html_hint_no_stations_for_manual_session(db, user_id),
            }
        stations = (
            db.query(Station)
            .filter(Station.id.in_(ids), Station.is_active.is_(True))
            .order_by(Station.id)
            .all()
        )
    options: list[dict[str, str]] = []
    for st in stations:
        offer_rows = (
            db.query(Offer)
            .join(StationOffer, StationOffer.offer_id == Offer.id)
            .filter(
                StationOffer.station_id == st.id,
                StationOffer.is_active.is_(True),
                Offer.is_active.is_(True),
            )
            .order_by(Offer.duration_minutes)
            .all()
        )
        if st.salle_id is not None:
            salle_rows = (
                db.query(Offer)
                .join(SalleOffer, SalleOffer.offer_id == Offer.id)
                .filter(
                    SalleOffer.salle_id == st.salle_id,
                    SalleOffer.is_active.is_(True),
                    Offer.is_active.is_(True),
                )
                .order_by(Offer.duration_minutes)
                .all()
            )
            seen = {o.id for o in offer_rows}
            for o in salle_rows:
                if o.id not in seen:
                    offer_rows.append(o)
                    seen.add(o.id)
        for off in offer_rows:
            label = f"{st.code} — {off.name} ({off.duration_minutes} min)"
            options.append(
                {"value": f"{st.id}:{off.id}", "label": label}
            )
    if not options:
        return {
            "options": [],
            "empty": True,
            "hint_html": "<p>Aucune offre disponible sur vos stations.</p>",
        }
    return {"options": options, "empty": False, "hint_html": None}
