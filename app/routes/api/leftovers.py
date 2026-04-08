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



# LEFTOVERS

@router.get("/admin/bootstrap")
def api_admin_bootstrap(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    super_a = m.is_global_super_admin(db, uid)
    staff_users = m.has_staff_users_access(db, uid)
    staff_ops = m.has_staff_operations_access(db, uid)
    staff_zone = m.can_use_super_admin_zone(db, uid)
    gerant_only = m.is_session_gerant_only(db, uid)
    full_ops = m.has_platform_operations_scope(db, uid)
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
            {"label": "Feedback", "to": "/admin/feedback"},
            {"label": "Dashboard stations", "to": "/admin/dashboard"},
        ]
        if full_ops:
            items[3:3] = [
                {"label": "Forfaits location", "to": "/admin/rental-plans"},
                {"label": "Consoles location", "to": "/admin/rental-consoles"},
                {"label": "Jeux location", "to": "/admin/rental-games"},
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
