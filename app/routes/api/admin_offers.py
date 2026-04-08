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



@router.get("/public/rental-consoles")
def api_public_rental_consoles(db: Session = Depends(get_db)):
    consoles = (
        db.query(RentalConsole)
        .filter(RentalConsole.is_active.is_(True))
        .order_by(RentalConsole.code.asc())
        .all()
    )
    links = (
        db.query(RentalConsoleGame)
        .filter(RentalConsoleGame.rental_console_id.in_([c.id for c in consoles] or [-1]))
        .all()
    )
    game_ids = sorted({l.rental_game_id for l in links})
    games_by_id = {
        g.id: g
        for g in (
            db.query(RentalGame)
            .filter(RentalGame.id.in_(game_ids), RentalGame.is_active.is_(True))
            .all()
            if game_ids
            else []
        )
    }
    by_console: dict[int, list[dict[str, Any]]] = {}
    for l in links:
        g = games_by_id.get(l.rental_game_id)
        if not g:
            continue
        by_console.setdefault(l.rental_console_id, []).append(
            {"id": g.id, "name": g.name, "platform": g.platform}
        )
    return {
        "consoles": [
            {
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "tv_size_inches": c.tv_size_inches,
                "console_model": c.console_model,
                "controller_count": c.controller_count,
                "notes": c.notes,
                "games": sorted(by_console.get(c.id, []), key=lambda x: x["name"].lower()),
            }
            for c in consoles
        ]
    }

@router.get("/admin/dashboard/summary")
def api_dashboard_summary(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    paystack_flag = m.paystack_enabled()
    cinetpay_flag = m.cinetpay_enabled()

    # Uniquement les postes « salle de jeu » : pas les unités du parc location ControlPlay.
    stations_q = db.query(Station).filter(
        Station.is_active.is_(True),
        Station.usage_kind == "game_room",
    )
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

@router.get("/admin/rental-games")
def api_admin_rental_games(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(status_code=403, detail="Accès réservé à l'équipe plateforme")
    rows = db.query(RentalGame).order_by(RentalGame.name.asc()).all()
    return {
        "games": [
            {
                "id": g.id,
                "name": g.name,
                "genre": g.genre,
                "platform": g.platform,
                "is_active": g.is_active,
            }
            for g in rows
        ]
    }

@router.post("/admin/rental-games")
def api_admin_create_rental_game(
    request: Request, body: RentalGameUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(status_code=403, detail="Accès réservé à l'équipe plateforme")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")
    if db.query(RentalGame.id).filter(func.lower(RentalGame.name) == name.lower()).first():
        raise HTTPException(status_code=400, detail="Jeu déjà déclaré")
    row = RentalGame(
        name=name,
        genre=(body.genre or "").strip() or None,
        platform=(body.platform or "").strip() or None,
        is_active=bool(body.is_active),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}

@router.put("/admin/rental-games/{game_id}")
def api_admin_update_rental_game(
    game_id: int, request: Request, body: RentalGameUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(status_code=403, detail="Accès réservé à l'équipe plateforme")
    row = db.query(RentalGame).filter(RentalGame.id == game_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jeu introuvable")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")
    dup = (
        db.query(RentalGame.id)
        .filter(func.lower(RentalGame.name) == name.lower(), RentalGame.id != game_id)
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail="Jeu déjà déclaré")
    row.name = name
    row.genre = (body.genre or "").strip() or None
    row.platform = (body.platform or "").strip() or None
    row.is_active = bool(body.is_active)
    db.commit()
    return {"ok": True}

@router.get("/admin/rental-consoles")
def api_admin_rental_consoles(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(status_code=403, detail="Accès réservé à l'équipe plateforme")
    consoles = db.query(RentalConsole).order_by(RentalConsole.code.asc()).all()
    games = db.query(RentalGame).order_by(RentalGame.name.asc()).all()
    links = (
        db.query(RentalConsoleGame)
        .filter(RentalConsoleGame.rental_console_id.in_([c.id for c in consoles] or [-1]))
        .all()
    )
    by_station: dict[int, list[int]] = {}
    for l in links:
        by_station.setdefault(l.rental_console_id, []).append(l.rental_game_id)
    return {
        "consoles": [
            {
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "console_model": c.console_model,
                "controller_count": c.controller_count,
                "tv_size_inches": c.tv_size_inches,
                "notes": c.notes,
                "is_active": c.is_active,
                "game_ids": sorted(by_station.get(c.id, [])),
            }
            for c in consoles
        ],
        "games": [
            {"id": g.id, "name": g.name, "is_active": g.is_active}
            for g in games
        ],
    }

@router.post("/admin/rental-consoles")
def api_admin_create_rental_console(
    request: Request, body: RentalConsoleUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(status_code=403, detail="Accès réservé à l'équipe plateforme")
    code = body.code.strip()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")
    if db.query(RentalConsole.id).filter(RentalConsole.code == code).first():
        raise HTTPException(status_code=400, detail="Code console déjà utilisé")
    row = RentalConsole(
        code=code,
        name=name,
        tv_size_inches=body.tv_size_inches,
        console_model=(body.console_model or "").strip() or None,
        controller_count=body.controller_count,
        notes=(body.notes or "").strip() or None,
        is_active=bool(body.is_active),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}

@router.put("/admin/rental-consoles/{console_id}")
def api_admin_update_rental_console(
    console_id: int,
    request: Request,
    body: RentalConsoleUpsertBody,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(status_code=403, detail="Accès réservé à l'équipe plateforme")
    row = db.query(RentalConsole).filter(RentalConsole.id == console_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Console introuvable")
    code = body.code.strip()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")
    if (
        code != row.code
        and db.query(RentalConsole.id)
        .filter(RentalConsole.code == code, RentalConsole.id != console_id)
        .first()
    ):
        raise HTTPException(status_code=400, detail="Code console déjà utilisé")
    row.code = code
    row.name = name
    row.tv_size_inches = body.tv_size_inches
    row.console_model = (body.console_model or "").strip() or None
    row.controller_count = body.controller_count
    row.notes = (body.notes or "").strip() or None
    row.is_active = bool(body.is_active)
    db.commit()
    return {"ok": True}

@router.put("/admin/rental-consoles/{console_id}/games")
def api_admin_rental_console_games_update(
    console_id: int,
    request: Request,
    body: RentalConsoleGamesBody,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(status_code=403, detail="Accès réservé à l'équipe plateforme")
    rc = db.query(RentalConsole).filter(RentalConsole.id == console_id).first()
    if not rc:
        raise HTTPException(status_code=404, detail="Console location introuvable")
    ids = sorted({int(x) for x in body.game_ids if int(x) > 0})
    if ids:
        valid_n = db.query(RentalGame.id).filter(RentalGame.id.in_(ids)).count()
        if valid_n != len(ids):
            raise HTTPException(status_code=400, detail="Liste de jeux invalide")
    db.query(RentalConsoleGame).filter(RentalConsoleGame.rental_console_id == console_id).delete()
    for gid in ids:
        db.add(RentalConsoleGame(rental_console_id=console_id, rental_game_id=gid))
    db.commit()
    return {"ok": True, "game_ids": ids}

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
