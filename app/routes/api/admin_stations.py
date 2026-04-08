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
from routes.api.common_models import OfferOut, StationOffersOut
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

    usage_kind, ip = _station_usage_broadlink(body)

    code = body.code.strip()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")
    if db.query(Station).filter(Station.code == code).first():
        raise HTTPException(status_code=400, detail="Code station deja utilise")

    bundled = (body.bundled_games or "").strip() or None
    st = Station(
        code=code,
        name=name,
        broadlink_ip=ip,
        usage_kind=usage_kind,
        salle_id=salle_id,
        tv_size_inches=body.tv_size_inches,
        console_model=(body.console_model.strip() if body.console_model else None),
        vr_headset_model=(body.vr_headset_model.strip() if body.vr_headset_model else None),
        controller_count=body.controller_count,
        bundled_games=bundled,
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
            "usage_kind": st.usage_kind,
            "tv_size_inches": st.tv_size_inches,
            "console_model": st.console_model,
            "vr_headset_model": st.vr_headset_model,
            "controller_count": st.controller_count,
            "bundled_games": st.bundled_games,
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

    usage_kind, ip = _station_usage_broadlink(body)

    code = body.code.strip()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")

    if (
        code != st.code
        and db.query(Station).filter(Station.code == code, Station.id != station_id).first()
    ):
        raise HTTPException(status_code=400, detail="Code station deja utilise")

    bundled = (body.bundled_games or "").strip() or None
    st.code = code
    st.name = name
    st.broadlink_ip = ip
    st.usage_kind = usage_kind
    st.salle_id = salle_id
    st.tv_size_inches = body.tv_size_inches
    st.console_model = (body.console_model.strip() if body.console_model else None)
    st.vr_headset_model = (
        body.vr_headset_model.strip() if body.vr_headset_model else None
    )
    st.controller_count = body.controller_count
    st.bundled_games = bundled
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
            "usage_kind": st.usage_kind,
            "tv_size_inches": st.tv_size_inches,
            "console_model": st.console_model,
            "vr_headset_model": st.vr_headset_model,
            "controller_count": st.controller_count,
            "bundled_games": st.bundled_games,
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
                "usage_kind": s.usage_kind,
                "tv_size_inches": s.tv_size_inches,
                "console_model": s.console_model,
                "vr_headset_model": s.vr_headset_model,
                "controller_count": s.controller_count,
                "bundled_games": s.bundled_games,
                "salle_code": salle_by_id.get(s.salle_id, ""),
                "is_active": s.is_active,
            }
            for s in stations
        ]
    }

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
