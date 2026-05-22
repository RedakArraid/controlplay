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
    ShopProduct,
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

@router.get("/public/shop-products")
def api_public_shop_products(db: Session = Depends(get_db)):
    products = (
        db.query(ShopProduct)
        .filter(ShopProduct.is_active.is_(True))
        .order_by(ShopProduct.sort_order.asc(), ShopProduct.id.asc())
        .all()
    )
    return {
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price_xof": p.price_xof,
                "provider": p.provider,
            }
            for p in products
        ]
    }


@router.get("/public/rental-catalog")
def api_public_rental_catalog(db: Session = Depends(get_db)):
    """Forfaits + consoles disponibles pour le tunnel location (SPA)."""
    plans = (
        db.query(RentalPlan)
        .filter(RentalPlan.is_active.is_(True))
        .order_by(RentalPlan.price_xof.asc(), RentalPlan.id.asc())
        .all()
    )
    consoles = (
        db.query(RentalConsole)
        .filter(RentalConsole.is_active.is_(True))
        .order_by(RentalConsole.code.asc())
        .all()
    )
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
            }
            for p in plans
        ],
        "consoles": [
            {"id": c.id, "code": c.code, "name": c.name} for c in consoles
        ],
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
        .filter(Station.is_active.is_(True), Station.usage_kind == "game_room")
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
                "usage_kind": st.usage_kind,
                "tv_size_inches": st.tv_size_inches,
                "console_model": st.console_model,
                "vr_headset_model": st.vr_headset_model,
                "controller_count": st.controller_count,
                "bundled_games": st.bundled_games,
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
    if st.usage_kind != "game_room":
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
    if st.controller_count is not None:
        composition.append(f"{st.controller_count} manette(s)")

    return {
        "station": {
            "id": st.id,
            "code": st.code,
            "name": st.name,
            "usage_kind": st.usage_kind,
            "salle_id": st.salle_id,
            "controller_count": st.controller_count,
            "bundled_games": st.bundled_games,
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

@router.post("/public/feedback")
def api_public_feedback_create(body: PublicFeedbackCreateBody, db: Session = Depends(get_db)):
    station = None
    session = None
    if body.session_reference and body.session_reference.strip():
        session = (
            db.query(GameSession)
            .filter(GameSession.payment_reference == body.session_reference.strip())
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session introuvable")
        station = db.query(Station).filter(Station.id == session.station_id).first()
    elif body.station_code and body.station_code.strip():
        station = (
            db.query(Station)
            .filter(Station.code == body.station_code.strip(), Station.is_active.is_(True))
            .first()
        )
        if not station:
            raise HTTPException(status_code=404, detail="Station introuvable")
    else:
        raise HTTPException(status_code=400, detail="station_code ou session_reference requis")

    category = (body.category or "general").strip().lower()
    if category not in {"general", "experience", "paiement", "materiel", "support"}:
        category = "general"

    fb = FeedbackEntry(
        station_id=station.id if station else None,
        session_id=session.id if session else None,
        rating=int(body.rating),
        category=category,
        comment=(body.comment or "").strip() or None,
        contact_email=(body.contact_email or "").strip() or None,
        contact_phone=(body.contact_phone or "").strip() or None,
        status="new",
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"ok": True, "feedback_id": fb.id}
