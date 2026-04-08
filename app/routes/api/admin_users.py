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



@router.get("/admin/feedback")
def api_admin_feedback(
    request: Request,
    status: str = Query("all", alias="status"),
    rating: int = Query(0, ge=0, le=5, alias="rating"),
    page: int = Query(1, ge=1, alias="page"),
    page_size: int = Query(20, ge=1, le=200, alias="page_size"),
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    q = db.query(FeedbackEntry)
    if not full_ops:
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if not allowed_salles:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        q = q.join(Station, Station.id == FeedbackEntry.station_id).filter(
            Station.salle_id.in_(allowed_salles)
        )

    status = (status or "all").strip().lower()
    if status != "all":
        q = q.filter(FeedbackEntry.status == status)
    if rating > 0:
        q = q.filter(FeedbackEntry.rating == rating)

    total = q.count()
    rows = (
        q.order_by(FeedbackEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    station_ids = [r.station_id for r in rows if r.station_id is not None]
    stations = {}
    if station_ids:
        stations = {
            s.id: s for s in db.query(Station).filter(Station.id.in_(station_ids)).all()
        }

    items = []
    for r in rows:
        st = stations.get(r.station_id) if r.station_id is not None else None
        items.append(
            {
                "id": r.id,
                "rating": r.rating,
                "category": r.category,
                "comment": r.comment,
                "contact_email": r.contact_email,
                "contact_phone": r.contact_phone,
                "status": r.status,
                "station_code": st.code if st else None,
                "session_id": r.session_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "handled_at": r.handled_at.isoformat() if r.handled_at else None,
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@router.put("/admin/feedback/{feedback_id}/status")
def api_admin_feedback_set_status(
    feedback_id: int,
    body: AdminFeedbackStatusBody,
    request: Request,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    full_ops = m.has_platform_operations_scope(db, uid)

    row = db.query(FeedbackEntry).filter(FeedbackEntry.id == feedback_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Feedback introuvable")

    if not full_ops:
        if row.station_id is None:
            raise HTTPException(status_code=403, detail="Accès refusé")
        st = db.query(Station).filter(Station.id == row.station_id).first()
        allowed_salles = m.get_scoped_salle_ids(db, uid)
        if not st or not allowed_salles or st.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    new_status = (body.status or "").strip().lower()
    if new_status not in {"new", "in_review", "resolved", "archived"}:
        raise HTTPException(status_code=400, detail="Statut invalide")
    row.status = new_status
    row.handled_by_user_id = uid
    row.handled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True}

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
