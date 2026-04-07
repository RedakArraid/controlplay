import html as html_lib
import hashlib
import hmac
import io
import os
import re
import secrets
from pathlib import Path
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import uuid4

import bcrypt
import qrcode
import requests
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, func, or_
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import Base, engine, get_db, SessionLocal
from models import (
    EventLog,
    GameSession,
    Offer,
    PaymentProviderConfig,
    RentalOrder,
    RentalPlan,
    RentalConsole,
    Salle,
    Role,
    SalleUser,
    SessionExtension,
    Station,
    StationOffer,
    SalleOffer,
    User,
    UserRole,
    UserStaffPermission,
)
from tasks import activate_session, deactivate_session
from ui_theme import (
    THEME_SUPER_ADMIN,
    admin_page_response,
    html_shell,
    html_shell_login,
    public_page_html,
    super_admin_nav_html,
)


def _pub(title: str, inner_html: str) -> HTMLResponse:
    """Page publique (thème orange + sarcelle)."""
    return HTMLResponse(public_page_html(title, inner_html))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Seed au démarrage (remplace on_event startup, exécuté par le lifespan ASGI)."""
    seed_default_data()
    yield


app = FastAPI(title="ControlPlay", lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)

_spa_assets = Path(__file__).resolve().parent / "static" / "spa" / "assets"
if _spa_assets.is_dir():
    # Alias : anciens builds Vite (base « / ») référencent /assets/… ; le build actuel utilise /static/spa/assets/…
    app.mount(
        "/assets",
        StaticFiles(directory=str(_spa_assets)),
        name="spa_assets",
    )

from api_json import router as api_json_router  # noqa: E402

app.include_router(api_json_router, prefix="/api")

if os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true":
    Base.metadata.create_all(bind=engine)


@app.middleware("http")
async def redirect_if_admin_routes_without_session(request: Request, call_next):
    """Pages /admin et /super-admin : session obligatoire (sinon → /login)."""
    path = request.url.path
    if path.startswith("/admin") or path.startswith("/super-admin"):
        if path in ("/login", "/logout") or path.startswith("/login/"):
            return await call_next(request)
        if request.session.get("user_id") is None:
            dest = path
            if request.url.query:
                dest = f"{path}?{request.url.query}"
            return RedirectResponse(
                url=f"/login?next={quote(dest, safe='')}",
                status_code=303,
            )
    return await call_next(request)


# Dernier add_middleware = le plus externe : la session est disponible pour le middleware HTTP ci-dessus.
# Aligné avec la valeur d’exemple dans `.env.example` (à surcharger impérativement en prod).
_session_secret = os.getenv("APP_SECRET_KEY", "change-me-in-prod")
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    session_cookie="controlplay_session",
    max_age=60 * 60 * 24 * 14,  # 14 jours
    same_site="lax",
)


def log_event(db: Session, message: str, level: str = "info", station_id=None, session_id=None):
    db.add(
        EventLog(
            message=message,
            level=level,
            station_id=station_id,
            session_id=session_id,
        )
    )
    db.commit()


def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False


def is_global_salle_admin(db: Session, user_id: int) -> bool:
    """Rôle `salle_admin` global (user_roles) : accès /admin sans salle assignée au préalable."""
    return (
        db.query(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .filter(Role.key == "salle_admin")
        .first()
        is not None
    )


def user_can_access_admin(db: Session, user: User) -> bool:
    """True si le compte peut utiliser /admin : super_admin, admin équipe ControlPlay, salle_admin global, ou rôle sur une salle."""
    ga = (
        db.query(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == user.id)
        .filter(Role.key == "super_admin")
        .first()
    )
    if ga is not None:
        return True
    if is_global_platform_staff(db, user.id):
        return True
    if is_global_salle_admin(db, user.id):
        return True
    sa = (
        db.query(SalleUser)
        .join(Role, Role.id == SalleUser.role_id)
        .filter(SalleUser.user_id == user.id)
        .filter(Role.key.in_(("salle_admin", "manager", "responsable")))
        .first()
    )
    return sa is not None


def get_authenticated_admin_user_id(request: Request, db: Session) -> int:
    """Lit la session et vérifie que l'utilisateur a un rôle admin (global ou scopé)."""
    raw = request.session.get("user_id")
    if raw is None:
        raise HTTPException(status_code=401, detail="Non connecté")
    try:
        uid = int(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=401, detail="Session invalide") from e

    user = db.query(User).filter(User.id == uid, User.is_active.is_(True)).first()
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Utilisateur introuvable ou inactif")

    if not user_can_access_admin(db, user):
        raise HTTPException(status_code=403, detail="Accès administration refusé")
    return uid


def require_admin(request: Request, db: Session = Depends(get_db)) -> str:
    return str(get_authenticated_admin_user_id(request, db))


def require_super_admin(request: Request, db: Session = Depends(get_db)) -> str:
    uid = get_authenticated_admin_user_id(request, db)
    if not is_global_super_admin(db, uid):
        raise HTTPException(
            status_code=403, detail="Réservé au super administrateur"
        )
    return str(uid)


def require_super_zone_or_staff(request: Request, db: Session = Depends(get_db)) -> str:
    """Hub /super-admin (SPA) : super_admin ou admin équipe avec permission déléguée."""
    uid = get_authenticated_admin_user_id(request, db)
    if not can_use_super_admin_zone(db, uid):
        raise HTTPException(
            status_code=403,
            detail="Accès à l’espace super administrateur refusé (permissions insuffisantes).",
        )
    return str(uid)


def require_staff_users_or_super(request: Request, db: Session = Depends(get_db)) -> str:
    uid = get_authenticated_admin_user_id(request, db)
    if not (is_global_super_admin(db, uid) or has_staff_users_access(db, uid)):
        raise HTTPException(
            status_code=403,
            detail="Accès réservé à la gestion des comptes (super administrateur ou délégation).",
        )
    return str(uid)


def is_global_super_admin(db: Session, user_id: int) -> bool:
    """Seul le rôle global `super_admin` a accès plateforme entière (/super-admin, toutes salles)."""
    return (
        db.query(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .filter(Role.key == "super_admin")
        .first()
        is not None
    )


STAFF_PERM_OPERATIONS = "operations"
STAFF_PERM_USERS = "users"
_STAFF_PERM_KEYS: frozenset[str] = frozenset((STAFF_PERM_OPERATIONS, STAFF_PERM_USERS))


def is_global_platform_staff(db: Session, user_id: int) -> bool:
    """Rôle global `admin` : membre équipe ControlPlay (distinct du client `salle_admin`)."""
    return (
        db.query(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .filter(Role.key == "admin")
        .first()
        is not None
    )


def staff_permission_keys(db: Session, user_id: int) -> set[str]:
    """Permissions déléguées par le super_admin ; le super_admin a implicitement tout."""
    if is_global_super_admin(db, user_id):
        return set(_STAFF_PERM_KEYS)
    if not is_global_platform_staff(db, user_id):
        return set()
    rows = (
        db.query(UserStaffPermission.permission_key)
        .filter(UserStaffPermission.user_id == user_id)
        .all()
    )
    return {r[0] for r in rows if r[0] in _STAFF_PERM_KEYS}


def has_staff_operations_access(db: Session, user_id: int) -> bool:
    """Périmètre opérationnel (toutes salles/stations/offres) comme le super, hors PSP et hors gestion super_admins."""
    if is_global_super_admin(db, user_id):
        return True
    return STAFF_PERM_OPERATIONS in staff_permission_keys(db, user_id)


def has_platform_operations_scope(db: Session, user_id: int) -> bool:
    """Alias API : vue / actions sur toute la plateforme (super_admin ou délégation `operations`)."""
    return is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id)


def has_staff_users_access(db: Session, user_id: int) -> bool:
    """Gestion des comptes / rôles hors super_admin."""
    if is_global_super_admin(db, user_id):
        return True
    return STAFF_PERM_USERS in staff_permission_keys(db, user_id)


def can_use_super_admin_zone(db: Session, user_id: int) -> bool:
    """Accès au hub /super-admin (SPA) — sans les providers, réservés au super_admin."""
    if is_global_super_admin(db, user_id):
        return True
    if not is_global_platform_staff(db, user_id):
        return False
    return bool(staff_permission_keys(db, user_id))


def user_visible_to_salle_admin(
    db: Session, viewer_salle_admin_id: int, target: User, salle_id: int
) -> bool:
    """
    Un admin de salle voit un compte rattaché à cette salle si :
    - créé par lui-même,
    - sans créateur (NULL) — seed / import,
    - créé par un super-admin (assignation possible depuis l’espace super admin).
    """
    cb = target.created_by_user_id
    if cb is None:
        return True
    if cb == viewer_salle_admin_id:
        return True
    if is_global_super_admin(db, cb):
        return True
    return False


def get_scoped_salle_ids(db: Session, user_id: int) -> list[int]:
    """
    Salles autorisées à un admin scopé :
    - salle_admin, responsable : config (stations, offres, etc.)
    - manager (gérant seul) : uniquement pour les pages « sessions » / stations autorisées en lecture
    """

    rows = (
        db.query(SalleUser.salle_id)
        .join(Role, Role.id == SalleUser.role_id)
        .filter(SalleUser.user_id == user_id)
        .filter(Role.key.in_(("salle_admin", "manager", "responsable")))
        .all()
    )
    return [r[0] for r in rows]


def get_salle_admin_salle_ids(db: Session, user_id: int) -> list[int]:
    """Salles pour lesquelles l'utilisateur est explicitement `salle_admin` (CRUD salles)."""

    rows = (
        db.query(SalleUser.salle_id)
        .join(Role, Role.id == SalleUser.role_id)
        .filter(SalleUser.user_id == user_id)
        .filter(Role.key == "salle_admin")
        .all()
    )
    return [r[0] for r in rows]


def effective_salle_admin_salle_ids(db: Session, user_id: int) -> set[int]:
    """
    Salles où l’utilisateur a les pouvoirs « admin de salle » effectifs :
    - entrée `salle_users` en rôle `salle_admin`, et/ou
    - rôle global `salle_admin` (`user_roles`) + n’importe quel rôle scopé sur la même salle
      (évite un trou de droits si seul `responsable` ou co-assignation partielle).
    """
    ids = set(get_salle_admin_salle_ids(db, user_id))
    if is_global_salle_admin(db, user_id):
        ids |= set(get_scoped_salle_ids(db, user_id))
    return ids


def is_effective_salle_admin_for_salle(db: Session, user_id: int, salle_id: int) -> bool:
    """Peut gérer la fiche salle, nommer des responsables, etc. (hors super admin global)."""
    if is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id):
        return True
    return salle_id in effective_salle_admin_salle_ids(db, user_id)


def html_hint_empty_scoped_salles(db: Session, user_id: int) -> str:
    """Message quand `get_scoped_salle_ids` est vide (dashboard, offres, stations, sessions…)."""
    if is_global_salle_admin(db, user_id):
        return (
            "<p><strong>Périmètre vide.</strong> Vous avez le rôle <em>admin de salle (global)</em> : "
            "créez d’abord une <a href='/admin/salles'>salle</a>, puis des stations et offres ; "
            "créez les comptes gérants/responsables dans <a href='/admin/mes-utilisateurs'>Mes utilisateurs</a>.</p>"
        )
    if is_session_gerant_only(db, user_id):
        return (
            "<p><strong>Aucune salle liée à votre compte gérant.</strong> "
            "Demandez à un administrateur de vous rattacher à une salle.</p>"
        )
    return (
        "<p><strong>Aucune salle</strong> ne correspond à vos rôles. "
        "Contactez le super administrateur si vous attendiez un accès.</p>"
    )


def html_hint_no_stations_for_manual_session(db: Session, user_id: int) -> str:
    if is_global_salle_admin(db, user_id):
        return (
            "<p>Aucune station disponible. Créez une <a href='/admin/salles'>salle</a>, "
            "puis des <a href='/admin/stations'>stations</a> et rattachez des offres.</p>"
        )
    if is_session_gerant_only(db, user_id):
        return "<p>Aucune station dans votre périmètre gérant.</p>"
    return "<p>Aucune station autorisée pour votre compte.</p>"


def _user_ids_created_by_salle_admin(db: Session, viewer_id: int) -> set[int]:
    """Comptes créés par cet admin de salle (pour assignation gérant / responsable)."""
    return {
        r[0]
        for r in db.query(User.id).filter(User.created_by_user_id == viewer_id).all()
    }


def _user_ids_allowed_for_manager_responsable_form(
    db: Session, viewer_id: int, salle_id: int, *, super_admin: bool
) -> set[int] | None:
    """
    IDs autorisés dans les cases gérant/responsable d’une salle.
    None = tous (super admin). Sinon : comptes créés par le viewer + déjà gérant/responsable sur cette salle.
    """
    if super_admin:
        return None
    allowed = _user_ids_created_by_salle_admin(db, viewer_id)
    mgr = db.query(Role).filter(Role.key == "manager").first()
    resp = db.query(Role).filter(Role.key == "responsable").first()
    role_ids = [rid for rid in (mgr.id if mgr else None, resp.id if resp else None) if rid is not None]
    if role_ids:
        for (uid,) in (
            db.query(SalleUser.user_id)
            .filter(SalleUser.salle_id == salle_id, SalleUser.role_id.in_(role_ids))
            .distinct()
            .all()
        ):
            allowed.add(uid)
    return allowed


def _filter_manager_responsable_ids(
    db: Session,
    viewer_id: int,
    salle_id: int,
    manager_ids: list[int],
    responsable_ids: list[int],
    *,
    super_admin: bool,
) -> tuple[list[int], list[int]]:
    allowed = _user_ids_allowed_for_manager_responsable_form(
        db, viewer_id, salle_id, super_admin=super_admin
    )
    if allowed is None:
        return manager_ids, responsable_ids
    return (
        [i for i in manager_ids if i in allowed],
        [i for i in responsable_ids if i in allowed],
    )


def _salle_admin_may_use_existing_user_for_assignment(
    db: Session, viewer_id: int, target: User
) -> bool:
    """Hors super-admin : n’assigner que des comptes créés par le viewer, sans créateur (legacy), ou par le super admin."""
    cb = target.created_by_user_id
    if cb is None:
        return True
    if cb == viewer_id:
        return True
    return is_global_super_admin(db, cb)


def can_use_mes_utilisateurs_page(db: Session, user_id: int) -> bool:
    """Lien « Mes utilisateurs » : admins de salle (hors super admin global)."""
    if is_global_super_admin(db, user_id):
        return False
    return is_global_salle_admin(db, user_id) or bool(get_salle_admin_salle_ids(db, user_id))


def user_salle_role_keys(db: Session, user_id: int) -> set[str]:
    rows = (
        db.query(Role.key)
        .join(SalleUser, SalleUser.role_id == Role.id)
        .filter(SalleUser.user_id == user_id)
        .all()
    )
    return {r[0] for r in rows}


def is_session_gerant_only(db: Session, user_id: int) -> bool:
    """
    Gérant seul : au moins un rôle `manager`, et aucun `salle_admin` ni `responsable`.
    Ce profil n'accède qu'aux actions de session (démarrer, pause, durée).
    """
    if is_global_super_admin(db, user_id):
        return False
    if is_global_salle_admin(db, user_id):
        return False
    keys = user_salle_role_keys(db, user_id)
    if not keys:
        return False
    if "salle_admin" in keys or "responsable" in keys:
        return False
    return "manager" in keys


def require_config_admin(request: Request, db: Session = Depends(get_db)) -> str:
    """Comme require_admin mais refuse le gérant seul (pas de config offres/stations/salles)."""
    uid = get_authenticated_admin_user_id(request, db)
    if is_session_gerant_only(db, uid):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : compte gérant — utilise « Sessions » et « Démarrer une session ».",
        )
    return str(uid)


def session_station_allowed_for_user(
    db: Session, user_id: int, station_id: int | None
) -> bool:
    if not station_id:
        return False
    if is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id):
        return True
    allowed = get_allowed_station_ids(db, user_id)
    return station_id in allowed


def get_allowed_station_ids(db: Session, user_id: int) -> list[int]:
    """
    Stations autorisées pour un admin scopé :
    - station dans une salle autorisée
    """

    if is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id):
        rows = db.query(Station.id).all()
        return [r[0] for r in rows]

    allowed_salles = get_scoped_salle_ids(db, user_id)
    if not allowed_salles:
        return []
    rows = db.query(Station.id).filter(Station.salle_id.in_(allowed_salles)).all()
    return [r[0] for r in rows]


def get_allowed_offer_ids_for_user(db: Session, user_id: int) -> set[int]:
    """Offres autorisées à un admin scopé : attachées via salle_offers/station_offers à ses salles."""
    if is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id):
        rows = db.query(Offer.id).filter(Offer.is_active.is_(True)).all()
        return {r[0] for r in rows}

    allowed_salles = get_scoped_salle_ids(db, user_id)
    allowed_stations = get_allowed_station_ids(db, user_id)
    if not allowed_salles or not allowed_stations:
        return set()

    offer_ids_station = (
        db.query(StationOffer.offer_id)
        .filter(StationOffer.is_active.is_(True))
        .filter(StationOffer.station_id.in_(allowed_stations))
        .all()
    )
    offer_ids_salle = (
        db.query(SalleOffer.offer_id)
        .filter(SalleOffer.is_active.is_(True))
        .filter(SalleOffer.salle_id.in_(allowed_salles))
        .all()
    )
    return {r[0] for r in (offer_ids_station + offer_ids_salle)}


DEFAULT_USER_EMAIL = "default_user@controlplay.local"
DEFAULT_PAYSTACK_EMAIL_DOMAIN = "example.com"


def get_paystack_email(customer_email: str | None, customer_phone: str | None) -> str:
    """
    Paystack exige un email pour l'initialisation.
    Côté UI, l'email reste optionnel : on envoie donc un placeholder si absent.
    """

    if customer_email and customer_email.strip():
        return customer_email.strip()

    if customer_phone and customer_phone.strip():
        # On ne garde que les chiffres pour que ce soit un local-part email robuste.
        local_part = re.sub(r"\D+", "", customer_phone.strip())
        if local_part:
            return f"{local_part}@{DEFAULT_PAYSTACK_EMAIL_DOMAIN}"

    return f"default_user@{DEFAULT_PAYSTACK_EMAIL_DOMAIN}"


def get_default_user(db: Session) -> User:
    user = db.query(User).filter(User.email == DEFAULT_USER_EMAIL).first()
    if user:
        return user

    # Guest user (invité) : on force un email fixe car le schéma impose (email ou phone) != NULL.
    user = User(
        name="default_user",
        email=DEFAULT_USER_EMAIL,
        phone=None,
        avatar=None,
        password_hash=hash_password(secrets.token_urlsafe(24)),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_user_by_phone(db: Session, phone: str, email: str | None) -> User:
    phone_v = phone.strip()
    email_v = (email or "").strip() or None

    user = db.query(User).filter(User.phone == phone_v).first()
    if user:
        # Optionnel : on complète l'email si l'utilisateur l'a fourni pour la première fois.
        if email_v and not user.email:
            user.email = email_v
            db.commit()
        return user

    # On crée un user “identifié” par son téléphone. (Mot de passe non utilisé pour l'instant côté client.)
    user = User(
        name=f"User {phone_v}",
        email=email_v,
        phone=phone_v,
        avatar=None,
        password_hash=hash_password(secrets.token_urlsafe(24)),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Si le rôle “joueur” existe, on l'assigne (sinon on ignore).
    joueur_role = db.query(Role).filter(Role.key == "joueur").first()
    if joueur_role:
        db.add(UserRole(user_id=user.id, role_id=joueur_role.id))
        db.commit()

    return user


def verify_paystack_transaction(reference: str) -> bool:
    secret_key = os.getenv("PAYSTACK_SECRET_KEY", "")
    if not secret_key or "xxx" in secret_key:
        return False
    try:
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})
        return bool(payload.get("status")) and data.get("status") == "success"
    except requests.RequestException:
        return False


def verify_cinetpay_transaction(reference: str) -> bool:
    api_key = os.getenv("CINETPAY_API_KEY", "")
    site_id = os.getenv("CINETPAY_SITE_ID", "")
    if not api_key or not site_id or "xxx" in api_key:
        return False
    try:
        response = requests.post(
            "https://api-checkout.cinetpay.com/v2/payment/check",
            json={"apikey": api_key, "site_id": site_id, "transaction_id": reference},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})
        return str(data.get("status", "")).upper() == "ACCEPTED"
    except requests.RequestException:
        return False


def verify_transaction(provider: str, reference: str) -> bool:
    if provider == "paystack":
        return verify_paystack_transaction(reference)
    if provider == "cinetpay":
        return verify_cinetpay_transaction(reference)
    return False


def get_payment_provider_config() -> PaymentProviderConfig | None:
    """
    Lit les flags d'activation des providers.
    Utilisé par les helpers sans dépendance DB directe.
    """
    db = SessionLocal()
    try:
        return db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    finally:
        db.close()


def paystack_enabled() -> bool:
    cfg = get_payment_provider_config()
    return cfg.paystack_enabled if cfg else True


def cinetpay_enabled() -> bool:
    cfg = get_payment_provider_config()
    return cfg.cinetpay_enabled if cfg else True


def is_paystack_api_configured() -> bool:
    """Clé secrète suffisante pour /transaction/initialize et /transaction/verify."""
    if not paystack_enabled():
        return False
    secret = os.getenv("PAYSTACK_SECRET_KEY", "")
    return bool(secret) and "xxx" not in secret.lower()


def is_paystack_webhook_secret_configured() -> bool:
    """Secret du dashboard Paystack pour valider x-paystack-signature (recommandé en prod)."""
    if not paystack_enabled():
        return False
    wh = os.getenv("PAYSTACK_WEBHOOK_SECRET", "")
    return bool(wh) and "xxx" not in wh.lower()


def is_paystack_configured() -> bool:
    """Alias rétro-compat : paiement Paystack possible dès que la clé API est présente."""
    return is_paystack_api_configured()


def is_cinetpay_configured() -> bool:
    api_key = os.getenv("CINETPAY_API_KEY", "")
    site_id = os.getenv("CINETPAY_SITE_ID", "")
    if not cinetpay_enabled():
        return False
    return bool(api_key) and bool(site_id) and "xxx" not in api_key and "xxx" not in site_id


def is_cinetpay_webhook_secret_configured() -> bool:
    """Secret (CINETPAY_SECRET_KEY) pour valider le header `x-token` du webhook."""
    if not cinetpay_enabled():
        return False
    secret = os.getenv("CINETPAY_SECRET_KEY", "")
    return bool(secret) and "xxx" not in secret.lower()


def make_payment_reference(provider: str) -> str:
    """
    Référence utilisée pour retrouver la transaction dans les webhooks.
    - Paystack: Paystack refuse certains caractères (ex: `_`), on utilise `ps-<hex>`.
    - CinetPay: on évite `_` et autres caractères spéciaux, on utilise `cp<hex>`.
    """
    base = uuid4().hex[:18]
    if provider == "cinetpay":
        return f"cp{base}"
    # Paystack refuse certains caractères (ex: `_`), on utilise donc un format
    # alphanumérique avec tirets autorisés.
    return f"ps-{base}"


def get_base_url() -> str:
    return os.getenv("BASE_URL", "http://localhost:8000")


def paystack_amount_units(amount_main: int) -> int:
    """
    Montant envoyé à Paystack (integer).
    - XOF / franc CFA : Paystack semble attendre des sous-unités (centimes), soit ×100.
      Défaut multiplier = 100.
    - NGN (kobo) : mettre PAYSTACK_AMOUNT_MULTIPLIER=100 dans l'env.
    """
    mult = int(os.getenv("PAYSTACK_AMOUNT_MULTIPLIER", "100"))
    return int(amount_main) * mult


def init_paystack_payment(reference: str, email: str | None, amount_xof: int, callback_url: str | None = None) -> str:
    """
    Initialise un paiement Paystack et renvoie l'URL d'autorisation.
    """
    if not is_paystack_api_configured():
        raise RuntimeError("Paystack non configuré (PAYSTACK_SECRET_KEY)")
    secret_key = os.getenv("PAYSTACK_SECRET_KEY", "")
    if callback_url is None:
        callback_url = f"{get_base_url()}/payments/return/paystack/{reference}"
    currency = os.getenv("PAYSTACK_CURRENCY", "XOF")
    payload = {
        "amount": paystack_amount_units(amount_xof),
        "reference": reference,
        "currency": currency,
        "callback_url": callback_url,
    }
    # Paystack exige un email pour l'initialisation : on l'alimente côté backend
    # (UI peut rester optionnelle, on génère un placeholder si nécessaire).
    if email:
        payload["email"] = email
    response = requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers={"Authorization": f"Bearer {secret_key}"},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    authorization_url = (data.get("data") or {}).get("authorization_url")
    if not data.get("status") or not authorization_url:
        raise RuntimeError(f"Paystack init invalide: {data}")
    return authorization_url


def init_cinetpay_payment(transaction_id: str, amount_xof: int, description: str) -> str:
    """
    Initialise un paiement CinetPay et renvoie l'URL de checkout.
    """
    if not is_cinetpay_configured():
        raise RuntimeError("CinetPay non configuré")
    api_key = os.getenv("CINETPAY_API_KEY", "")
    site_id = os.getenv("CINETPAY_SITE_ID", "")
    if amount_xof % 5 != 0:
        raise RuntimeError("Le montant CinetPay doit être un multiple de 5")

    notify_url = f"{get_base_url()}/webhooks/cinetpay"
    return_url = f"{get_base_url()}/payments/return/cinetpay"
    payload = {
        "apikey": api_key,
        "site_id": site_id,
        "transaction_id": transaction_id,
        "amount": int(amount_xof),
        "currency": "XOF",
        "description": description,
        "notify_url": notify_url,
        "return_url": return_url,
        "channels": "ALL",
    }
    response = requests.post(
        "https://api-checkout.cinetpay.com/v2/payment",
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    payment_url = (data.get("data") or {}).get("payment_url")
    if not data.get("code") or not payment_url:
        raise RuntimeError(f"CinetPay init invalide: {data}")
    return payment_url


def get_equivalent_offer(db: Session, station_id: int, base_offer: Offer, provider: str) -> Offer | None:
    """
    Trouve l'offre équivalente pour un fallback Paystack/CinetPay sur une station:
    - même durée/prix
    - même provider souhaité
    - liée soit directement à la station, soit (si la station a une salle) à la salle.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        return None

    # 1) Priorité: offre rattachée directement à la station
    station_offer = (
        db.query(Offer)
        .join(StationOffer, StationOffer.offer_id == Offer.id)
        .filter(
            Offer.is_active.is_(True),
            Offer.provider == provider,
            Offer.duration_minutes == base_offer.duration_minutes,
            Offer.price_xof == base_offer.price_xof,
            StationOffer.station_id == station_id,
            StationOffer.is_active.is_(True),
        )
        .first()
    )
    if station_offer:
        return station_offer

    # 2) Sinon: offre rattachée à la salle de la station
    if station.salle_id is not None:
        salle_offer = (
            db.query(Offer)
            .join(SalleOffer, SalleOffer.offer_id == Offer.id)
            .filter(
                Offer.is_active.is_(True),
                Offer.provider == provider,
                Offer.duration_minutes == base_offer.duration_minutes,
                Offer.price_xof == base_offer.price_xof,
                SalleOffer.salle_id == station.salle_id,
                SalleOffer.is_active.is_(True),
            )
            .first()
        )
        if salle_offer:
            return salle_offer

    return None


def get_active_session_by_station(db: Session, station_id: int) -> GameSession | None:
    return (
        db.query(GameSession)
        .filter(GameSession.station_id == station_id, GameSession.status == "active")
        .first()
    )


def extend_session_end_at(db: Session, session: GameSession, extra_minutes: int, source: str) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    # Si une extension est demandée alors que end_at est déjà passé (edge case),
    # on base le nouveau end_at sur maintenant.
    base_end = session.end_at if session.end_at and session.end_at > now else now
    session.end_at = base_end + timedelta(minutes=extra_minutes)
    db.add(session)
    db.commit()
    remaining_s = max(0, int((session.end_at - now).total_seconds()))
    deactivate_session.apply_async(args=[session.id], countdown=remaining_s)
    log_event(
        db,
        f"Extension de session {session.id}: +{extra_minutes} minutes (source={source}).",
        level="info",
        station_id=session.station_id,
        session_id=session.id,
    )


def apply_paid_extension(db: Session, extension: SessionExtension, source: str, trusted: bool = False) -> bool:
    lock_for_update = db.get_bind().dialect.name == "postgresql"

    # Recharger l'extension sous verrou (idempotence en concurrence)
    ext_q = db.query(SessionExtension).filter(SessionExtension.id == extension.id)
    if lock_for_update:
        ext_q = ext_q.with_for_update()
    extension_db = ext_q.first()

    if not extension_db or extension_db.status == "applied" or extension_db.payment_status == "paid":
        return False

    if not trusted and not verify_transaction(extension_db.payment_provider, extension_db.payment_reference):
        extension_db.payment_status = "failed"
        extension_db.status = "failed"
        db.commit()
        log_event(
            db,
            f"Vérification paiement extension échouée ({source}) ref={extension_db.payment_reference}.",
            level="warning",
            station_id=extension_db.session_id,
            session_id=extension_db.session_id,
        )
        return False

    # Verrouiller la session active avant application
    session_q = db.query(GameSession).filter(GameSession.id == extension_db.session_id)
    if lock_for_update:
        session_q = session_q.with_for_update()
    session = session_q.first()
    if not session or session.status != "active":
        extension_db.payment_status = "failed"
        extension_db.status = "failed"
        db.commit()
        return False

    try:
        extension_db.payment_status = "paid"
        extension_db.status = "applied"
        extend_session_end_at(db, session, extension_db.extra_minutes, source=source)
        return True
    except IntegrityError:
        db.rollback()
        extension_db.payment_status = "failed"
        extension_db.status = "failed"
        db.commit()
        return False


def activate_paid_session(db: Session, session: GameSession, source: str, trusted: bool = False) -> bool:
    lock_for_update = db.get_bind().dialect.name == "postgresql"

    # Recharger la session sous verrou (idempotence concurrence)
    sess_q = db.query(GameSession).filter(GameSession.id == session.id)
    if lock_for_update:
        sess_q = sess_q.with_for_update()
    session_db = sess_q.first()

    if not session_db or session_db.status != "pending" or session_db.payment_status == "paid":
        return False

    if not trusted and not verify_transaction(session_db.payment_provider, session_db.payment_reference):
        session_db.payment_status = "failed"
        session_db.status = "failed"
        db.commit()
        log_event(
            db,
            f"Verification transaction echouee ({source}) pour {session_db.payment_reference}",
            level="warning",
            station_id=session_db.station_id,
            session_id=session_db.id,
        )
        return False

    # Vérifier la station occupée sous verrou si possible
    active_q = db.query(GameSession).filter(
        and_(
            GameSession.station_id == session_db.station_id,
            GameSession.id != session_db.id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
    )
    if lock_for_update:
        active_q = active_q.with_for_update()
    active_station_session = active_q.first()

    if active_station_session:
        log_event(
            db,
            f"Paiement recu ({source}) mais station occupee pour {session_db.payment_reference}",
            level="warning",
            station_id=session_db.station_id,
            session_id=session_db.id,
        )
        return False

    session_db.payment_status = "paid"
    try:
        db.commit()
    except IntegrityError:
        # Contrainte DB: une autre session pending/active occupe déjà la station.
        db.rollback()
        session_db.payment_status = "failed"
        session_db.status = "failed"
        db.commit()
        log_event(
            db,
            f"Activation/paymark refusé ({source}) - station déjà occupée (contrainte DB).",
            level="warning",
            station_id=session_db.station_id,
            session_id=session_db.id,
        )
        return False

    activate_session.delay(session_db.id)
    log_event(
        db,
        f"Paiement valide ({source}) pour {session_db.payment_reference}; activation programmee.",
        station_id=session_db.station_id,
        session_id=session_db.id,
    )
    return True


def activate_paid_rental(
    db: Session, order: RentalOrder, source: str, trusted: bool = False
) -> bool:
    """Marque une commande de location validée (sans session TV / worker)."""
    order_db = db.query(RentalOrder).filter(RentalOrder.id == order.id).first()
    if not order_db or order_db.status != "pending" or order_db.payment_status == "paid":
        return False
    if not trusted and not verify_transaction(
        order_db.payment_provider, order_db.payment_reference
    ):
        order_db.payment_status = "failed"
        order_db.status = "failed"
        db.commit()
        log_event(
            db,
            f"Location: verification transaction echouee ({source}) pour {order_db.payment_reference}",
            level="warning",
        )
        return False
    order_db.payment_status = "paid"
    order_db.status = "paid"
    db.commit()
    log_event(
        db,
        f"Location payée ({source}) ref={order_db.payment_reference}",
    )
    return True


def _should_auto_ensure_dev_admin() -> bool:
    """Synchronise le compte dev documenté au démarrage (Docker local, pytest)."""
    v = os.getenv("AUTO_ENSURE_DEV_ADMIN", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return os.getenv("APP_ENV", "development").strip().lower() in (
        "development",
        "dev",
        "",
    )


def seed_default_data() -> None:
    db = next(get_db())
    try:
        if db.query(Salle).count() == 0:
            db.add(Salle(code="salle-1", name="Salle 1"))
            db.commit()

        if db.query(Station).count() == 0:
            salle = db.query(Salle).filter(Salle.code == "salle-1").first()
            station = Station(
                code="station-1",
                name="Station 1",
                broadlink_ip=os.getenv("BROADLINK_IP", "192.168.1.250"),
                ir_code_hdmi1=os.getenv("IR_CODE_HDMI1", "hdmi1_code_placeholder"),
                ir_code_hdmi2=os.getenv("IR_CODE_HDMI2", "hdmi2_code_placeholder"),
                salle_id=salle.id if salle else None,
            )
            db.add(station)
            db.commit()

        if db.query(RentalConsole.id).filter(RentalConsole.is_active.is_(True)).first() is None:
            db.add(
                RentalConsole(
                    code="rental-console-1",
                    name="Console location 1",
                    console_model="PS5",
                    controller_count=2,
                    tv_size_inches=55,
                    is_active=True,
                )
            )
            db.commit()

        # Offres globales: on s'assure que les 2 providers existent par défaut (paystack prioritaire).
        # Si la DB a déjà des offres, on ne duplique pas inutilement.
        global_offers = [
            ("30 minutes", 30, 1000),
            ("60 minutes", 60, 1800),
        ]
        for name, duration, price in global_offers:
            provider = "paystack"
            exists = (
                db.query(Offer)
                .filter(
                    and_(
                        Offer.station_id.is_(None),
                        Offer.duration_minutes == duration,
                        Offer.price_xof == price,
                        Offer.provider == provider,
                    )
                )
                .first()
            )
            if not exists:
                db.add(
                    Offer(
                        name=name,
                        duration_minutes=duration,
                        price_xof=price,
                        provider=provider,
                        station_id=None,
                        is_active=True,
                    )
                )

        # Après avoir créé les offres "templates" (station_id=NULL),
        # on les rattache par défaut à toutes les salles existantes.
        # (Sur une DB neuve, la migration 0007 n'a pas encore ces offres à mapper.)
        global_offer_rows = (
            db.query(Offer)
            .filter(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True))
            .all()
        )
        salles = db.query(Salle).all()
        stations_no_salle = (
            db.query(Station)
            .filter(Station.salle_id.is_(None), Station.usage_kind == "game_room")
            .all()
        )

        for sl in salles:
            for go in global_offer_rows:
                exists = (
                    db.query(SalleOffer)
                    .filter(SalleOffer.salle_id == sl.id, SalleOffer.offer_id == go.id)
                    .first()
                )
                if not exists:
                    db.add(SalleOffer(salle_id=sl.id, offer_id=go.id, is_active=True))

        for st in stations_no_salle:
            for go in global_offer_rows:
                exists = (
                    db.query(StationOffer)
                    .filter(StationOffer.station_id == st.id, StationOffer.offer_id == go.id)
                    .first()
                )
                if not exists:
                    db.add(StationOffer(station_id=st.id, offer_id=go.id, is_active=True))

        # Forfaits location console (paiement séparé, hors table `offers`)
        if db.query(RentalPlan).count() == 0:
            db.add(
                RentalPlan(
                    name="Location console — 1 jour",
                    description="Retrait au comptoir de la salle choisie. Tarif indépendant du temps de jeu.",
                    duration_label="24 h",
                    price_xof=5000,
                    provider="paystack",
                    rental_console_id=None,
                    is_active=True,
                )
            )
            db.add(
                RentalPlan(
                    name="Location console — week-end",
                    description="Ven–dim selon disponibilité du lieu.",
                    duration_label="Week-end",
                    price_xof=15000,
                    provider="paystack",
                    rental_console_id=None,
                    is_active=True,
                )
            )

        # --- Auth / RBAC seed (users/roles) ---
        # On seed des roles minimaux + un admin global de bootstrap.
        role_seed = [
            ("super_admin", "Super admin (global)"),
            ("admin", "Équipe ControlPlay (délégation super_admin — hors client salle_admin)"),
            ("salle_admin", "Admin de salle (client, scopé)"),
            ("manager", "Gérant"),
            ("responsable", "Responsable"),
            ("joueur", "Joueur"),
        ]
        for key, name in role_seed:
            if not db.query(Role).filter(Role.key == key).first():
                db.add(Role(key=key, name=name))

        super_admin_role = db.query(Role).filter(Role.key == "super_admin").first()

        if super_admin_role:
            admin_exists = (
                db.query(UserRole)
                .filter(UserRole.role_id == super_admin_role.id)
                .first()
            )
            if not admin_exists:
                admin_identifier = os.getenv("ADMIN_USERNAME", "admin").strip()
                admin_password = os.getenv("ADMIN_PASSWORD", "change-me")

                if admin_password:
                    existing_user = (
                        db.query(User)
                        .filter(or_(User.email == admin_identifier, User.phone == admin_identifier))
                        .first()
                    )

                    if not existing_user:
                        if "@" in admin_identifier:
                            existing_user = User(
                                name="Admin",
                                email=admin_identifier,
                                phone=None,
                                avatar=None,
                                password_hash=hash_password(admin_password),
                                is_active=True,
                            )
                        else:
                            existing_user = User(
                                name="Admin",
                                email=None,
                                phone=admin_identifier,
                                avatar=None,
                                password_hash=hash_password(admin_password),
                                is_active=True,
                            )
                        db.add(existing_user)
                        db.flush()

                    # Ne pas re-promouvoir en super_admin un compte déjà configuré
                    # uniquement comme `salle_admin` (ex: après migration manuelle des rôles).
                    salle_admin_role_check = (
                        db.query(Role).filter(Role.key == "salle_admin").first()
                    )
                    has_salle_admin_only_bootstrap = False
                    if existing_user and salle_admin_role_check:
                        has_global_salle_admin = (
                            db.query(UserRole)
                            .filter(
                                UserRole.user_id == existing_user.id,
                                UserRole.role_id == salle_admin_role_check.id,
                            )
                            .first()
                            is not None
                        )
                        has_salle_admin_only_bootstrap = has_global_salle_admin or (
                            db.query(SalleUser)
                            .filter(
                                SalleUser.user_id == existing_user.id,
                                SalleUser.role_id == salle_admin_role_check.id,
                            )
                            .first()
                            is not None
                        )

                    if not has_salle_admin_only_bootstrap:
                        if super_admin_role:
                            db.add(
                                UserRole(
                                    user_id=existing_user.id,
                                    role_id=super_admin_role.id,
                                )
                            )

        # Dev : garantir admin@test.com + rôles (mot de passe aligné tests / make ensure-dev-admin).
        # Désactivé en prod par défaut (APP_ENV=production) ou AUTO_ENSURE_DEV_ADMIN=false.
        if _should_auto_ensure_dev_admin():
            try:
                from ensure_dev_admin import apply_dev_admin_to_db

                apply_dev_admin_to_db(db)
            except Exception as e:
                import logging

                logging.getLogger("controlplay").warning(
                    "AUTO_ENSURE_DEV_ADMIN: %s", e, exc_info=True
                )

        db.commit()
    finally:
        db.close()


def _login_next_safe(raw: str) -> str:
    """Paramètre next : chemin interne uniquement (pas d'open redirect)."""
    u = (raw or "/admin").strip() or "/admin"
    if not u.startswith("/") or u.startswith("//"):
        return "/admin"
    return u


def _login_identifier_variants(identifier: str) -> list[str]:
    """Email : une seule forme. Téléphone : +225… / 225… / espaces."""
    s = identifier.strip()
    if not s:
        return []
    if "@" in s:
        return [s]
    digits = re.sub(r"\D+", "", s)
    variants = [s]
    if digits:
        for alt in (digits, f"+{digits}"):
            if alt != s and alt not in variants:
                variants.append(alt)
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _find_user_for_login(db: Session, identifier: str) -> User | None:
    for v in _login_identifier_variants(identifier):
        u = (
            db.query(User)
            .filter(User.is_active.is_(True))
            .filter(or_(User.email == v, User.phone == v))
            .first()
        )
        if u:
            return u
    return None


def _html_login_page(next_internal: str, *, error: str | None = None) -> str:
    """Page de connexion administration (thème orange + sarcelle, carte centrée)."""
    nxt_esc = html_lib.escape(next_internal, quote=True)
    err_html = ""
    if error:
        err_html = (
            '<div class="cp-alert" role="alert">'
            f"{html_lib.escape(error)}"
            "</div>"
        )
    inner = (
        "<main class='cp-login-card'>"
        "<div>"
        "<h1>ControlPlay</h1>"
        "<p class='subtitle'>Connexion administration</p>"
        "</div>"
        f"{err_html}"
        "<form method='post' action='/login' autocomplete='on'>"
        f"<input type='hidden' name='next' value=\"{nxt_esc}\"/>"
        "<label for='identifier'>Email ou téléphone</label>"
        "<input id='identifier' name='identifier' type='text' required autocomplete='username' "
        "autocapitalize='none' spellcheck='false' placeholder='ex. admin@domaine.com'/>"
        "<label for='password'>Mot de passe</label>"
        "<input id='password' name='password' type='password' required autocomplete='current-password' "
        "placeholder='••••••••'/>"
        "<p class='cp-muted' style='margin:-0.25rem 0 1rem'>"
        "Identifiant identique à celui enregistré sur votre compte (email ou numéro).</p>"
        "<button type='submit'>Se connecter</button>"
        "</form>"
        "<div class='cp-login-footer'>"
        "<a href='/'>← Retour à l’accueil public</a>"
        "</div>"
        "</main>"
    )
    return html_shell_login("Connexion — ControlPlay", inner)


@app.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next_url: str = Query("", alias="next"),
):
    if request.session.get("user_id"):
        target = _login_next_safe(next_url or "/admin")
        return RedirectResponse(url=target, status_code=303)
    from spa import spa_index_response

    return spa_index_response(login_next=next_url or "/admin")


@app.post("/login")
def login_post(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    next_url: str = Form("/admin", alias="next"),
    db: Session = Depends(get_db),
):
    nxt = _login_next_safe(next_url)
    ident = identifier.strip()
    pwd = password or ""
    user = _find_user_for_login(db, ident)
    if not user or not verify_password(pwd, user.password_hash):
        # 200 (pas 401/403) : évite la page « HTTP ERROR » vide du navigateur ; le message reste dans le HTML.
        return HTMLResponse(
            _html_login_page(nxt, error="Identifiants incorrects. Vérifiez l’email ou le téléphone et le mot de passe."),
            status_code=200,
        )
    if not user_can_access_admin(db, user):
        return HTMLResponse(
            _html_login_page(
                nxt,
                error=(
                    "Ce compte n’a pas accès à l’administration. Il faut le rôle super_admin global "
                    "ou le rôle global « admin de salle », ou un rôle sur au moins une salle (salle_admin, responsable ou gérant). "
                    "Un super admin peut vous attribuer un rôle depuis la page utilisateurs de la salle. "
                    "Compte propriétaire : créez-le avec « make ensure-super-admin » (identifiant e-mail par défaut, pas le téléphone)."
                ),
            ),
            status_code=200,
        )
    request.session["user_id"] = user.id
    return RedirectResponse(url=nxt, status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home():
    from spa import spa_index_response

    return spa_index_response()


@app.get("/salle/{salle_code}", response_class=HTMLResponse)
def salle_page(salle_code: str, db: Session = Depends(get_db)):
    salle = db.query(Salle).filter(Salle.code == salle_code).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    stations = (
        db.query(Station)
        .filter(Station.salle_id == salle.id, Station.is_active.is_(True))
        .order_by(Station.id.desc())
        .all()
    )

    rows = "".join(
        [
            "<li>"
            f"<strong>{html_lib.escape(s.name)}</strong> "
            f"<span class='cp-muted'>({html_lib.escape(s.code)})</span><br/>"
            f"<a href='/s/{html_lib.escape(s.code)}'>Ouvrir la page station</a> · "
            f"<a href='/qr/{html_lib.escape(s.code)}.png'>QR</a>"
            "</li>"
            for s in stations
        ]
    )

    body = (
        "<header class='cp-client-topbar'>"
        "<a class='cp-client-logo' href='/'>ControlPlay</a>"
        "</header>"
        "<main class='cp-client-main'>"
        f"<h1>{html_lib.escape(salle.name)}</h1>"
        "<p class='cp-client-lead'>Stations rattachées à ce lieu.</p>"
        f"<ul class='cp-station-list'>{rows}</ul>"
        "<p class='cp-client-links'><a href='/'>Accueil ControlPlay</a></p>"
        "</main>"
    )
    return _pub(f"Salle {salle.name}", body)


@app.get("/s/{station_code}", response_class=HTMLResponse)
def station_page(station_code: str, db: Session = Depends(get_db)):
    # Migration progressive : tunnel station servi par la SPA, tout en gardant
    # les endpoints POST historiques (/checkout, /extend/checkout).
    if os.getenv("PUBLIC_STATION_SPA", "1").strip() == "1":
        from spa import spa_index_response

        return spa_index_response()

    station = db.query(Station).filter(Station.code == station_code).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")
    active_session = get_active_session_by_station(db, station.id)
    station_offers = (
        db.query(Offer)
        .join(StationOffer, StationOffer.offer_id == Offer.id)
        .filter(
            StationOffer.station_id == station.id,
            StationOffer.is_active.is_(True),
            Offer.is_active.is_(True),
        )
        .all()
    )
    salle_offers = []
    if station.salle_id is not None:
        salle_offers = (
            db.query(Offer)
            .join(SalleOffer, SalleOffer.offer_id == Offer.id)
            .filter(
                SalleOffer.salle_id == station.salle_id,
                SalleOffer.is_active.is_(True),
                Offer.is_active.is_(True),
            )
            .all()
        )
    # On affiche au plus 1 offre par (durée, prix).
    # Priorité d'affichage (et dédup) : Paystack si activé, sinon CinétPay.
    if paystack_enabled():
        provider_priority = {"paystack": 0, "cinetpay": 1}
    else:
        provider_priority = {"paystack": 1, "cinetpay": 0}
    offers_by_duration_price = {}
    for offer in [*station_offers, *salle_offers]:
        key = (offer.duration_minutes, offer.price_xof)
        current = offers_by_duration_price.get(key)
        if current is None:
            offers_by_duration_price[key] = offer
            continue
        if provider_priority.get(offer.provider, 99) < provider_priority.get(current.provider, 99):
            offers_by_duration_price[key] = offer

    offers = sorted(offers_by_duration_price.values(), key=lambda o: (o.duration_minutes, o.price_xof))
    esc_station_code = html_lib.escape(station_code)
    offer_cards = []
    for offer in offers:
        on = html_lib.escape(offer.name)
        offer_cards.append(
            "<article class='cp-offer-card'>"
            "<div class='cp-offer-meta'>"
            f"<h2 class='cp-offer-title'>{on}</h2>"
            f"<p class='cp-offer-price'><strong>{offer.price_xof} XOF</strong> · {offer.duration_minutes} min</p>"
            "</div>"
            "<form method='post' action='/checkout' class='cp-offer-form'>"
            f"<input type='hidden' name='station_code' value='{esc_station_code}'/>"
            f"<input type='hidden' name='offer_id' value='{offer.id}'/>"
            "<div class='cp-form-row'>"
            "<label>Email<input type='email' name='email' placeholder='optionnel' autocomplete='email'/></label>"
            "<label class='cp-form-connect'><input type='checkbox' name='connect' value='1'/> "
            "Lier un compte (téléphone requis)</label>"
            "<label>Téléphone<input type='tel' name='phone' placeholder='+225…' autocomplete='tel'/></label>"
            "</div>"
            "<button type='submit'>Payer</button>"
            "</form>"
            "</article>"
        )
    offers_section = (
        "<section class='cp-offers' aria-label='Jeux disponibles'>"
        + "<h2 class='cp-section-title'>Jeux disponibles</h2>"
        + "".join(offer_cards)
        + "</section>"
    )

    extension_section = ""
    if active_session:
        ext_cards = []
        for offer in offers:
            on = html_lib.escape(offer.name)
            ext_cards.append(
                "<article class='cp-offer-card'>"
                "<div class='cp-offer-meta'>"
                f"<h2 class='cp-offer-title'>+ {offer.duration_minutes} min · {on}</h2>"
                f"<p class='cp-offer-price'><strong>{offer.price_xof} XOF</strong></p>"
                "</div>"
                "<form method='post' action='/extend/checkout' class='cp-offer-form'>"
                f"<input type='hidden' name='station_code' value='{esc_station_code}'/>"
                f"<input type='hidden' name='offer_id' value='{offer.id}'/>"
                "<div class='cp-form-row'>"
                "<label>Email<input type='email' name='email' placeholder='optionnel' autocomplete='email'/></label>"
                "<label class='cp-form-connect'><input type='checkbox' name='connect' value='1'/> "
                "Lier un compte (téléphone requis)</label>"
                "<label>Téléphone<input type='tel' name='phone' placeholder='+225…' autocomplete='tel'/></label>"
                "</div>"
                "<button type='submit'>Ajouter du temps</button>"
                "</form>"
                "</article>"
            )
        extension_section = (
            "<section class='cp-offers cp-offers--extend' aria-label='Prolongation'>"
            "<h2 class='cp-section-title'>Session en cours — ajouter du temps</h2>"
            + "".join(ext_cards)
            + "</section>"
        )

    retour_href = "/"
    if station.salle_id is not None:
        salle = db.query(Salle).filter(Salle.id == station.salle_id).first()
        if salle:
            retour_href = f"/salle/{salle.code}"

    composition_items: list[str] = []
    if station.tv_size_inches is not None:
        composition_items.append(f"TV {station.tv_size_inches} pouces")
    if station.console_model:
        composition_items.append(f"Console {html_lib.escape(station.console_model)}")
    if station.vr_headset_model:
        composition_items.append(f"VR {html_lib.escape(station.vr_headset_model)}")

    composition_section = ""
    if composition_items:
        pills = "".join(
            [f"<span class='cp-composition-pill'>{html_lib.escape(x)}</span>" for x in composition_items]
        )
        composition_section = (
            "<section class='cp-station-meta' aria-label='Composition de la station'>"
            "<h2 class='cp-section-title' style='margin-top:0.5rem'>Composition</h2>"
            f"<div class='cp-composition-grid'>{pills}</div>"
            "</section>"
        )

    body = (
        "<header class='cp-client-topbar'>"
        "<a class='cp-client-logo' href='/'>ControlPlay</a>"
        f"<span class='cp-client-badge'>{esc_station_code}</span>"
        "</header>"
        "<main class='cp-client-main'>"
        f"<h1>{html_lib.escape(station.name)}</h1>"
        "<p class='cp-client-lead'>Choisissez un jeu, complétez si besoin, puis payez en ligne.</p>"
        f"{composition_section}"
        f"{offers_section}"
        f"{extension_section}"
        "<p class='cp-client-links'>"
        f"<a href='/qr/{esc_station_code}.png'>QR de la station</a>"
        " · "
        f"<a href='{html_lib.escape(retour_href)}'>Retour</a>"
        "</p>"
        "</main>"
    )
    return _pub(station.name, body)


@app.get("/rental", response_class=HTMLResponse)
def rental_catalog_page(db: Session = Depends(get_db)):
    """Location console : catalogue et checkout (tunnel distinct du temps de jeu `/checkout`)."""
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
    plan_options = "".join(
        [
            f"<option value='{p.id}'>{html_lib.escape(p.name)} — {p.price_xof} XOF ({html_lib.escape(p.duration_label)})</option>"
            for p in plans
        ]
    )
    console_options = "".join(
        [
            f"<option value='{html_lib.escape(c.code)}'>{html_lib.escape(c.code)} — {html_lib.escape(c.name)}</option>"
            for c in consoles
        ]
    )
    body = (
        "<header class='cp-client-topbar'>"
        "<a class='cp-client-logo' href='/'>ControlPlay</a>"
        "<span class='cp-client-badge'>Location</span>"
        "</header>"
        "<main class='cp-client-main cp-wrap'>"
        "<h1>Location console / matériel</h1>"
        "<p class='cp-client-lead'>Catalogue <strong>location ControlPlay</strong> (indépendant des salles de jeu / QR). "
        "Choisissez un forfait et une console de retrait.</p>"
        "<form method='post' action='/rental/checkout' class='cp-offer-card' style='max-width:520px'>"
        "<div class='cp-form-row' style='flex-direction:column;align-items:stretch'>"
        "<label>Forfait<select name='rental_plan_id' required>" + plan_options + "</select></label>"
        "<label>Console de retrait<select name='console_code' required>" + console_options + "</select></label>"
        "<label>Email<input type='email' name='email' placeholder='optionnel' autocomplete='email'/></label>"
        "<label class='cp-form-connect'><input type='checkbox' name='connect' value='1'/> "
        "Lier un compte (téléphone requis)</label>"
        "<label>Téléphone<input type='tel' name='phone' placeholder='+225…' autocomplete='tel'/></label>"
        "</div>"
        "<button type='submit' class='cp-offer-form' style='margin-top:12px'>Payer la location</button>"
        "</form>"
        "<p class='cp-client-links'><a href='/location'>← Vitrine location</a> · <a href='/'>Accueil</a></p>"
        "</main>"
    )
    return _pub("Location console", body)


@app.post("/rental/checkout")
def rental_checkout(
    rental_plan_id: int = Form(...),
    console_code: str = Form(...),
    connect: str = Form("0"),
    email: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    plan = (
        db.query(RentalPlan)
        .filter(RentalPlan.id == rental_plan_id, RentalPlan.is_active.is_(True))
        .first()
    )
    console = db.query(RentalConsole).filter(RentalConsole.code == console_code.strip()).first()
    if not plan or not console or not console.is_active:
        raise HTTPException(status_code=404, detail="Forfait ou console location introuvable")
    if plan.rental_console_id is not None and plan.rental_console_id != console.id:
        raise HTTPException(status_code=400, detail="Ce forfait n'est pas disponible sur ce point de retrait")

    if connect == "1":
        if not phone or not phone.strip():
            raise HTTPException(status_code=400, detail="Numéro de téléphone requis (connexion)")
        customer_phone = phone.strip()
        customer_email = (email or "").strip() or None
        user = get_or_create_user_by_phone(db, customer_phone, customer_email)
    else:
        user = get_default_user(db)
        customer_phone = None
        customer_email = None

    if not (is_paystack_configured() or is_cinetpay_configured()):
        chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
        reference = make_payment_reference(chosen_sim_provider)
        order = RentalOrder(
            rental_plan_id=plan.id,
            rental_console_id=console.id,
            user_id=user.id,
            payment_provider=chosen_sim_provider,
            payment_reference=reference,
            payment_status="pending",
            status="pending",
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        log_event(
            db,
            f"Location checkout (simulation) {reference} ({chosen_sim_provider})",
        )
        email_query = customer_email or ""
        return RedirectResponse(
            url=f"/simulate/pay/{reference}?status=success&email={email_query}",
            status_code=303,
        )

    if is_paystack_configured():
        paystack_email = get_paystack_email(customer_email, customer_phone)
        reference = make_payment_reference("paystack")
        try:
            authorization_url = init_paystack_payment(
                reference,
                email=paystack_email,
                amount_xof=plan.price_xof,
                callback_url=f"{get_base_url()}/payments/return/paystack/{reference}",
            )
            order = RentalOrder(
                rental_plan_id=plan.id,
                rental_console_id=console.id,
                user_id=user.id,
                payment_provider="paystack",
                payment_reference=reference,
                payment_status="pending",
                status="pending",
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            log_event(db, f"Location Paystack init {reference}")
            return RedirectResponse(url=authorization_url, status_code=303)
        except Exception as e:
            log_event(
                db,
                f"Location Paystack init echoue: {e}",
                level="warning",
            )

    if is_cinetpay_configured():
        reference = make_payment_reference("cinetpay")
        payment_url = init_cinetpay_payment(
            transaction_id=reference,
            amount_xof=plan.price_xof,
            description=plan.name,
        )
        order = RentalOrder(
            rental_plan_id=plan.id,
            rental_console_id=console.id,
            user_id=user.id,
            payment_provider="cinetpay",
            payment_reference=reference,
            payment_status="pending",
            status="pending",
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        log_event(db, f"Location CinetPay init {reference}")
        return RedirectResponse(url=payment_url, status_code=303)

    chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
    reference = make_payment_reference(chosen_sim_provider)
    order = RentalOrder(
        rental_plan_id=plan.id,
        rental_console_id=console.id,
        user_id=user.id,
        payment_provider=chosen_sim_provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_email=customer_email,
        customer_phone=customer_phone,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    email_query = customer_email or ""
    return RedirectResponse(
        url=f"/simulate/pay/{reference}?status=success&email={email_query}",
        status_code=303,
    )


@app.post("/checkout")
def checkout(
    station_code: str = Form(...),
    offer_id: int = Form(...),
    connect: str = Form("0"),
    email: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    station = db.query(Station).filter(Station.code == station_code).first()
    offer = db.query(Offer).filter(Offer.id == offer_id, Offer.is_active.is_(True)).first()
    if not station or not offer:
        raise HTTPException(status_code=404, detail="Station ou offre introuvable")

    if connect == "1":
        if not phone or not phone.strip():
            raise HTTPException(status_code=400, detail="Numéro de téléphone requis (connexion)")
        customer_phone = phone.strip()
        customer_email = (email or "").strip() or None
        user = get_or_create_user_by_phone(db, customer_phone, customer_email)
    else:
        # Mode “invité” : aucun email/phone requis.
        user = get_default_user(db)
        customer_phone = None
        customer_email = None

    station_allowed = (
        db.query(StationOffer)
        .filter(
            StationOffer.station_id == station.id,
            StationOffer.offer_id == offer.id,
            StationOffer.is_active.is_(True),
        )
        .first()
    )
    salle_allowed = None
    if station.salle_id is not None:
        salle_allowed = (
            db.query(SalleOffer)
            .filter(
                SalleOffer.salle_id == station.salle_id,
                SalleOffer.offer_id == offer.id,
                SalleOffer.is_active.is_(True),
            )
            .first()
        )
    if not station_allowed and not salle_allowed:
        raise HTTPException(status_code=400, detail="Offre non disponible pour cette station")
    station_busy = (
        db.query(GameSession)
        .filter(
            GameSession.station_id == station.id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .first()
    )
    if station_busy:
        raise HTTPException(status_code=409, detail="Station deja occupee")

    # Si PSP non configuré (MVP/dev), on conserve la simulation.
    if not (is_paystack_configured() or is_cinetpay_configured()):
        chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
        reference = make_payment_reference(chosen_sim_provider)
        session = GameSession(
            station_id=station.id,
            offer_id=offer.id,
            user_id=user.id,
            payment_provider=chosen_sim_provider,
            payment_reference=reference,
            payment_status="pending",
            status="pending",
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.add(session)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Station deja occupee")
        db.refresh(session)
        log_event(db, f"Checkout (simulation) cree {reference} ({chosen_sim_provider})", station_id=station.id, session_id=session.id)
        email_query = customer_email or ""
        fake_url = f"/simulate/pay/{reference}?status=success&email={email_query}"
        return RedirectResponse(url=fake_url, status_code=303)

    # Mode paiements réels:
    # - Paystack en priorité tant qu'il est activé (admin) et configuré (clés)
    # - Si Paystack échoue ou est désactivé, on bascule sur CinetPay
    if is_paystack_configured():
        paystack_email = get_paystack_email(customer_email, customer_phone)
        reference = make_payment_reference("paystack")
        try:
            authorization_url = init_paystack_payment(
                reference,
                email=paystack_email,
                amount_xof=offer.price_xof,
            )
            session = GameSession(
                station_id=station.id,
                offer_id=offer.id,
                user_id=user.id,
                payment_provider="paystack",
                payment_reference=reference,
                payment_status="pending",
                status="pending",
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
            db.add(session)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(status_code=409, detail="Station deja occupee")
            db.refresh(session)
            log_event(db, f"Checkout Paystack init {reference}", station_id=station.id, session_id=session.id)
            return RedirectResponse(url=authorization_url, status_code=303)
        except Exception as e:
            log_event(
                db,
                f"Paystack init echoue, fallback vers cinetpay: {e}",
                level="warning",
                station_id=station.id,
            )

    # Fallback direct vers CinetPay (init réussie ou Paystack désactivé/indisponible)
    if is_cinetpay_configured():
        reference = make_payment_reference("cinetpay")
        payment_url = init_cinetpay_payment(
            transaction_id=reference,
            amount_xof=offer.price_xof,
            description=offer.name,
        )
        session = GameSession(
            station_id=station.id,
            offer_id=offer.id,
            user_id=user.id,
            payment_provider="cinetpay",
            payment_reference=reference,
            payment_status="pending",
            status="pending",
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.add(session)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Station deja occupee")
        db.refresh(session)
        log_event(db, f"Checkout CinetPay init {reference}", station_id=station.id, session_id=session.id)
        return RedirectResponse(url=payment_url, status_code=303)

    # Si on arrive ici: aucun provider réel utilisable => simulation.
    chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
    reference = make_payment_reference(chosen_sim_provider)
    session = GameSession(
        station_id=station.id,
        offer_id=offer.id,
        user_id=user.id,
        payment_provider=chosen_sim_provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_email=customer_email,
        customer_phone=customer_phone,
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Station deja occupee")
    db.refresh(session)
    log_event(
        db,
        f"Checkout (simulation fallback) cree {reference} ({chosen_sim_provider})",
        station_id=station.id,
        session_id=session.id,
    )
    email_query = customer_email or ""
    fake_url = f"/simulate/pay/{reference}?status=success&email={email_query}"
    return RedirectResponse(url=fake_url, status_code=303)


@app.post("/extend/checkout")
def extend_checkout(
    station_code: str = Form(...),
    offer_id: int = Form(...),
    connect: str = Form("0"),
    email: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    station = db.query(Station).filter(Station.code == station_code).first()
    offer = db.query(Offer).filter(Offer.id == offer_id, Offer.is_active.is_(True)).first()
    if not station or not offer:
        raise HTTPException(status_code=404, detail="Station ou offre introuvable")

    station_allowed = (
        db.query(StationOffer)
        .filter(
            StationOffer.station_id == station.id,
            StationOffer.offer_id == offer.id,
            StationOffer.is_active.is_(True),
        )
        .first()
    )
    salle_allowed = None
    if station.salle_id is not None:
        salle_allowed = (
            db.query(SalleOffer)
            .filter(
                SalleOffer.salle_id == station.salle_id,
                SalleOffer.offer_id == offer.id,
                SalleOffer.is_active.is_(True),
            )
            .first()
        )
    if not station_allowed and not salle_allowed:
        raise HTTPException(status_code=400, detail="Offre non disponible pour cette station")

    active_session = get_active_session_by_station(db, station.id)
    if not active_session:
        raise HTTPException(status_code=409, detail="Aucune session active à prolonger")

    if connect == "1":
        if not phone or not phone.strip():
            raise HTTPException(status_code=400, detail="Numéro de téléphone requis (connexion)")
        customer_phone = phone.strip()
        customer_email = (email or "").strip() or None
    else:
        customer_phone = None
        customer_email = None

    reference = make_payment_reference(offer.provider)
    extension = SessionExtension(
        session_id=active_session.id,
        extra_minutes=offer.duration_minutes,
        user_id=active_session.user_id,
        payment_provider=offer.provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_phone=customer_phone,
    )
    db.add(extension)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Station deja occupee")
    db.refresh(extension)

    # Pour l'instant, on ne supporte le paiement d'extension que via Paystack.
    # En prod, si Paystack est configuré mais l'offre n'est pas paystack, on refuse (pas d'extension gratuite).
    if is_paystack_api_configured():
        if extension.payment_provider != "paystack":
            raise HTTPException(status_code=501, detail="Extension paystack uniquement pour l'instant")
        callback = f"{get_base_url()}/payments/return/extension/paystack/{reference}"
        paystack_email = get_paystack_email(customer_email, customer_phone)
        authorization_url = init_paystack_payment(
            reference,
            email=paystack_email,
            amount_xof=offer.price_xof,
            callback_url=callback,
        )
        return RedirectResponse(url=authorization_url, status_code=303)

    # Si Paystack est désactivé/indisponible mais CinetPay est disponible,
    # on refuse pour l'instant car le flux "extension cinetpay" n'existe pas.
    if is_cinetpay_configured():
        raise HTTPException(status_code=501, detail="Extension CinetPay non supportée pour l'instant")

    # MVP/dev: si aucun provider réel n'est disponible, on applique directement.
    applied = apply_paid_extension(db, extension, source="extend_simulate", trusted=True)
    if not applied:
        return _pub(
            "Extension",
            "<h1>Extension refusée</h1><p>La session n'est plus active.</p><p><a href='/'>Retour</a></p>",
        )
    return _pub(
        "Extension",
        f"<h1>Temps ajoute</h1><p>La TV reste sur HDMI2.</p><p><a href='/s/{html_lib.escape(station_code)}'>Retour</a></p>",
    )


@app.get("/simulate/pay/{reference}", response_class=HTMLResponse)
def simulate_payment(reference: str, status: str, email: str = "", db: Session = Depends(get_db)):
    rental_order = db.query(RentalOrder).filter(RentalOrder.payment_reference == reference).first()
    if rental_order:
        if status != "success":
            if rental_order.payment_status != "paid":
                rental_order.payment_status = "failed"
                rental_order.status = "failed"
                db.commit()
            return _pub(
                "Location",
                "<h1>Paiement location refuse</h1>"
                "<p><a href='/rental'>Nouvelle tentative</a></p>"
                "<p><a href='/location'>Vitrine location</a></p>",
            )
        if rental_order.payment_status == "paid" and rental_order.status == "paid":
            return RedirectResponse(url="/location", status_code=303)
        activated = activate_paid_rental(db, rental_order, "simulate", trusted=True)
        if not activated:
            db.refresh(rental_order)
            if rental_order.payment_status == "paid":
                return RedirectResponse(url="/location", status_code=303)
            return _pub(
                "Location",
                "<h1>Location non validee</h1>"
                "<p>Impossible de confirmer le paiement.</p>"
                "<p><a href='/rental'>Retour location</a></p>",
            )
        return RedirectResponse(url="/location", status_code=303)

    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")
    if status != "success":
        original_offer = session.offer
        session.payment_status = "failed"
        session.status = "failed"
        db.commit()

        # Fallback simulation: paystack d'abord, sinon cinetpay. On ne repasse pas sur paystack automatiquement.
        if session.payment_provider != "paystack":
            return _pub(
                "Paiement",
                "<h1>Paiement echoue</h1><p>Aucun fallback disponible.</p><p><a href='/'>Retour accueil</a></p>",
            )

        new_reference = make_payment_reference("cinetpay")
        new_session = GameSession(
            station_id=session.station_id,
            offer_id=original_offer.id,
            user_id=session.user_id,
            payment_provider="cinetpay",
            payment_reference=new_reference,
            payment_status="pending",
            status="pending",
            customer_email=session.customer_email,
            customer_phone=session.customer_phone,
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        log_event(
            db,
            f"Fallback paiement simulation: {reference} ({session.payment_provider}) -> {new_reference} (cinetpay)",
            level="warning",
            station_id=session.station_id,
            session_id=new_session.id,
        )

        activated = activate_paid_session(db, new_session, "simulate_fallback", trusted=True)
        if not activated:
            return _pub(
                "Paiement",
                f"<h1>Paiement valide (fallback)</h1><p>Reference initiale: {html_lib.escape(reference)}</p>"
                f"<p>Reference fallback: {html_lib.escape(new_reference)}</p>"
                "<p>Station actuellement occupee: activation differee.</p>"
                "<p><a href='/'>Retour accueil</a></p>",
            )

        station_code = new_session.station.code if new_session.station else None
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Paiement",
            f"<h1>Paiement valide (fallback)</h1><p>Reference initiale: {html_lib.escape(reference)}</p>"
            f"<p>Reference fallback: {html_lib.escape(new_reference)}</p>"
            "<p>La TV devrait basculer sur HDMI2.</p>"
            "<p><a href='/'>Retour accueil</a></p>",
        )

    activate_paid_session(db, session, "simulate", trusted=True)
    station_code = session.station.code if session.station else None
    if station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)
    return _pub(
        "Paiement",
        f"<h1>Paiement valide</h1><p>Reference: {html_lib.escape(reference)}</p>"
        "<p>La TV devrait basculer sur HDMI2.</p>"
        "<p><a href='/'>Retour accueil</a></p>",
    )


@app.get("/payments/return/paystack/{reference}")
def paystack_return(reference: str, request: Request, db: Session = Depends(get_db)):
    rental = db.query(RentalOrder).filter(RentalOrder.payment_reference == reference).first()
    if rental:
        if rental.payment_status == "paid":
            return RedirectResponse(url="/location", status_code=303)
        if (
            rental.payment_provider == "paystack"
            and is_paystack_api_configured()
            and rental.status == "pending"
            and rental.payment_status != "paid"
        ):
            if verify_paystack_transaction(reference):
                activate_paid_rental(db, rental, "paystack_return", trusted=False)
                db.refresh(rental)
        if rental.payment_status == "paid":
            return RedirectResponse(url="/location", status_code=303)
        return _pub(
            "Location",
            "<h1>Paiement location en attente</h1>"
            "<p>La confirmation peut arriver par notification (webhook).</p>"
            "<p><a href='/location'>Vitrine location</a></p>",
        )

    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")

    callback_status = (request.query_params.get("status") or request.query_params.get("payment_status") or "").lower()
    station_code = session.station.code if session.station else None

    if session.payment_status == "paid" or session.status == "active":
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Paiement",
            "<h1>Paiement confirme</h1><p>La TV sera activee.</p><p><a href='/'>Retour accueil</a></p>",
        )

    # En général, l'activation réelle arrive via webhook.
    # Mais Paystack “return” peut arriver sans `status=` (ex: seulement `trxref`/`reference`).
    # Donc on tente une vérification + activation côté serveur ici aussi.
    if (
        session.payment_provider == "paystack"
        and is_paystack_api_configured()
        and session.status == "pending"
        and session.payment_status != "paid"
    ):
        if verify_paystack_transaction(reference):
            activate_paid_session(db, session, "paystack_return", trusted=False)
            db.refresh(session)

    # Si on a réussi, on renvoie sur la page de la station.
    if (session.payment_status == "paid" or session.status == "active") and station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)

    # Sinon, on redirige quand même sur la station (pour que l'utilisateur puisse
    # voir la session et attendre l'activation via webhook/worker).
    if station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)

    return _pub(
        "Paiement",
        "<h1>Paiement en attente</h1><p>Merci de patienter.</p><p><a href='/'>Retour accueil</a></p>",
    )


@app.get("/payments/return/extension/paystack/{reference}", response_class=HTMLResponse)
def paystack_extension_return(reference: str, request: Request, db: Session = Depends(get_db)):
    extension = db.query(SessionExtension).filter(SessionExtension.payment_reference == reference).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Reference introuvable")

    station_code = None
    if extension.session and extension.session.station:
        station_code = extension.session.station.code

    if extension.status == "applied" or extension.payment_status == "paid":
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Extension",
            "<h1>Extension confirmée</h1><p>Temps ajouté.</p><p><a href='/'>Retour accueil</a></p>",
        )

    if not is_paystack_api_configured():
        return _pub(
            "Extension",
            "<h1>Extension en attente</h1><p>Paystack non configuré.</p><p><a href='/'>Retour accueil</a></p>",
        )

    if verify_paystack_transaction(reference):
        apply_paid_extension(db, extension, "paystack_extension_return", trusted=True)
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Extension",
            "<h1>Extension confirmée</h1><p>Temps ajouté.</p><p><a href='/'>Retour accueil</a></p>",
        )

    extension.payment_status = "failed"
    extension.status = "failed"
    db.commit()
    return _pub(
        "Extension",
        "<h1>Extension refusée</h1><p>Paiement Paystack non confirmé.</p><p><a href='/'>Retour accueil</a></p>",
    )


@app.api_route("/payments/return/cinetpay", methods=["GET", "POST"])
async def cinetpay_return(request: Request, db: Session = Depends(get_db)):
    transaction_id = request.query_params.get("transaction_id")
    if not transaction_id and request.method in ("POST",):
        form = await request.form()
        transaction_id = form.get("transaction_id")

    if not transaction_id:
        raise HTTPException(status_code=404, detail="transaction_id introuvable")

    rental = db.query(RentalOrder).filter(RentalOrder.payment_reference == transaction_id).first()
    if rental:
        if rental.payment_status == "paid":
            return RedirectResponse(url="/location", status_code=303)
        return _pub(
            "Location",
            "<h1>Paiement location en attente</h1>"
            "<p>Merci de patienter (validation via webhook CinetPay).</p>"
            "<p><a href='/location'>Vitrine location</a></p>",
        )

    session = db.query(GameSession).filter(GameSession.payment_reference == transaction_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")

    station_code = session.station.code if session.station else None
    if session.payment_status == "paid" or session.status == "active":
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Paiement",
            "<h1>Paiement confirme</h1><p>La TV sera activee.</p><p><a href='/'>Retour accueil</a></p>",
        )

    if station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)
    return _pub(
        "Paiement",
        "<h1>Paiement en attente / echoue</h1>"
        "<p>Merci de patienter (validation via webhook).</p>"
        "<p><a href='/'>Retour accueil</a></p>",
    )


@app.post("/webhooks/paystack")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    secret = os.getenv("PAYSTACK_WEBHOOK_SECRET", "")
    if secret:
        expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
        if signature != expected:
            raise HTTPException(status_code=401, detail="Signature invalide")
    data = await request.json()
    event = data.get("event", "")
    reference = data.get("data", {}).get("reference")
    if not reference:
        return {"ok": True}
    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    extension = db.query(SessionExtension).filter(SessionExtension.payment_reference == reference).first()

    # En cas d'événement non-success, on libère la station.
    if event and event != "charge.success":
        if session and session.status == "pending":
            session.payment_status = "failed"
            session.status = "failed"
            db.commit()
            log_event(
                db,
                f"Paystack event {event}: session echouee pour {reference}",
                level="warning",
                station_id=session.station_id,
                session_id=session.id,
            )
        if extension and extension.status == "pending":
            extension.payment_status = "failed"
            extension.status = "failed"
            db.commit()
        return {"ok": True}

    if session:
        activate_paid_session(db, session, "paystack_webhook")
    elif extension:
        apply_paid_extension(db, extension, "paystack_webhook")
    return {"ok": True}


@app.post("/webhooks/cinetpay")
async def cinetpay_webhook(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    received_token = request.headers.get("x-token", "") or request.headers.get("X-Token", "")
    secret_key = os.getenv("CINETPAY_SECRET_KEY", "")

    # Vérification x-token (HMAC SHA256) si la clé secrète est configurée.
    if secret_key and received_token:
        # Concaténation exacte des champs dans l'ordre demandé par la doc CinetPay.
        # Voir: https://docs.cinetpay.com/api/1.0-en/checkout/hmac
        data_str = (
            str(form.get("cpm_site_id", ""))
            + str(form.get("cpm_trans_id", ""))
            + str(form.get("cpm_trans_date", ""))
            + str(form.get("cpm_amount", ""))
            + str(form.get("cpm_currency", ""))
            + str(form.get("signature", ""))
            + str(form.get("payment_method", ""))
            + str(form.get("cel_phone_num", ""))
            + str(form.get("cpm_phone_prefixe", ""))
            + str(form.get("cpm_language", ""))
            + str(form.get("cpm_version", ""))
            + str(form.get("cpm_payment_config", ""))
            + str(form.get("cpm_page_action", ""))
            + str(form.get("cpm_custom", ""))
            + str(form.get("cpm_designation", ""))
            + str(form.get("cpm_error_message", ""))
        )
        generated_token = hmac.new(
            secret_key.encode("utf-8"),
            data_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(received_token, generated_token):
            raise HTTPException(status_code=401, detail="x-token invalide")

    reference = form.get("cpm_trans_id")
    payment_status = (form.get("cpm_result") or form.get("status") or "").lower()
    if not reference:
        return {"ok": True}
    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    rental_order = db.query(RentalOrder).filter(RentalOrder.payment_reference == reference).first()

    if payment_status and payment_status not in ("00", "accepted", "success"):
        if session and session.status == "pending":
            session.payment_status = "failed"
            session.status = "failed"
            db.commit()
            log_event(
                db,
                f"CinetPay status {payment_status}: session echouee pour {reference}",
                level="warning",
                station_id=session.station_id,
                session_id=session.id,
            )
        if rental_order and rental_order.status == "pending":
            rental_order.payment_status = "failed"
            rental_order.status = "failed"
            db.commit()
            log_event(
                db,
                f"CinetPay status {payment_status}: location echouee pour {reference}",
                level="warning",
            )
        return {"ok": True}

    if session:
        activate_paid_session(db, session, "cinetpay_webhook")
    elif rental_order:
        activate_paid_rental(db, rental_order, "cinetpay_webhook", trusted=False)
    return {"ok": True}


@app.get("/qr/{station_code}.png")
def station_qr(station_code: str):
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    url = f"{base_url}/s/{station_code}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/admin")
@app.get("/admin/{path:path}")
def admin_spa(path: str = "", _: str = Depends(require_admin)):
    from spa import spa_index_response

    return spa_index_response()


def _batch_user_roles_maps(
    db: Session, user_ids: list[int]
) -> tuple[dict[int, list[str]], dict[int, list[tuple[str, str]]]]:
    """Rôles globaux (user_roles) et par salle (code, role_key) pour une liste d'utilisateurs."""
    if not user_ids:
        return {}, {}
    gmap: dict[int, list[str]] = defaultdict(list)
    for uid, key in (
        db.query(UserRole.user_id, Role.key)
        .join(Role, Role.id == UserRole.role_id)
        .filter(UserRole.user_id.in_(user_ids))
        .order_by(Role.key)
        .all()
    ):
        gmap[uid].append(key)
    smap: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for uid, code, key in (
        db.query(SalleUser.user_id, Salle.code, Role.key)
        .join(Role, Role.id == SalleUser.role_id)
        .join(Salle, Salle.id == SalleUser.salle_id)
        .filter(SalleUser.user_id.in_(user_ids))
        .order_by(Salle.code, Role.key)
        .all()
    ):
        smap[uid].append((code, key))
    return gmap, smap


def _html_user_roles_summary_cell(global_keys: list[str], salle_pairs: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    if global_keys:
        uniq = sorted(set(global_keys))
        parts.append("<b>Global :</b> " + html_lib.escape(", ".join(uniq)))
    for code, rk in sorted(salle_pairs, key=lambda x: (x[0], x[1])):
        parts.append(html_lib.escape(f"{code} → {rk}"))
    inner = "<br/>".join(parts) if parts else "<span style='color:#888'>—</span>"
    return f"<td style='vertical-align:top;font-size:90%;max-width:320px'>{inner}</td>"


def _count_global_super_admins(db: Session) -> int:
    return (
        db.query(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.key == "super_admin")
        .count()
    )


_SUPER_ADMIN_REMOVABLE_GLOBAL_ROLE_KEYS: frozenset[str] = frozenset(
    {"super_admin", "salle_admin", "admin"}
)


def _apply_salle_role_for_user(
    db: Session, user_id: int, salle_id: int, role_key: str
) -> str | None:
    """
    Ajoute ou remplace SalleUser pour (user, salle). Retourne un message d’erreur ou None.
    """
    allowed = ("salle_admin", "responsable", "manager")
    if role_key not in allowed:
        return "Rôle sur salle invalide."
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        return "Salle introuvable."
    role = db.query(Role).filter(Role.key == role_key).first()
    if not role:
        return "Rôle introuvable en base."
    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    if role_key == "manager" and mgr_role:
        other = (
            db.query(SalleUser)
            .filter(
                SalleUser.user_id == user_id,
                SalleUser.role_id == mgr_role.id,
                SalleUser.salle_id != salle_id,
            )
            .first()
        )
        if other:
            return "Ce compte ne peut être gérant que d’une seule salle."
    su = (
        db.query(SalleUser)
        .filter(SalleUser.user_id == user_id, SalleUser.salle_id == salle_id)
        .first()
    )
    if su:
        su.role_id = role.id
    else:
        db.add(SalleUser(salle_id=salle_id, user_id=user_id, role_id=role.id))
    return None


def _html_global_users_admin_page(
    db: Session,
    *,
    page_title: str,
    redirect_after: str,
    nav_prefix_html: str,
    back_href: str,
    back_label: str,
) -> HTMLResponse:
    users = db.query(User).order_by(User.id.desc()).limit(200).all()
    uids = [u.id for u in users]
    gmap, smap = _batch_user_roles_maps(db, uids)
    users_rows = "".join(
        [
            "<tr>"
            f"<td>{u.id}</td>"
            f"<td>{html_lib.escape(u.name)}</td>"
            f"<td>{html_lib.escape(u.email or '')}</td>"
            f"<td>{html_lib.escape(u.phone or '')}</td>"
            + _html_user_roles_summary_cell(gmap.get(u.id, []), smap.get(u.id, []))
            + f"<td>{u.is_active}</td>"
            f"<td><a href='/super-admin/users/{u.id}/roles'>Modifier rôles</a></td>"
            "</tr>"
            for u in users
        ]
    )
    ra_esc = html_lib.escape(redirect_after, quote=True)
    salles = db.query(Salle).order_by(Salle.code).all()
    salle_pick = "".join(
        f"<option value='{sl.id}'>{html_lib.escape(sl.code)} — {html_lib.escape(sl.name)}</option>"
        for sl in salles
    )
    inner = (
        nav_prefix_html
        + f"<h1>{html_lib.escape(page_title)}</h1>"
        + "<p>Au moins <b>email</b> ou <b>phone</b> doit être renseigné.</p>"
        + "<form method='post' action='/admin/users'>"
        + f"<input type='hidden' name='redirect_after' value=\"{ra_esc}\"/>"
        + "<p><b>Identité</b></p>"
        + "<input name='name' placeholder='Nom' required/> "
        + "<input name='email' placeholder='Email (optionnel)'/> "
        + "<input name='phone' placeholder='Téléphone (optionnel)'/> "
        + "<input name='password' placeholder='Mot de passe' type='password' required/> "
        + "<label><input type='checkbox' name='is_active' value='1' checked/> Actif</label>"
        + "<p><b>Rôles globaux</b> (optionnel, cumulables)</p>"
        + "<label><input type='checkbox' name='is_admin' value='1'/> Super administrateur (<code>super_admin</code>)</label><br/>"
        + "<label><input type='checkbox' name='global_salle_admin' value='1'/> Admin de salle <em>sans salle au départ</em> (<code>salle_admin</code> global)</label>"
        + "<p><b>Rôle sur une salle</b> (optionnel — une ligne : remplace tout rôle existant sur cette salle pour ce compte)</p>"
        + "<label>Salle <select name='assign_salle_id'><option value=''>— Aucune —</option>"
        + salle_pick
        + "</select></label> "
        + "<label>Rôle <select name='assign_salle_role'>"
        + "<option value=''>—</option>"
        + "<option value='salle_admin'>Admin de cette salle</option>"
        + "<option value='responsable'>Responsable</option>"
        + "<option value='manager'>Gérant</option>"
        + "</select></label>"
        + "<p><button type='submit'>Créer l’utilisateur</button></p>"
        + "</form>"
        + "<table style='margin-top:12px'>"
        + "<tr><th>ID</th><th>Nom</th><th>Email</th><th>Phone</th><th>Rôles</th><th>Actif</th><th>Actions</th></tr>"
        + f"{users_rows}</table>"
        + f"<p><a href='{html_lib.escape(back_href, quote=True)}'>{html_lib.escape(back_label)}</a></p>"
    )
    return HTMLResponse(html_shell(page_title, inner, theme=THEME_SUPER_ADMIN))



def admin_users(db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    return _html_global_users_admin_page(
        db,
        page_title="Utilisateurs globaux",
        redirect_after="/admin/users",
        nav_prefix_html=super_admin_nav_html(),
        back_href="/admin",
        back_label="Retour admin",
    )


def _safe_internal_redirect(url: str, default: str) -> str:
    u = (url or default).strip() or default
    if not u.startswith("/") or u.startswith("//"):
        return default
    return u


@app.post("/admin/users")
def create_user(
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    is_admin: str = Form("0"),
    global_salle_admin: str = Form("0"),
    assign_salle_id: str = Form(""),
    assign_salle_role: str = Form(""),
    redirect_after: str = Form("/admin/users"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    email_v = email.strip() or None
    phone_v = phone.strip() or None

    if not email_v and not phone_v:
        raise HTTPException(status_code=400, detail="Email ou phone requis")
    if not password or not password.strip():
        raise HTTPException(status_code=400, detail="Mot de passe requis")

    assign_sid_raw = (assign_salle_id or "").strip()
    assign_rk = (assign_salle_role or "").strip()
    if (assign_sid_raw and not assign_rk) or (assign_rk and not assign_sid_raw):
        raise HTTPException(
            status_code=400,
            detail="Pour un rôle sur salle, choisissez à la fois la salle et le rôle (ou laissez les deux vides).",
        )
    assign_sid: int | None = None
    if assign_sid_raw:
        if not assign_sid_raw.isdigit():
            raise HTTPException(status_code=400, detail="Identifiant de salle invalide.")
        assign_sid = int(assign_sid_raw)

    user = User(
        name=name.strip(),
        email=email_v,
        phone=phone_v,
        avatar=None,
        password_hash=hash_password(password.strip()),
        is_active=is_active == "1",
    )
    try:
        db.add(user)
        db.flush()

        if is_admin == "1":
            super_role = db.query(Role).filter(Role.key == "super_admin").first()
            if not super_role:
                raise HTTPException(status_code=500, detail="Role super_admin manquant")
            db.add(UserRole(user_id=user.id, role_id=super_role.id))

        if global_salle_admin == "1":
            sar = db.query(Role).filter(Role.key == "salle_admin").first()
            if not sar:
                raise HTTPException(status_code=500, detail="Role salle_admin manquant")
            exists_sa = (
                db.query(UserRole)
                .filter(UserRole.user_id == user.id, UserRole.role_id == sar.id)
                .first()
            )
            if not exists_sa:
                db.add(UserRole(user_id=user.id, role_id=sar.id))

        if assign_sid is not None and assign_rk:
            err = _apply_salle_role_for_user(db, user.id, assign_sid, assign_rk)
            if err:
                db.rollback()
                raise HTTPException(status_code=400, detail=err)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return RedirectResponse(
        url=_safe_internal_redirect(redirect_after, "/admin/users"),
        status_code=303,
    )



def admin_mes_utilisateurs_get(db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    viewer_id = int(_)
    if not can_use_mes_utilisateurs_page(db, viewer_id):
        raise HTTPException(
            status_code=403,
            detail="Réservé aux administrateurs de salle (non super admin global).",
        )
    owned = (
        db.query(User)
        .filter(User.created_by_user_id == viewer_id)
        .order_by(User.id.desc())
        .all()
    )
    rows: list[str] = []
    for u in owned:
        rows.append(
            "<tr>"
            f"<td>{u.id}</td>"
            f"<td>{html_lib.escape(u.name)}</td>"
            f"<td>{html_lib.escape(u.email or '')}</td>"
            f"<td>{html_lib.escape(u.phone or '')}</td>"
            f"<td>{u.is_active}</td>"
            "<td>"
            f"<form method='post' action='/admin/mes-utilisateurs/{u.id}/update' style='display:inline-block'>"
            f"<input name='name' value=\"{html_lib.escape(u.name, quote=True)}\" required size='14'/> "
            "<label><input type='checkbox' name='is_active' value='1' "
            f"{'checked' if u.is_active else ''}/> actif</label> "
            "<input name='password' type='password' placeholder='Nouveau mdp' size='12'/> "
            "<button type='submit'>Enregistrer</button>"
            "</form>"
            "</td>"
            "</tr>"
        )
    table = (
        "<table><tr><th>ID</th><th>Nom</th><th>Email</th><th>Tél.</th><th>Actif</th><th>Modifier</th></tr>"
        + ("".join(rows) if rows else "<tr><td colspan='6'><i>Aucun compte créé pour l’instant.</i></td></tr>")
        + "</table>"
    )
    return admin_page_response(
        "<h1>Mes utilisateurs</h1>"
        "<p>Comptes que <b>vous</b> avez créés. Vous pouvez les assigner comme gérant ou responsable sur vos salles "
        "(formulaire salle ou édition salle). Les comptes créés par le super admin sur votre salle sont gérés depuis "
        "la page utilisateurs de la salle.</p>"
        + table
        + "<h2>Créer un compte</h2>"
        + "<p>Au moins <b>email</b> ou <b>téléphone</b> obligatoire.</p>"
        + "<form method='post' action='/admin/mes-utilisateurs'>"
        + "<input name='name' placeholder='Nom' required/> "
        + "<input name='email' placeholder='Email'/> "
        + "<input name='phone' placeholder='Téléphone'/> "
        + "<input name='password' type='password' placeholder='Mot de passe' required/> "
        + "<label><input type='checkbox' name='is_active' value='1' checked/> Actif</label> "
        + "<button type='submit'>Créer</button>"
        + "</form>"
        + "<p><a href='/admin'>← Retour administration</a></p>",
        title="Mes utilisateurs",
    )


@app.post("/admin/mes-utilisateurs")
def admin_mes_utilisateurs_post(
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    viewer_id = int(_)
    if not can_use_mes_utilisateurs_page(db, viewer_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    email_v = email.strip() or None
    phone_v = phone.strip() or None
    if not email_v and not phone_v:
        raise HTTPException(status_code=400, detail="Email ou téléphone requis")
    if not password.strip():
        raise HTTPException(status_code=400, detail="Mot de passe requis")
    user = User(
        name=name.strip(),
        email=email_v,
        phone=phone_v,
        avatar=None,
        password_hash=hash_password(password.strip()),
        is_active=is_active == "1",
        created_by_user_id=viewer_id,
    )
    try:
        db.add(user)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Email ou téléphone déjà utilisé : {e}")
    return RedirectResponse(url="/admin/mes-utilisateurs", status_code=303)


@app.post("/admin/mes-utilisateurs/{child_user_id}/update")
def admin_mes_utilisateurs_update(
    child_user_id: int,
    name: str = Form(...),
    password: str = Form(""),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    viewer_id = int(_)
    if not can_use_mes_utilisateurs_page(db, viewer_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    child = db.query(User).filter(User.id == child_user_id).first()
    if not child or child.created_by_user_id != viewer_id:
        raise HTTPException(status_code=403, detail="Compte introuvable ou non créé par vous.")
    child.name = name.strip()
    child.is_active = is_active == "1"
    pwd = password.strip()
    if pwd:
        child.password_hash = hash_password(pwd)
    db.add(child)
    db.commit()
    return RedirectResponse(url="/admin/mes-utilisateurs", status_code=303)


def _html_providers_admin_page(
    db: Session,
    *,
    page_title: str,
    redirect_after: str,
    nav_prefix_html: str,
    back_href: str,
    back_label: str,
) -> HTMLResponse:
    # Cases à cocher seules : si décochée, la clé est absente → Form("0") côté POST.
    # Ne pas ajouter de <input type="hidden" value="0"> *après* la case : Starlette
    # garde la dernière valeur pour une clé dupliquée, ce qui forçait toujours 0.
    cfg = db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    if not cfg:
        cfg = PaymentProviderConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    paystack_checked = "checked" if cfg.paystack_enabled else ""
    cinetpay_checked = "checked" if cfg.cinetpay_enabled else ""
    ra_esc = html_lib.escape(redirect_after, quote=True)
    inner = (
        nav_prefix_html
        + f"<h1>{html_lib.escape(page_title)}</h1>"
        + "<p>Contrôle du provider à tenter en priorité. Si Paystack est désactivé, on bascule vers CinetPay.</p>"
        + "<form method='post' action='/admin/providers'>"
        + f"<input type='hidden' name='redirect_after' value=\"{ra_esc}\"/>"
        + f"<label><input type='checkbox' name='paystack_enabled' value='1' {paystack_checked}/> Paystack activé</label><br/>"
        + f"<label><input type='checkbox' name='cinetpay_enabled' value='1' {cinetpay_checked}/> CinetPay activé</label><br/>"
        + "<button type='submit'>Sauvegarder</button>"
        + "</form>"
        + f"<p><a href='{html_lib.escape(back_href, quote=True)}'>{html_lib.escape(back_label)}</a></p>"
    )
    return HTMLResponse(html_shell(page_title, inner, theme=THEME_SUPER_ADMIN))



def admin_providers(db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    return _html_providers_admin_page(
        db,
        page_title="Providers (paiement)",
        redirect_after="/admin/providers",
        nav_prefix_html=super_admin_nav_html(),
        back_href="/admin",
        back_label="Retour admin",
    )


@app.post("/admin/providers")
def update_providers(
    paystack_enabled: str = Form("0"),
    cinetpay_enabled: str = Form("0"),
    redirect_after: str = Form("/admin/providers"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    cfg = db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    if not cfg:
        cfg = PaymentProviderConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    cfg.paystack_enabled = paystack_enabled == "1"
    cfg.cinetpay_enabled = cinetpay_enabled == "1"
    db.commit()
    return RedirectResponse(
        url=_safe_internal_redirect(redirect_after, "/admin/providers"),
        status_code=303,
    )


@app.get("/super-admin")
@app.get("/super-admin/{path:path}")
def super_admin_spa(path: str = "", _: str = Depends(require_super_zone_or_staff)):
    from spa import spa_index_response

    return spa_index_response()



def super_admin_users(
    db: Session = Depends(get_db), _: str = Depends(require_super_admin)
):
    return _html_global_users_admin_page(
        db,
        page_title="Utilisateurs globaux (super admin)",
        redirect_after="/super-admin/users",
        nav_prefix_html=super_admin_nav_html(),
        back_href="/super-admin",
        back_label="Retour espace super admin",
    )


# Rôles modifiables via le formulaire « une salle » : pas de salle_admin ici
# (admin sans salle = section « Admin de salle (global) » ; admin sur une salle = /admin/salles/{id}/users).
_SUPER_ADMIN_EDITABLE_SALLE_ROLES: tuple[tuple[str, str], ...] = (
    ("responsable", "Responsable"),
    ("manager", "Gérant (manager)"),
)


def _html_super_admin_user_roles_editor(
    db: Session,
    target: User,
    *,
    error: str | None = None,
    viewer_is_super: bool = True,
) -> HTMLResponse:
    gmap, _ = _batch_user_roles_maps(db, [target.id])
    gk = sorted(set(gmap.get(target.id, [])))
    has_super = "super_admin" in gk

    su_list = (
        db.query(SalleUser, Salle.code, Salle.name, Role.key)
        .join(Salle, Salle.id == SalleUser.salle_id)
        .join(Role, Role.id == SalleUser.role_id)
        .filter(SalleUser.user_id == target.id)
        .order_by(Salle.code, Role.key)
        .all()
    )

    salles = db.query(Salle).order_by(Salle.code).all()
    salle_opts = "".join(
        f"<option value='{s.id}'>{html_lib.escape(s.code)} — {html_lib.escape(s.name)}</option>"
        for s in salles
    ) or "<option value=''>— Aucune salle —</option>"
    role_opts = "".join(
        f"<option value='{rk}'>{html_lib.escape(lbl)}</option>"
        for rk, lbl in _SUPER_ADMIN_EDITABLE_SALLE_ROLES
    )

    err_block = (
        f"<div class='cp-alert' role='alert'><b>{html_lib.escape(error)}</b></div>"
        if error
        else ""
    )

    global_rows: list[str] = []
    for rk in gk:
        row = f"<li><code>{html_lib.escape(rk)}</code>"
        if viewer_is_super and rk in _SUPER_ADMIN_REMOVABLE_GLOBAL_ROLE_KEYS:
            rk_esc = html_lib.escape(rk, quote=True)
            row += (
                f" <form method='post' action='/super-admin/users/{target.id}/roles/global-remove' "
                "style='display:inline'>"
                f"<input type='hidden' name='role_key' value=\"{rk_esc}\"/>"
                "<button type='submit'>Retirer</button></form>"
            )
        row += "</li>"
        global_rows.append(row)
    if global_rows:
        global_html = (
            "<h2>Rôles globaux (UserRole)</h2>"
            "<ul>"
            + "".join(global_rows)
            + "</ul>"
            + "<p><i>Les rôles non listés ici (ex. hérités ailleurs) ne sont pas retirables depuis cette page.</i></p>"
        )
    else:
        global_html = "<h2>Rôles globaux (UserRole)</h2><p><i>Aucun.</i></p>"

    salle_table_rows: list[str] = []
    for su, scode, sname, rk in su_list:
        salle_table_rows.append(
            "<tr>"
            f"<td>{html_lib.escape(scode)}</td>"
            f"<td>{html_lib.escape(sname)}</td>"
            f"<td>{html_lib.escape(rk)}</td>"
            "<td>"
            f"<form method='post' action='/super-admin/users/{target.id}/roles/salle-remove' style='display:inline'>"
            f"<input type='hidden' name='salle_id' value='{su.salle_id}'/>"
            "<button type='submit'>Retirer</button></form>"
            "</td>"
            "</tr>"
        )
    salle_section = (
        "<h2>Rôles par salle</h2>"
        + (
            "<table><tr><th>Code salle</th><th>Nom</th><th>Rôle</th><th></th></tr>"
            + "".join(salle_table_rows)
            + "</table>"
            if salle_table_rows
            else "<p><i>Aucun rôle sur une salle.</i></p>"
        )
        + "<h3>Ajouter ou remplacer sur une salle (gérant ou responsable)</h3>"
        + "<p><b>Pour un admin de salle <em>sans</em> choisir de salle</b>, utilisez la section "
        + "<strong>« Admin de salle (global) »</strong> plus haut (bouton Accorder) ou retirez le rôle "
        + "dans la liste des rôles globaux.</p>"
        + "<p>Pour un <b>admin de salle sur une salle précise</b> (ligne dans le tableau ci-dessus), "
        + "connectez-vous en super admin et allez sur <code>/admin/salles/&lt;id&gt;/users</code> "
        + "(case « Salle admin » lors de la création d’utilisateur).</p>"
        + "<p>Ici : uniquement <b>gérant</b> ou <b>responsable</b>. Un compte n’a qu’<b>un seul rôle par salle</b> ; "
        + "choisir une salle et un rôle <b>remplace</b> l’assignation existante pour cette salle. "
        + "Un <b>gérant</b> ne peut être lié qu’à <b>une seule</b> salle.</p>"
        + f"<form method='post' action='/super-admin/users/{target.id}/roles/salle-set'>"
        + "<label>Salle <select name='salle_id' required>" + salle_opts + "</select></label> "
        + "<label>Rôle <select name='role_key' required>" + role_opts + "</select></label> "
        + "<button type='submit'>Enregistrer</button></form>"
    )

    super_section = (
        "<h2>Super administrateur (plateforme entière)</h2>"
        + f"<p>État actuel : <b>{'oui' if has_super else 'non'}</b> — retrait via la liste "
        + "<strong>Rôles globaux</strong> ci-dessus.</p>"
        + f"<form method='post' action='/super-admin/users/{target.id}/roles/super-admin' style='display:inline'>"
        + "<input type='hidden' name='grant' value='1'/>"
        + "<button type='submit'>Accorder super_admin</button></form>"
    )

    has_glob_salle_adm = is_global_salle_admin(db, target.id)
    global_salle_admin_section = (
        "<h2>Admin de salle (global) — sans choisir de salle</h2>"
        + "<p><strong>Aucune salle à sélectionner.</strong> Ce rôle donne accès à <code>/admin</code> tout de suite ; "
        + "la personne crée ensuite sa première salle depuis le menu <strong>Salles</strong>.</p>"
        + "<p>C’est le bon choix pour un <b>nouvel</b> admin de salle qui n’a encore aucune salle. "
        + "Pour rattacher quelqu’un comme admin <b>d’une salle déjà existante</b>, utilisez plutôt "
        + "<code>/admin/salles/&lt;id&gt;/users</code> (connecté en super admin).</p>"
        + f"<p>État actuel : <b>{'oui' if has_glob_salle_adm else 'non'}</b> — retrait via la liste "
        + "<strong>Rôles globaux</strong> ci-dessus.</p>"
        + f"<form method='post' action='/super-admin/users/{target.id}/roles/global-salle-admin' style='display:inline'>"
        + "<input type='hidden' name='grant' value='1'/>"
        + "<button type='submit'>Accorder (global)</button></form>"
    )

    staff_global_sections = (
        (global_salle_admin_section + super_section) if viewer_is_super else ""
    )

    body = (
        super_admin_nav_html()
        + f"<h1>Rôles — {html_lib.escape(target.name)}</h1>"
        + f"<p>ID <b>{target.id}</b> · Email : {html_lib.escape(target.email or '—')} · Tél. : "
        f"{html_lib.escape(target.phone or '—')} · Actif : <b>{target.is_active}</b></p>"
        + err_block
        + staff_global_sections
        + global_html
        + salle_section
        + "<p style='margin-top:20px'><a href='/super-admin/users'>← Liste des utilisateurs</a></p>"
    )
    return HTMLResponse(
        html_shell(f"Rôles — {target.name}", body, theme=THEME_SUPER_ADMIN)
    )



@app.get("/super-admin/users/{target_user_id}/roles")
def super_admin_edit_user_roles_get(
    target_user_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    uid = int(_)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not is_global_super_admin(db, uid):
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            raise HTTPException(status_code=403, detail="Profil réservé au super administrateur")
    return _html_super_admin_user_roles_editor(
        db, u, viewer_is_super=is_global_super_admin(db, uid)
    )


@app.post("/super-admin/users/{target_user_id}/roles/super-admin")
def super_admin_edit_user_roles_super_admin(
    target_user_id: int,
    grant: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if grant not in ("0", "1"):
        return _html_super_admin_user_roles_editor(db, u, error="Paramètre grant invalide.")

    super_role = db.query(Role).filter(Role.key == "super_admin").first()
    if not super_role:
        return _html_super_admin_user_roles_editor(db, u, error="Rôle super_admin introuvable en base.")

    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == super_role.id)
        .first()
    )

    if grant == "1":
        if not existing:
            db.add(UserRole(user_id=target_user_id, role_id=super_role.id))
            db.commit()
    else:
        if existing:
            if _count_global_super_admins(db) <= 1:
                return _html_super_admin_user_roles_editor(
                    db,
                    u,
                    error="Impossible de retirer le dernier super administrateur de la plateforme.",
                )
            db.delete(existing)
            db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )


@app.post("/super-admin/users/{target_user_id}/roles/global-salle-admin")
def super_admin_edit_user_roles_global_salle_admin(
    target_user_id: int,
    grant: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if grant not in ("0", "1"):
        return _html_super_admin_user_roles_editor(db, u, error="Paramètre grant invalide.")

    salle_adm_role = db.query(Role).filter(Role.key == "salle_admin").first()
    if not salle_adm_role:
        return _html_super_admin_user_roles_editor(db, u, error="Rôle salle_admin introuvable en base.")

    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == salle_adm_role.id)
        .first()
    )

    if grant == "1":
        if not existing:
            db.add(UserRole(user_id=target_user_id, role_id=salle_adm_role.id))
            db.commit()
    else:
        if existing:
            db.delete(existing)
            db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )


@app.post("/super-admin/users/{target_user_id}/roles/global-remove")
def super_admin_edit_user_roles_global_remove(
    target_user_id: int,
    role_key: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    rk = (role_key or "").strip()
    if rk not in _SUPER_ADMIN_REMOVABLE_GLOBAL_ROLE_KEYS:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Ce rôle global ne peut pas être retiré depuis cette action.",
        )
    role = db.query(Role).filter(Role.key == rk).first()
    if not role:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error=f"Rôle « {rk} » introuvable en base.",
        )
    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == role.id)
        .first()
    )
    if not existing:
        return RedirectResponse(
            url=f"/super-admin/users/{target_user_id}/roles",
            status_code=303,
        )
    if rk == "super_admin" and _count_global_super_admins(db) <= 1:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Impossible de retirer le dernier super administrateur de la plateforme.",
        )
    db.delete(existing)
    db.commit()
    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )


@app.post("/super-admin/users/{target_user_id}/roles/salle-set")
def super_admin_edit_user_roles_salle_set(
    target_user_id: int,
    salle_id: int = Form(...),
    role_key: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    viewer_uid = int(_)
    v_super = is_global_super_admin(db, viewer_uid)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not v_super:
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            return _html_super_admin_user_roles_editor(
                db,
                u,
                error="Profil réservé au super administrateur.",
                viewer_is_super=False,
            )

    allowed_keys = {rk for rk, _ in _SUPER_ADMIN_EDITABLE_SALLE_ROLES}
    if role_key not in allowed_keys:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Rôle de salle non autorisé.",
            viewer_is_super=v_super,
        )

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        return _html_super_admin_user_roles_editor(
            db, u, error="Salle introuvable.", viewer_is_super=v_super
        )

    role = db.query(Role).filter(Role.key == role_key).first()
    if not role:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error=f"Rôle « {role_key} » introuvable en base.",
            viewer_is_super=v_super,
        )

    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    if role_key == "manager" and mgr_role:
        existing_other = (
            db.query(SalleUser)
            .filter(
                SalleUser.user_id == target_user_id,
                SalleUser.role_id == mgr_role.id,
                SalleUser.salle_id != salle_id,
            )
            .first()
        )
        if existing_other:
            return _html_super_admin_user_roles_editor(
                db,
                u,
                error="Ce compte est déjà gérant d’une autre salle ; un gérant n’est lié qu’à une seule salle.",
                viewer_is_super=v_super,
            )

    su = (
        db.query(SalleUser)
        .filter(SalleUser.user_id == target_user_id, SalleUser.salle_id == salle_id)
        .first()
    )
    if su:
        su.role_id = role.id
    else:
        db.add(SalleUser(salle_id=salle_id, user_id=target_user_id, role_id=role.id))
    # Assignation par le super admin : rendre le compte visible pour les admins de salle (règle created_by).
    tu = db.query(User).filter(User.id == target_user_id).first()
    if tu and tu.created_by_user_id is not None and not is_global_super_admin(
        db, tu.created_by_user_id
    ):
        tu.created_by_user_id = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Impossible d’enregistrer (contrainte base de données).",
            viewer_is_super=v_super,
        )

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )


@app.post("/super-admin/users/{target_user_id}/roles/salle-remove")
def super_admin_edit_user_roles_salle_remove(
    target_user_id: int,
    salle_id: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    viewer_uid = int(_)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not is_global_super_admin(db, viewer_uid):
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            raise HTTPException(status_code=403, detail="Profil réservé au super administrateur")

    su = (
        db.query(SalleUser)
        .filter(SalleUser.user_id == target_user_id, SalleUser.salle_id == salle_id)
        .first()
    )
    if su:
        db.delete(su)
        db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )



def super_admin_providers(
    db: Session = Depends(get_db), _: str = Depends(require_super_admin)
):
    return _html_providers_admin_page(
        db,
        page_title="Providers de paiement (super admin)",
        redirect_after="/super-admin/providers",
        nav_prefix_html=super_admin_nav_html(),
        back_href="/super-admin",
        back_label="Retour espace super admin",
    )



def admin_dashboard(db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)

    paystack_flag = paystack_enabled()
    cinetpay_flag = cinetpay_enabled()

    stations_q = db.query(Station).filter(Station.is_active.is_(True))
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles:
            return admin_page_response(
                "<h1>Dashboard admin</h1>"
                + html_hint_empty_scoped_salles(db, user_id)
                + "<p><a href='/admin'>Retour</a></p>",
                title="Dashboard admin",
            )
        stations_q = stations_q.filter(Station.salle_id.in_(allowed_salles))
    stations = stations_q.order_by(Station.id.desc()).all()

    rows = []
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
            "<tr>"
            f"<td>{st.code}</td>"
            f"<td>{st.name}</td>"
            f"<td>{state}</td>"
            f"<td>{remaining_s}</td>"
            f"<td>{sess_for_timer.offer.duration_minutes if sess_for_timer and sess_for_timer.offer else ''}</td>"
            f"<td>{sess_for_timer.offer.price_xof if sess_for_timer and sess_for_timer.offer else ''}</td>"
            f"<td>{sess_for_timer.payment_provider if sess_for_timer else ''}</td>"
            f"<td><a href='/admin/stations/{st.id}/offers'>Offres</a></td>"
            f"<td><a href='/admin/stations/{st.id}/edit'>Edit</a></td>"
            "</tr>"
        )

    return admin_page_response(
        "<h1>Dashboard admin</h1>"
        f"<p>Paystack: <b>{'ON' if paystack_flag else 'OFF'}</b> — CinetPay: <b>{'ON' if cinetpay_flag else 'OFF'}</b></p>"
        "<table>"
        "<tr><th>Code</th><th>Nom</th><th>Etat</th><th>Temps restants</th><th>Duree (min)</th><th>Prix (XOF)</th><th>Provider</th><th>Offres</th><th>Edit</th></tr>"
        f"{''.join(rows)}"
        "</table>"
        "<p><a href='/admin'>Retour</a></p>",
        title="Dashboard admin",
    )



def admin_offers(db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)

    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        allowed_stations = get_allowed_station_ids(db, user_id)
        if not allowed_salles or not allowed_stations:
            offers = []
            return admin_page_response(
                "<h1>Admin Offres</h1>"
                + html_hint_empty_scoped_salles(db, user_id)
                + "<p><a href='/admin'>Retour</a></p>",
                title="Admin offres",
            )

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
    if super_admin:
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
    salles = db.query(Salle).order_by(Salle.id.desc()).all()
    salle_options = "".join([f"<option value='{sl.code}'>{sl.code} - {sl.name}</option>" for sl in salles])

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

    rows = "".join(
        [
            f"<tr>"
            f"<td>{o.id}</td>"
            f"<td>{o.name}</td>"
            f"<td>{station_offer_counts.get(o.id, 0)} stations / {salle_offer_counts.get(o.id, 0)} salles</td>"
            f"<td>{o.duration_minutes}</td>"
            f"<td>{o.price_xof}</td>"
            f"<td>{o.provider}</td>"
            f"<td>{o.is_active}</td>"
            f"<td><a href='/admin/offers/{o.id}/edit'>Edit</a></td>"
            f"<td>"
            f"<form method='post' action='/admin/offers/{o.id}/delete' onsubmit=\"return confirm('Supprimer cette offre ?');\">"
            f"<button type='submit'>Delete</button>"
            f"</form>"
            f"</td>"
            f"</tr>"
            for o in offers
        ]
    )

    return admin_page_response(
        "<h1>Admin Offres</h1>"
        "<p>Les offres sont des <b>templates</b>. Le rattachement se fait via les pages <b>Offres</b> des stations et des salles.</p>"
        "<form method='post' action='/admin/offers'>"
        "<input name='name' placeholder='Nom offre' required/>"
        "<input name='duration_minutes' type='number' placeholder='Duree minutes' required/>"
        "<input name='price_xof' type='number' placeholder='Prix XOF' required/>"
        "<button type='submit'>Creer offre</button></form>"
        "<table><tr><th>ID</th><th>Nom</th><th>Scope</th><th>Duree</th><th>Prix</th><th>Provider</th><th>Active</th><th></th><th></th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>",
        title="Admin offres",
    )


@app.post("/admin/offers")
def create_offer(
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    offer = Offer(
        name=name,
        duration_minutes=duration_minutes,
        price_xof=price_xof,
        provider="paystack",
        station_id=None,
        is_active=True,
    )
    db.add(offer)
    db.commit()
    return RedirectResponse(url="/admin/offers", status_code=303)



def edit_offer(offer_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    active_checked = "checked" if offer.is_active else ""

    return admin_page_response(
        "<h1>Edit Offre</h1>"
        f"<form method='post' action='/admin/offers/{offer_id}/update'>"
        f"<input name='name' placeholder='Nom offre' required value='{html_lib.escape(offer.name, quote=True)}'/>"
        f"<input name='duration_minutes' type='number' placeholder='Duree minutes' required value='{offer.duration_minutes}'/>"
        f"<input name='price_xof' type='number' placeholder='Prix XOF' required value='{offer.price_xof}'/>"
        f"<input type='hidden' name='is_active' value='0'/>"
        f"<label><input type='checkbox' name='is_active' value='1' {active_checked}/> Active</label>"
        f"<button type='submit'>Mettre à jour</button>"
        f"</form>"
        f"<p><a href='/admin/offers'>Retour</a></p>",
        title="Modifier offre",
    )


@app.post("/admin/offers/{offer_id}/update")
def update_offer(
    offer_id: int,
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    offer.name = name
    offer.duration_minutes = duration_minutes
    offer.price_xof = price_xof
    offer.provider = "paystack"
    offer.station_id = None
    offer.is_active = is_active == "1"
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")
    return RedirectResponse(url="/admin/offers", status_code=303)


@app.post("/admin/offers/{offer_id}/delete")
def delete_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    # Comportement souhaité:
    # - l'offre disparaît immédiatement des stations (liaisons supprimées)
    # - on évite de casser les FK vers game_sessions/session_extensions en faisant
    #   un soft delete (is_active=false) au lieu de supprimer physiquement la ligne.
    db.query(StationOffer).filter(StationOffer.offer_id == offer_id).delete()
    db.query(SalleOffer).filter(SalleOffer.offer_id == offer_id).delete()
    offer.is_active = False
    db.commit()
    return RedirectResponse(url="/admin/offers", status_code=303)


@app.post("/admin/offers/clone-global-to-all")
def clone_global_offers_to_all(
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    target_stations = db.query(Station).filter(Station.is_active.is_(True)).all()
    if not target_stations:
        return admin_page_response(
            "<h1>Aucune station active</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0
    for st in target_stations:
        for go in global_offers:
            existing = (
                db.query(StationOffer)
                .filter(
                    and_(
                        StationOffer.station_id == st.id,
                        StationOffer.offer_id == go.id,
                    )
                )
                .first()
            )
            if not existing:
                db.add(StationOffer(station_id=st.id, offer_id=go.id, is_active=True))
                created += 1
            elif override and not existing.is_active:
                existing.is_active = True
                updated += 1

    db.commit()
    return admin_page_response(
        "<h1>Dupliquer terminé</h1>"
        f"<p>Rattachements créés (station_offers): {created}</p>"
        f"<p>Rattachements réactivés: {updated}</p>"
        "<p><a href='/admin/offers'>Retour</a></p>",
        title="Offres",
    )


@app.post("/admin/offers/clone-global-to-station/{station_id}")
def clone_global_offers_to_station(
    station_id: int,
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0

    for go in global_offers:
        existing = (
            db.query(StationOffer)
            .filter(and_(StationOffer.station_id == station_id, StationOffer.offer_id == go.id))
            .first()
        )
        if not existing:
            db.add(StationOffer(station_id=station_id, offer_id=go.id, is_active=True))
            created += 1
        elif override and not existing.is_active:
            existing.is_active = True
            updated += 1

    db.commit()
    return RedirectResponse(url=f"/admin/stations/{station_id}/offers", status_code=303)


@app.post("/admin/offers/clone-global-to-salle")
def clone_global_offers_to_salle(
    salle_code: str = Form(...),
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    salle = db.query(Salle).filter(Salle.code == salle_code).first()
    if not salle:
        return admin_page_response(
            "<h1>Salle introuvable</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle.id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0

    # "Global -> salle" = rattacher les templates à la salle via salle_offers.
    # Les stations de cette salle recevront automatiquement les offres (car station_page regarde salle_offers).
    for go in global_offers:
        existing = (
            db.query(SalleOffer)
            .filter(
                and_(
                    SalleOffer.salle_id == salle.id,
                    SalleOffer.offer_id == go.id,
                )
            )
            .first()
        )
        if not existing:
            db.add(SalleOffer(salle_id=salle.id, offer_id=go.id, is_active=True))
            created += 1
        elif override and not existing.is_active:
            existing.is_active = True
            updated += 1

    db.commit()
    return admin_page_response(
        "<h1>Dupliquer terminé</h1>"
        f"<p>Salle: {html_lib.escape(salle_code)}</p>"
        f"<p>Rattachements créés (salle_offers): {created}</p>"
        f"<p>Rattachements réactivés: {updated}</p>"
        "<p><a href='/admin/offers'>Retour</a></p>",
        title="Offres",
    )



def admin_stations(db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if super_admin:
        stations = db.query(Station).order_by(Station.id.desc()).all()
        salles = db.query(Salle).order_by(Salle.id.desc()).all()
    else:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles:
            return admin_page_response(
                "<h1>Admin Stations</h1>"
                + html_hint_empty_scoped_salles(db, user_id)
                + "<p><a href='/admin'>Retour</a></p>",
                title="Stations",
            )
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
    rows_parts = []
    for s in stations:
        salle_code = salle_by_id.get(s.salle_id, "")
        rows_parts.append(
            "<tr>"
            f"<td>{s.id}</td>"
            f"<td>{s.code}</td>"
            f"<td>{s.name}</td>"
            f"<td>{s.broadlink_ip}</td>"
            f"<td>{salle_code}</td>"
            f"<td>"
            f"<form method='post' action='/admin/stations/{s.id}/reset-sessions' onsubmit=\"return confirm('Supprimer les sessions pending/active de cette station ?');\">"
            f"<button type='submit'>Reset sessions</button>"
            f"</form>"
            f"</td>"
            f"<td><a href='/admin/stations/{s.id}/offers'>Offres</a></td>"
            f"<td><a href='/admin/stations/{s.id}/edit'>Edit</a></td>"
            f"<td>"
            f"<form method='post' action='/admin/stations/{s.id}/delete' onsubmit=\"return confirm('Supprimer cette station ?');\">"
            f"<button type='submit'>Delete</button>"
            f"</form>"
            f"</td>"
            "</tr>"
        )
    rows = "".join(rows_parts)

    salle_options = "<option value=''>AUCUNE</option>" + "".join(
        [
            f"<option value='{sl.code}'>{sl.code} - {sl.name}</option>"
            for sl in salles
        ]
    )
    return admin_page_response(
        "<h1>Admin Stations</h1>"
        "<form method='post' action='/admin/stations'>"
        "<input name='code' placeholder='station-2' required/>"
        "<input name='name' placeholder='Nom station' required/>"
        "<input name='broadlink_ip' placeholder='192.168.1.250' required/>"
        "<input name='ir_code_hdmi1' placeholder='code hdmi1' required/>"
        "<input name='ir_code_hdmi2' placeholder='code hdmi2' required/>"
        f"<select name='salle_code'>{salle_options}</select>"
        "<input type='hidden' name='is_active' value='0'/>"
        "<label><input type='checkbox' name='is_active' value='1' checked/> Active</label>"
        "<button type='submit'>Creer station</button></form>"
        "<table><tr><th>ID</th><th>Code</th><th>Nom</th><th>IP</th><th>Salle</th><th>Sessions</th><th>Offres</th><th></th><th></th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>",
        title="Stations",
    )


@app.post("/admin/stations")
def create_station(
    code: str = Form(...),
    name: str = Form(...),
    broadlink_ip: str = Form(...),
    ir_code_hdmi1: str = Form(...),
    ir_code_hdmi2: str = Form(...),
    salle_code: str = Form(""),
    is_active: str = Form("1"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    existing = db.query(Station).filter(Station.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Code station deja utilise")
    salle_id = None
    if salle_code:
        salle = db.query(Salle).filter(Salle.code == salle_code).first()
        if not salle:
            raise HTTPException(status_code=404, detail="Salle introuvable")
        if not super_admin:
            allowed_salles = get_scoped_salle_ids(db, user_id)
            if not allowed_salles or salle.id not in allowed_salles:
                raise HTTPException(status_code=403, detail="Accès refusé")
        salle_id = salle.id
    else:
        if not super_admin:
            raise HTTPException(status_code=403, detail="Salle requise pour un admin scopé")
    station = Station(
        code=code,
        name=name,
        broadlink_ip=broadlink_ip,
        ir_code_hdmi1=ir_code_hdmi1,
        ir_code_hdmi2=ir_code_hdmi2,
        salle_id=salle_id,
        is_active=is_active == "1",
    )
    db.add(station)
    db.commit()
    return RedirectResponse(url="/admin/stations", status_code=303)



def edit_station(station_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    allowed_salles = None
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    salles_q = db.query(Salle)
    if not super_admin:
        salles_q = salles_q.filter(Salle.id.in_(allowed_salles))
    salles = salles_q.order_by(Salle.id.desc()).all()
    salle_by_id = {sl.id: sl for sl in salles}
    current_salle_code = ""
    if station.salle_id and station.salle_id in salle_by_id:
        current_salle_code = salle_by_id[station.salle_id].code

    salle_options = "<option value=''>AUCUNE</option>" + "".join(
        [
            (
                f"<option value='{sl.code}' selected>{sl.code} - {sl.name}</option>"
                if sl.code == current_salle_code
                else f"<option value='{sl.code}'>{sl.code} - {sl.name}</option>"
            )
            for sl in salles
        ]
    )

    active_checked = "checked" if station.is_active else ""

    return admin_page_response(
        "<h1>Edit Station</h1>"
        f"<form method='post' action='/admin/stations/{station_id}/update'>"
        f"<input name='code' required value='{html_lib.escape(station.code, quote=True)}'/>"
        f"<input name='name' required value='{html_lib.escape(station.name, quote=True)}'/>"
        f"<input name='broadlink_ip' required value='{html_lib.escape(station.broadlink_ip, quote=True)}'/>"
        f"<input name='ir_code_hdmi1' required value='{html_lib.escape(station.ir_code_hdmi1 or '', quote=True)}'/>"
        f"<input name='ir_code_hdmi2' required value='{html_lib.escape(station.ir_code_hdmi2 or '', quote=True)}'/>"
        f"<select name='salle_code'>{salle_options}</select>"
        "<input type='hidden' name='is_active' value='0'/>"
        f"<label><input type='checkbox' name='is_active' value='1' {active_checked}/> Active</label>"
        "<button type='submit'>Mettre à jour</button>"
        "</form>"
        "<p><a href='/admin/stations'>Retour</a></p>",
        title="Modifier station",
    )


@app.post("/admin/stations/{station_id}/update")
def update_station(
    station_id: int,
    code: str = Form(...),
    name: str = Form(...),
    broadlink_ip: str = Form(...),
    ir_code_hdmi1: str = Form(...),
    ir_code_hdmi2: str = Form(...),
    salle_code: str = Form(""),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    allowed_salles = None
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        if not salle_code:
            raise HTTPException(status_code=403, detail="Salle requise")

    station.salle_id = None
    if salle_code:
        salle = db.query(Salle).filter(Salle.code == salle_code).first()
        if not salle:
            raise HTTPException(status_code=404, detail="Salle introuvable")
        if not super_admin and salle.id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        station.salle_id = salle.id

    station.code = code
    station.name = name
    station.broadlink_ip = broadlink_ip
    station.ir_code_hdmi1 = ir_code_hdmi1
    station.ir_code_hdmi2 = ir_code_hdmi2
    station.is_active = is_active == "1"

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return RedirectResponse(url="/admin/stations", status_code=303)


@app.post("/admin/stations/{station_id}/reset-sessions")
def reset_station_sessions(
    station_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    active_ids_rows = (
        db.query(GameSession.id)
        .filter(
            GameSession.station_id == station_id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .all()
    )
    active_session_ids = [r[0] for r in active_ids_rows]
    if active_session_ids:
        db.query(EventLog).filter(EventLog.session_id.in_(active_session_ids)).delete(synchronize_session=False)
        db.query(SessionExtension).filter(SessionExtension.session_id.in_(active_session_ids)).delete(synchronize_session=False)
        db.query(GameSession).filter(GameSession.id.in_(active_session_ids)).delete(synchronize_session=False)
        db.commit()

    return RedirectResponse(url="/admin/stations", status_code=303)


@app.post("/admin/stations/{station_id}/delete")
def delete_station(station_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    used = db.query(GameSession).filter(GameSession.station_id == station_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="Station utilisée par des sessions : suppression refusée")

    db.query(StationOffer).filter(StationOffer.station_id == station_id).delete()
    db.delete(station)
    db.commit()
    return RedirectResponse(url="/admin/stations", status_code=303)



def admin_station_offers(station_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)

    if super_admin:
        offers = (
            db.query(Offer)
            .filter(Offer.is_active.is_(True))
            .order_by(Offer.duration_minutes.asc(), Offer.price_xof.asc(), Offer.id.asc())
            .all()
        )
    else:
        if station.salle_id is None:
            raise HTTPException(status_code=403, detail="Accès refusé")
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        offers = []
        if allowed_offer_ids:
            offers = (
                db.query(Offer)
                .filter(Offer.id.in_(list(allowed_offer_ids)))
                .filter(Offer.is_active.is_(True))
                .order_by(Offer.duration_minutes.asc(), Offer.price_xof.asc(), Offer.id.asc())
                .all()
            )
    attached_offer_ids = {
        so.offer_id
        for so in db.query(StationOffer).filter(StationOffer.station_id == station_id, StationOffer.is_active.is_(True)).all()
    }

    offers_rows = "".join(
        [
            f"<tr>"
            f"<td>{o.id}</td>"
            f"<td>{o.name}</td>"
            f"<td>{o.duration_minutes}</td>"
            f"<td>{o.price_xof}</td>"
            f"<td>{o.provider}</td>"
            f"<td><input type='checkbox' name='offer_ids' value='{o.id}' {'checked' if o.id in attached_offer_ids else ''} {'disabled' if not o.is_active else ''}/></td>"
            f"</tr>"
            for o in offers
        ]
    )

    return admin_page_response(
        "<h1>Offres de la station</h1>"
        f"<p>Station: {html_lib.escape(station.code)} — {html_lib.escape(station.name)}</p>"
        f"<form method='post' action='/admin/offers/clone-global-to-station/{station_id}' style='margin-bottom:12px'>"
        "<label><input type='checkbox' name='override_existing' value='1'/> Remplacer si existe</label>"
        "<button type='submit'>Dupliquer offres globales vers cette station</button>"
        "</form>"
        f"<form method='post' action='/admin/stations/{station_id}/offers'>"
        "<table><tr><th>ID</th><th>Nom</th><th>Duree</th><th>Prix</th><th>Provider</th><th>Attacher</th></tr>"
        f"{offers_rows}</table>"
        "<button type='submit' style='margin-top:12px'>Enregistrer</button></form>"
        "<p><a href='/admin/stations'>Retour</a></p>",
        title="Offres station",
    )


@app.post("/admin/stations/{station_id}/offers")
async def admin_station_offers_post(station_id: int, request: Request, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        if station.salle_id is None:
            raise HTTPException(status_code=403, detail="Accès refusé")
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    form = await request.form()
    raw_ids = form.getlist("offer_ids")
    offer_ids = [int(x) for x in raw_ids if str(x).isdigit()]

    if not super_admin:
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        offer_ids = [oid for oid in offer_ids if oid in allowed_offer_ids]

    # Vérifie que les offres existent et sont actives (sinon on ignore).
    active_ids = {
        o.id
        for o in db.query(Offer).filter(Offer.id.in_(offer_ids), Offer.is_active.is_(True)).all()
    }

    db.query(StationOffer).filter(StationOffer.station_id == station_id).delete()
    for oid in active_ids:
        db.add(StationOffer(station_id=station_id, offer_id=oid, is_active=True))
    db.commit()
    return RedirectResponse(url=f"/admin/stations/{station_id}/offers", status_code=303)



def admin_salles(db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if super_admin:
        salles = db.query(Salle).order_by(Salle.id.desc()).all()
    else:
        allowed_salle_ids = get_scoped_salle_ids(db, user_id)
        if allowed_salle_ids:
            salles = (
                db.query(Salle)
                .filter(Salle.id.in_(allowed_salle_ids))
                .order_by(Salle.id.desc())
                .all()
            )
        elif is_global_salle_admin(db, user_id):
            salles = []
        else:
            raise HTTPException(status_code=403, detail="Accès refusé")

    manager_role_key = "manager"
    responsable_role_key = "responsable"
    salle_ids = [s.id for s in salles]
    salle_admin_ids = (
        effective_salle_admin_salle_ids(db, user_id) if not super_admin else set(salle_ids)
    )

    names_by_salle_role: dict[tuple[int, str], list[str]] = {}
    if salle_ids:
        assignments = (
            db.query(SalleUser.salle_id, User.name, Role.key)
            .join(User, User.id == SalleUser.user_id)
            .join(Role, Role.id == SalleUser.role_id)
            .filter(SalleUser.salle_id.in_(salle_ids))
            .filter(Role.key.in_((manager_role_key, responsable_role_key)))
            .all()
        )
        for salle_id, user_name, role_key in assignments:
            names_by_salle_role.setdefault((salle_id, role_key), []).append(user_name)

    if super_admin:
        users = db.query(User).filter(User.is_active.is_(True)).order_by(User.id.desc()).all()
    else:
        pool = _user_ids_created_by_salle_admin(db, user_id)
        if pool:
            users = (
                db.query(User)
                .filter(User.id.in_(pool), User.is_active.is_(True))
                .order_by(User.id.desc())
                .all()
            )
        else:
            users = []
    manager_choices = "".join(
        [
            f"<label><input type='checkbox' name='manager_user_ids' value='{u.id}'/> {html_lib.escape(u.name)} ({u.id})</label><br/>"
            for u in users
        ]
    )
    responsable_choices = "".join(
        [
            f"<label><input type='checkbox' name='responsable_user_ids' value='{u.id}'/> {html_lib.escape(u.name)} ({u.id})</label><br/>"
            for u in users
        ]
    )

    row_parts: list[str] = []
    for sl in salles:
        can_edit_salle = super_admin or sl.id in salle_admin_ids
        edit_cell = (
            f'<a href="/admin/salles/{sl.id}/edit">Edit</a>' if can_edit_salle else ""
        )
        delete_cell = (
            f'<form method="post" action="/admin/salles/{sl.id}/delete">'
            f'<button type="submit">Delete</button></form>'
            if can_edit_salle
            else ""
        )
        row_parts.append(
            "<tr>"
            f"<td>{sl.id}</td>"
            f"<td>{sl.code}</td>"
            f"<td>{sl.name}</td>"
            f"<td>{', '.join(names_by_salle_role.get((sl.id, manager_role_key), []))}</td>"
            f"<td>{', '.join(names_by_salle_role.get((sl.id, responsable_role_key), []))}</td>"
            f"<td><a href='/admin/salles/{sl.id}/offers'>Offres</a></td>"
            f"<td><a href='/admin/salles/{sl.id}/stations'>Stations</a></td>"
            f"<td>{edit_cell}</td>"
            f"<td><a href='/admin/salles/{sl.id}/users'>Users</a></td>"
            f"<td>{delete_cell}</td>"
            "</tr>"
        )
    rows = "".join(row_parts)
    pool_hint = ""
    if not super_admin and not users:
        pool_hint = (
            "<p><i>Pour assigner des gérants/responsables à la création, ajoutez d’abord des comptes via "
            "<a href='/admin/mes-utilisateurs'>Mes utilisateurs</a>.</i></p>"
        )
    return admin_page_response(
        "<h1>Admin Salles</h1>"
        f"{pool_hint}"
        "<form method='post' action='/admin/salles'>"
        "<input name='code' placeholder='salle-1' required/>"
        "<input name='name' placeholder='Nom salle' required/>"
        "<input name='latitude' placeholder='Latitude'/>"
        "<input name='longitude' placeholder='Longitude'/>"
        "<div><b>Gérants</b></div>"
        f"{manager_choices}"
        "<div style='margin-top:8px'><b>Responsables</b></div>"
        f"{responsable_choices}"
        "<button type='submit'>Creer salle</button></form>"
        "<table><tr><th>ID</th><th>Code</th><th>Nom</th><th>Gérant</th><th>Responsable</th><th>Offres</th><th>Stations</th><th>Edit</th><th>Users</th><th></th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>",
        title="Salles",
    )



def admin_salle_stations(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    stations = (
        db.query(Station)
        .filter(Station.salle_id == salle_id)
        .order_by(Station.id.desc())
        .all()
    )

    rows = "".join(
        [
            "<tr>"
            f"<td>{s.id}</td>"
            f"<td>{s.code}</td>"
            f"<td>{s.name}</td>"
            f"<td>{s.broadlink_ip}</td>"
            f"<td>{s.is_active}</td>"
            f"<td><a href='/admin/stations/{s.id}/offers'>Offres</a></td>"
            f"<td><a href='/admin/stations/{s.id}/edit'>Edit</a></td>"
            f"<td>"
            f"<form method='post' action='/admin/stations/{s.id}/reset-sessions' onsubmit=\"return confirm('Supprimer les sessions pending/active de cette station ?');\">"
            f"<button type='submit'>Reset sessions</button>"
            f"</form>"
            f"</td>"
            "</tr>"
            for s in stations
        ]
    )

    return admin_page_response(
        f"<h1>Stations — {html_lib.escape(salle.code)}</h1>"
        f"<p>{html_lib.escape(salle.name)}</p>"
        f"<form method='post' action='/admin/salles/{salle_id}/reset-sessions' onsubmit=\"return confirm('Supprimer les sessions pending/active pour toutes les stations de cette salle ?');\">"
        "<button type='submit' style='margin-bottom:12px'>Reset sessions (salle)</button>"
        "</form>"
        "<table><tr><th>ID</th><th>Code</th><th>Nom</th><th>IP</th><th>Actif</th><th>Offres</th><th>Edit</th><th>Reset</th></tr>"
        f"{rows}</table>"
        "<p><a href='/admin/salles'>Retour</a></p>",
        title=f"Stations {salle.code}",
    )


@app.post("/admin/salles/{salle_id}/reset-sessions")
def reset_salle_sessions(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    station_ids = [r[0] for r in db.query(Station.id).filter(Station.salle_id == salle_id).all()]
    if not station_ids:
        return RedirectResponse(url=f"/admin/salles/{salle_id}/stations", status_code=303)

    session_ids_rows = (
        db.query(GameSession.id)
        .filter(
            GameSession.station_id.in_(station_ids),
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .all()
    )
    session_ids = [r[0] for r in session_ids_rows]

    if session_ids:
        db.query(EventLog).filter(EventLog.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(SessionExtension).filter(SessionExtension.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(GameSession).filter(GameSession.id.in_(session_ids)).delete(synchronize_session=False)
        db.commit()

    return RedirectResponse(url=f"/admin/salles/{salle_id}/stations", status_code=303)


def _get_role_ids(db: Session, role_keys: list[str]) -> dict[str, int]:
    roles = db.query(Role).filter(Role.key.in_(role_keys)).all()
    return {r.key: r.id for r in roles}


def _find_or_create_user(
    db: Session,
    name: str,
    email: str | None,
    phone: str | None,
    password: str,
    is_active: bool,
    *,
    created_by_user_id: int | None = None,
) -> User:
    email_v = email.strip() if email else None
    phone_v = phone.strip() if phone else None
    user = None
    if phone_v:
        user = db.query(User).filter(User.phone == phone_v).first()
    if not user and email_v:
        user = db.query(User).filter(User.email == email_v).first()

    if user:
        # On ne modifie pas le password si l'utilisateur existe (pour éviter de casser des identifiants).
        # L'UI admin peut gérer explicitement si besoin plus tard.
        return user

    user = User(
        name=name.strip(),
        email=email_v,
        phone=phone_v,
        avatar=None,
        password_hash=hash_password(password.strip()),
        is_active=is_active,
        created_by_user_id=created_by_user_id,
    )
    db.add(user)
    db.flush()
    return user



def admin_salle_users(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin and salle_id not in get_scoped_salle_ids(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    roles_wanted = ["manager", "responsable"]
    role_ids = _get_role_ids(db, roles_wanted + (["salle_admin"] if super_admin else []))
    can_assign_responsable = super_admin or is_effective_salle_admin_for_salle(
        db, user_id, salle_id
    )

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_rows = (
        db.query(User, Role.key)
        .join(SalleUser, SalleUser.user_id == User.id)
        .join(Role, Role.id == SalleUser.role_id)
        .filter(SalleUser.salle_id == salle_id)
        .filter(Role.key.in_(roles_wanted))
        .all()
    )
    if not super_admin and is_effective_salle_admin_for_salle(db, user_id, salle_id):
        user_rows = [
            (u, rk)
            for (u, rk) in user_rows
            if user_visible_to_salle_admin(db, user_id, u, salle_id)
        ]

    users_list_rows = "".join(
        [
            "<tr>"
            f"<td>{u.id}</td>"
            f"<td>{u.name}</td>"
            f"<td>{u.email or ''}</td>"
            f"<td>{u.phone or ''}</td>"
            f"<td>{rk}</td>"
            "</tr>"
            for (u, rk) in user_rows
        ]
    )

    manager_checkbox = "".join(
        ["<label><input type='checkbox' name='make_manager' value='1'/> Gérant</label>"]
    )
    responsable_checkbox = ""
    if can_assign_responsable:
        responsable_checkbox = (
            "<label><input type='checkbox' name='make_responsable' value='1'/> Responsable</label>"
        )

    salle_admin_checkbox = ""
    if super_admin and "salle_admin" in role_ids:
        salle_admin_checkbox = "<label><input type='checkbox' name='make_salle_admin' value='1'/> Salle admin</label><br/>"

    vis_note = ""
    if not super_admin and is_effective_salle_admin_for_salle(db, user_id, salle_id):
        vis_note = (
            "<p><small>Comptes visibles : ceux que <b>vous</b> avez créés (via <a href='/admin/mes-utilisateurs'>Mes utilisateurs</a>), "
            "sans créateur en base (ancien/import), ou créés par le <b>super administrateur</b>. "
            "Pour de nouveaux gérants/responsables, créez d’abord le compte dans « Mes utilisateurs ».</small></p>"
        )
    return admin_page_response(
        f"<h1>Users — {html_lib.escape(salle.code)} ({html_lib.escape(salle.name)})</h1>"
        f"{vis_note}"
        "<h2>Gérants / Responsables</h2>"
        "<p><small>Un <b>gérant</b> ne peut être lié qu’à <b>une seule</b> salle. "
        "Un <b>responsable</b> peut l’être à plusieurs salles.</small></p>"
        "<table><tr><th>ID</th><th>Nom</th><th>Email</th><th>Phone</th><th>Rôle</th></tr>"
        f"{users_list_rows}</table>"
        "<h2>Créer un user</h2>"
        f"<form method='post' action='/admin/salles/{salle_id}/users'>"
        "<input name='name' placeholder='Nom' required/>"
        "<input name='email' placeholder='Email (optionnel)'/>"
        "<input name='phone' placeholder='Téléphone (optionnel)'/>"
        "<input name='password' placeholder='Mot de passe' type='password' required/>"
        "<label><input type='checkbox' name='is_active' value='1' checked/> Actif</label><br/>"
        f"{manager_checkbox}"
        f"{responsable_checkbox}<br/>"
        f"{salle_admin_checkbox}"
        "<button type='submit'>Créer & assigner</button>"
        "</form>"
        "<p><a href='/admin/salles'>Retour</a></p>",
        title="Utilisateurs salle",
    )


@app.post("/admin/salles/{salle_id}/users")
def admin_salle_users_post(
    salle_id: int,
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    make_manager: str = Form("0"),
    make_responsable: str = Form("0"),
    make_salle_admin: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin and salle_id not in get_scoped_salle_ids(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    roles_to_assign: list[str] = []
    if make_manager == "1":
        roles_to_assign.append("manager")
    if make_responsable == "1":
        if not super_admin and not is_effective_salle_admin_for_salle(db, user_id, salle_id):
            raise HTTPException(
                status_code=403,
                detail="Seul l’admin de salle ou le super-admin peut nommer un responsable.",
            )
        roles_to_assign.append("responsable")
    if super_admin and make_salle_admin == "1":
        roles_to_assign.append("salle_admin")

    if not roles_to_assign:
        raise HTTPException(status_code=400, detail="Choisissez au moins un rôle")

    role_ids = _get_role_ids(db, roles_to_assign)
    missing = [rk for rk in roles_to_assign if rk not in role_ids]
    if missing:
        raise HTTPException(status_code=500, detail=f"Rôles manquants: {missing}")

    user = _find_or_create_user(
        db=db,
        name=name,
        email=email or None,
        phone=phone or None,
        password=password,
        is_active=is_active == "1",
        created_by_user_id=user_id,
    )

    if not super_admin and not _salle_admin_may_use_existing_user_for_assignment(db, user_id, user):
        raise HTTPException(
            status_code=400,
            detail="Ce compte existe déjà et n’a pas été créé par vous. Créez un nouveau compte dans « Mes utilisateurs » "
            "ou utilisez un compte créé par le super administrateur.",
        )

    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    if make_manager == "1" and mgr_role:
        existing_other = (
            db.query(SalleUser)
            .filter(SalleUser.user_id == user.id, SalleUser.role_id == mgr_role.id)
            .filter(SalleUser.salle_id != salle_id)
            .first()
        )
        if existing_other:
            raise HTTPException(
                status_code=400,
                detail="Ce compte est déjà gérant d'une autre salle ; un gérant n'est lié qu'à une seule salle.",
            )

    for rk in roles_to_assign:
        rid = role_ids[rk]
        exists = (
            db.query(SalleUser)
            .filter(SalleUser.salle_id == salle_id)
            .filter(SalleUser.user_id == user.id)
            .filter(SalleUser.role_id == rid)
            .first()
        )
        if not exists:
            db.add(SalleUser(salle_id=salle_id, user_id=user.id, role_id=rid))

    db.commit()
    return RedirectResponse(url=f"/admin/salles/{salle_id}/users", status_code=303)


@app.post("/admin/salles")
async def create_salle(
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    form = await request.form()
    code = (form.get("code") or "").strip()
    name = (form.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")

    latitude_raw = (form.get("latitude") or "").strip()
    longitude_raw = (form.get("longitude") or "").strip()
    lat_v = float(latitude_raw) if latitude_raw else None
    lon_v = float(longitude_raw) if longitude_raw else None

    raw_manager_ids = form.getlist("manager_user_ids")
    raw_responsable_ids = form.getlist("responsable_user_ids")
    manager_ids = [int(x) for x in raw_manager_ids if str(x).isdigit()]
    responsable_ids = [int(x) for x in raw_responsable_ids if str(x).isdigit()]

    # Admin de salle : rôle global (user_roles) ou déjà admin d’au moins une salle ;
    # gérants/responsables = uniquement des comptes créés par lui (pool filtré).
    if not super_admin:
        has_cap = is_global_salle_admin(db, user_id) or (
            db.query(SalleUser)
            .join(Role, Role.id == SalleUser.role_id)
            .filter(SalleUser.user_id == user_id)
            .filter(Role.key == "salle_admin")
            .first()
            is not None
        )
        if not has_cap:
            raise HTTPException(status_code=403, detail="Accès refusé")
        pool = _user_ids_created_by_salle_admin(db, user_id)
        manager_ids = [uid for uid in manager_ids if uid in pool]
        responsable_ids = [uid for uid in responsable_ids if uid in pool]

    exists = db.query(Salle).filter(Salle.code == code).first()
    if exists:
        raise HTTPException(status_code=400, detail="Code salle deja utilise")

    manager_role = db.query(Role).filter(Role.key == "manager").first()
    responsable_role = db.query(Role).filter(Role.key == "responsable").first()
    if not manager_role or not responsable_role:
        raise HTTPException(status_code=500, detail="Roles manager/responsable manquants")

    # On filtre au passage pour éviter les clés étrangères invalides.
    valid_user_ids = {
        r[0]
        for r in db.query(User.id)
        .filter(User.id.in_(manager_ids + responsable_ids))
        .all()
    }
    manager_ids = [uid for uid in manager_ids if uid in valid_user_ids]
    responsable_ids = [uid for uid in responsable_ids if uid in valid_user_ids]

    salle = Salle(
        code=code,
        name=name,
        latitude=lat_v,
        longitude=lon_v,
    )
    db.add(salle)
    try:
        db.flush()
        salle_admin_role = db.query(Role).filter(Role.key == "salle_admin").first()
        # Le créateur non-super doit devenir `salle_admin` sur la salle créée.
        if salle_admin_role and not super_admin:
            db.add(SalleUser(salle_id=salle.id, user_id=user_id, role_id=salle_admin_role.id))
        for uid in manager_ids:
            db.add(SalleUser(salle_id=salle.id, user_id=uid, role_id=manager_role.id))
        for uid in responsable_ids:
            db.add(
                SalleUser(salle_id=salle.id, user_id=uid, role_id=responsable_role.id)
            )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")
    return RedirectResponse(url="/admin/salles", status_code=303)



def edit_salle(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin and not is_effective_salle_admin_for_salle(db, user_id, salle_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    manager_role = db.query(Role).filter(Role.key == "manager").first()
    responsable_role = db.query(Role).filter(Role.key == "responsable").first()
    if not manager_role or not responsable_role:
        raise HTTPException(status_code=500, detail="Roles manager/responsable manquants")

    assigned_manager_ids = {
        r[0]
        for r in db.query(SalleUser.user_id)
        .filter(SalleUser.salle_id == salle_id, SalleUser.role_id == manager_role.id)
        .all()
    }
    assigned_responsable_ids = {
        r[0]
        for r in db.query(SalleUser.user_id)
        .filter(
            SalleUser.salle_id == salle_id, SalleUser.role_id == responsable_role.id
        )
        .all()
    }

    pick_ids = _user_ids_allowed_for_manager_responsable_form(
        db, user_id, salle_id, super_admin=super_admin
    )
    if pick_ids is None:
        users = db.query(User).filter(User.is_active.is_(True)).order_by(User.id.desc()).all()
    elif pick_ids:
        users = (
            db.query(User)
            .filter(User.id.in_(pick_ids), User.is_active.is_(True))
            .order_by(User.id.desc())
            .all()
        )
    else:
        users = []
    manager_choices = "".join(
        [
            f"<label><input type='checkbox' name='manager_user_ids' value='{u.id}' "
            f"{'checked' if u.id in assigned_manager_ids else ''}/> "
            f"{html_lib.escape(u.name)} ({u.id})</label><br/>"
            for u in users
        ]
    )
    responsable_choices = "".join(
        [
            f"<label><input type='checkbox' name='responsable_user_ids' value='{u.id}' "
            f"{'checked' if u.id in assigned_responsable_ids else ''}/> "
            f"{html_lib.escape(u.name)} ({u.id})</label><br/>"
            for u in users
        ]
    )

    return admin_page_response(
        "<h1>Edit Salle</h1>"
        f"<form method='post' action='/admin/salles/{salle_id}/update'>"
        f"<input name='code' required value='{html_lib.escape(salle.code, quote=True)}'/>"
        f"<input name='name' required value='{html_lib.escape(salle.name, quote=True)}'/>"
        f"<input name='latitude' placeholder='Latitude' value='{html_lib.escape(str(salle.latitude) if salle.latitude is not None else '', quote=True)}'/>"
        f"<input name='longitude' placeholder='Longitude' value='{html_lib.escape(str(salle.longitude) if salle.longitude is not None else '', quote=True)}'/>"
        "<div><b>Gérants</b></div>"
        f"{manager_choices}"
        "<div style='margin-top:8px'><b>Responsables</b></div>"
        f"{responsable_choices}"
        "<button type='submit'>Mettre à jour</button>"
        "</form>"
        "<p><a href='/admin/salles'>Retour</a></p>",
        title="Modifier salle",
    )


@app.post("/admin/salles/{salle_id}/update")
async def update_salle(
    salle_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    form = await request.form()
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    code = (form.get("code") or "").strip()
    name = (form.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")

    latitude_raw = (form.get("latitude") or "").strip()
    longitude_raw = (form.get("longitude") or "").strip()
    lat_v = float(latitude_raw) if latitude_raw else None
    lon_v = float(longitude_raw) if longitude_raw else None

    raw_manager_ids = form.getlist("manager_user_ids")
    raw_responsable_ids = form.getlist("responsable_user_ids")
    manager_ids = [int(x) for x in raw_manager_ids if str(x).isdigit()]
    responsable_ids = [int(x) for x in raw_responsable_ids if str(x).isdigit()]

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    if not super_admin:
        if not is_effective_salle_admin_for_salle(db, user_id, salle_id):
            raise HTTPException(status_code=403, detail="Accès refusé")
        manager_ids, responsable_ids = _filter_manager_responsable_ids(
            db, user_id, salle_id, manager_ids, responsable_ids, super_admin=False
        )

    salle.code = code
    salle.name = name

    salle.latitude = lat_v
    salle.longitude = lon_v

    manager_role = db.query(Role).filter(Role.key == "manager").first()
    responsable_role = db.query(Role).filter(Role.key == "responsable").first()
    if not manager_role or not responsable_role:
        raise HTTPException(status_code=500, detail="Roles manager/responsable manquants")

    valid_user_ids = {
        r[0]
        for r in db.query(User.id)
        .filter(User.id.in_(manager_ids + responsable_ids))
        .all()
    }
    manager_ids = [uid for uid in manager_ids if uid in valid_user_ids]
    responsable_ids = [uid for uid in responsable_ids if uid in valid_user_ids]

    try:
        role_ids = [manager_role.id, responsable_role.id]
        db.query(SalleUser).filter(SalleUser.salle_id == salle_id, SalleUser.role_id.in_(role_ids)).delete(
            synchronize_session=False
        )
        for uid in manager_ids:
            db.add(SalleUser(salle_id=salle_id, user_id=uid, role_id=manager_role.id))
        for uid in responsable_ids:
            db.add(SalleUser(salle_id=salle_id, user_id=uid, role_id=responsable_role.id))
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")
    return RedirectResponse(url="/admin/salles", status_code=303)


@app.post("/admin/salles/{salle_id}/delete")
def delete_salle(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        if not is_effective_salle_admin_for_salle(db, user_id, salle_id):
            raise HTTPException(status_code=403, detail="Accès refusé")
    used = db.query(Station).filter(Station.salle_id == salle_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="Salle utilisée par des stations : suppression refusée")

    db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id).delete()
    db.query(SalleUser).filter(SalleUser.salle_id == salle_id).delete(synchronize_session=False)
    db.delete(salle)
    db.commit()
    return RedirectResponse(url="/admin/salles", status_code=303)



def admin_salle_offers(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if super_admin:
        offers = (
            db.query(Offer)
            .filter(Offer.is_active.is_(True))
            .order_by(
                Offer.duration_minutes.asc(),
                Offer.price_xof.asc(),
                Offer.id.asc(),
            )
            .all()
        )
    else:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        offers = []
        if allowed_offer_ids:
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
    attached_offer_ids = {
        so.offer_id
        for so in db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id, SalleOffer.is_active.is_(True)).all()
    }

    offers_rows = "".join(
        [
            f"<tr>"
            f"<td>{o.id}</td>"
            f"<td>{o.name}</td>"
            f"<td>{o.duration_minutes}</td>"
            f"<td>{o.price_xof}</td>"
            f"<td>{o.provider}</td>"
            f"<td><input type='checkbox' name='offer_ids' value='{o.id}' {'checked' if o.id in attached_offer_ids else ''} {'disabled' if not o.is_active else ''}/></td>"
            f"</tr>"
            for o in offers
        ]
    )

    return admin_page_response(
        "<h1>Offres de la salle</h1>"
        f"<p>Salle: {html_lib.escape(salle.code)} — {html_lib.escape(salle.name)}</p>"
        f"<form method='post' action='/admin/salles/{salle_id}/offers'>"
        "<table><tr><th>ID</th><th>Nom</th><th>Duree</th><th>Prix</th><th>Provider</th><th>Attacher</th></tr>"
        f"{offers_rows}</table>"
        "<button type='submit' style='margin-top:12px'>Enregistrer</button></form>"
        "<p><a href='/admin/salles'>Retour</a></p>",
        title="Offres salle",
    )


@app.post("/admin/salles/{salle_id}/offers")
async def admin_salle_offers_post(salle_id: int, request: Request, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    form = await request.form()
    raw_ids = form.getlist("offer_ids")
    offer_ids = [int(x) for x in raw_ids if str(x).isdigit()]

    if not super_admin:
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        offer_ids = [oid for oid in offer_ids if oid in allowed_offer_ids]

    active_ids = {
        o.id
        for o in db.query(Offer).filter(Offer.id.in_(offer_ids), Offer.is_active.is_(True)).all()
    }

    db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id).delete()
    for oid in active_ids:
        db.add(SalleOffer(salle_id=salle_id, offer_id=oid, is_active=True))
    db.commit()
    return RedirectResponse(url=f"/admin/salles/{salle_id}/offers", status_code=303)



def admin_manual_session_get(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    """Démarrage d’une session sans parcours paiement client (gérant / admin)."""
    user_id = int(_)
    if is_global_super_admin(db, user_id):
        stations = db.query(Station).filter(Station.is_active.is_(True)).order_by(Station.id).all()
    else:
        ids = get_allowed_station_ids(db, user_id)
        if not ids:
            return admin_page_response(
                "<h1>Démarrer une session</h1>"
                + html_hint_no_stations_for_manual_session(db, user_id)
                + "<p><a href='/admin'>Retour</a></p>",
                title="Session manuelle",
            )
        stations = (
            db.query(Station)
            .filter(Station.id.in_(ids), Station.is_active.is_(True))
            .order_by(Station.id)
            .all()
        )
    options: list[str] = []
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
            options.append(
                f"<option value='{st.id}:{off.id}'>{html_lib.escape(st.code)} — "
                f"{html_lib.escape(off.name)} ({off.duration_minutes} min)</option>"
            )
    if not options:
        return admin_page_response(
            "<h1>Démarrer une session</h1><p>Aucune offre disponible sur vos stations.</p>"
            "<p><a href='/admin'>Retour</a></p>",
            title="Session manuelle",
        )
    opts_html = "\n".join(options)
    return admin_page_response(
        "<h1>Démarrer une session pour un joueur</h1>"
        "<p>Activation immédiate (sans paiement en ligne). La station doit être libre.</p>"
        "<form method='post' action='/admin/manual-session'>"
        "<label>Station & offre<br/><select name='station_offer' required>"
        f"{opts_html}</select></label><br/><br/>"
        "<label>Téléphone joueur (optionnel)<br/><input type='tel' name='phone' placeholder='+225...'/></label><br/><br/>"
        "<label>Email joueur (optionnel)<br/><input type='email' name='email'/></label><br/><br/>"
        "<button type='submit'>Démarrer</button></form>"
        "<p><a href='/admin'>Retour</a></p>",
        title="Session manuelle",
    )


@app.post("/admin/manual-session")
def admin_manual_session_post(
    station_offer: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    user_id = int(_)
    parts = station_offer.split(":", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise HTTPException(status_code=400, detail="Choix station/offre invalide")
    station_id, offer_id = int(parts[0]), int(parts[1])

    if not session_station_allowed_for_user(db, user_id, station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    station = db.query(Station).filter(Station.id == station_id).first()
    offer = db.query(Offer).filter(Offer.id == offer_id, Offer.is_active.is_(True)).first()
    if not station or not offer:
        raise HTTPException(status_code=404, detail="Station ou offre introuvable")

    station_allowed = (
        db.query(StationOffer)
        .filter(
            StationOffer.station_id == station.id,
            StationOffer.offer_id == offer.id,
            StationOffer.is_active.is_(True),
        )
        .first()
    )
    salle_allowed = None
    if station.salle_id is not None:
        salle_allowed = (
            db.query(SalleOffer)
            .filter(
                SalleOffer.salle_id == station.salle_id,
                SalleOffer.offer_id == offer.id,
                SalleOffer.is_active.is_(True),
            )
            .first()
        )
    if not station_allowed and not salle_allowed:
        raise HTTPException(status_code=400, detail="Offre non disponible pour cette station")

    station_busy = (
        db.query(GameSession)
        .filter(
            GameSession.station_id == station.id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .first()
    )
    if station_busy:
        raise HTTPException(status_code=409, detail="Station déjà occupée")

    phone_v = phone.strip() or None
    email_v = email.strip() or None
    if phone_v:
        joueur = get_or_create_user_by_phone(db, phone_v, email_v)
    else:
        joueur = get_default_user(db)

    chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
    reference = make_payment_reference(chosen_sim_provider)
    session = GameSession(
        station_id=station.id,
        offer_id=offer.id,
        user_id=joueur.id,
        payment_provider=chosen_sim_provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_email=email_v,
        customer_phone=phone_v,
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Station déjà occupée")
    db.refresh(session)
    log_event(
        db,
        f"Démarrage manuel session {reference} station={station.code}",
        station_id=station.id,
        session_id=session.id,
    )
    if not activate_paid_session(db, session, source="admin_manual", trusted=True):
        raise HTTPException(status_code=400, detail="Impossible d'activer la session")
    return RedirectResponse(url="/admin/sessions", status_code=303)



def admin_sessions(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if super_admin:
        sessions = (
            db.query(GameSession).order_by(GameSession.id.desc()).limit(100).all()
        )
    else:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles:
            return admin_page_response(
                "<h1>Admin Sessions</h1>"
                + html_hint_empty_scoped_salles(db, user_id)
                + "<p><a href='/admin'>Retour</a></p>",
                title="Sessions",
            )
        sessions = (
            db.query(GameSession)
            .join(Station, Station.id == GameSession.station_id)
            .filter(Station.salle_id.in_(allowed_salles))
            .order_by(GameSession.id.desc())
            .limit(100)
            .all()
        )
    rows_parts = []
    for s in sessions:
        actions: list[str] = []
        if s.status == "active":
            actions.append(
                f"<form method='post' action='/admin/sessions/{s.id}/pause' style='display:inline'>"
                "<button type='submit'>Pause</button></form>"
            )
            actions.append(
                f"<form method='post' action='/admin/sessions/{s.id}/extend' style='display:inline'>"
                "<label>Δ min <input name='minutes' type='number' required value='10' "
                "title='Positif = prolonger, négatif = raccourcir'/></label> "
                "<button type='submit'>Appliquer</button></form>"
            )
        elif s.status == "paused":
            actions.append(
                f"<form method='post' action='/admin/sessions/{s.id}/resume' style='display:inline'>"
                "<button type='submit'>Reprendre</button></form>"
            )
            actions.append(
                f"<form method='post' action='/admin/sessions/{s.id}/extend' style='display:inline'>"
                "<label>Δ min <input name='minutes' type='number' required value='10' "
                "title='Modifie la fin prévue (reprise = timer relancé)'/></label> "
                "<button type='submit'>Appliquer</button></form>"
            )
        actions_cell = "<td>" + " &nbsp; ".join(actions) + "</td>" if actions else "<td></td>"

        rows_parts.append(
            "<tr>"
            f"<td>{s.id}</td>"
            f"<td>{s.payment_reference}</td>"
            f"<td>{s.payment_provider}</td>"
            f"<td>{s.payment_status}</td>"
            f"<td>{s.status}</td>"
            f"<td>{s.started_at}</td>"
            f"<td>{s.end_at}</td>"
            f"{actions_cell}"
            "</tr>"
        )
    rows = "".join(rows_parts)
    return admin_page_response(
        "<h1>Admin Sessions</h1>"
        "<table><tr><th>ID</th><th>Reference</th><th>Provider</th><th>Pay</th>"
        "<th>Status</th><th>Start</th><th>End</th><th>Actions</th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>",
        title="Sessions",
    )


@app.post("/admin/sessions/{session_id}/extend")
def admin_extend_session(
    session_id: int,
    minutes: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status not in ("active", "paused"):
        raise HTTPException(
            status_code=400,
            detail="Session non modifiable (active ou en pause uniquement).",
        )

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    base_end = session.end_at if session.end_at and session.end_at > now else now
    new_end = base_end + timedelta(minutes=minutes)
    if new_end < now + timedelta(minutes=1):
        raise HTTPException(
            status_code=400,
            detail="Il doit rester au moins 1 minute avant la fin de session.",
        )

    if session.status == "active":
        extend_session_end_at(db, session, minutes, source="admin")
    else:
        # En pause : pas de tâche Celery en cours ; on met seulement à jour end_at.
        session.end_at = new_end
        db.add(session)
        db.commit()
        log_event(
            db,
            f"Ajustement fin session {session.id} (en pause): {minutes:+d} min (source=admin).",
            level="info",
            station_id=session.station_id,
            session_id=session.id,
        )
    return RedirectResponse(url="/admin/sessions", status_code=303)


@app.post("/admin/sessions/{session_id}/pause")
def admin_pause_session(
    session_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status != "active":
        raise HTTPException(status_code=400, detail="Seule une session active peut être mise en pause.")

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    session.status = "paused"
    db.add(session)
    db.commit()
    log_event(
        db,
        f"Session {session.id} mise en pause (admin).",
        level="info",
        station_id=session.station_id,
        session_id=session.id,
    )
    return RedirectResponse(url="/admin/sessions", status_code=303)


@app.post("/admin/sessions/{session_id}/resume")
def admin_resume_session(
    session_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status != "paused":
        raise HTTPException(status_code=400, detail="Seule une session en pause peut être reprise.")

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    session.status = "active"
    db.add(session)
    db.commit()
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    if session.end_at and session.end_at > now:
        remaining_s = max(0, int((session.end_at - now).total_seconds()))
        deactivate_session.apply_async(args=[session.id], countdown=remaining_s)
    else:
        deactivate_session.apply_async(args=[session.id], countdown=0)
    log_event(
        db,
        f"Session {session.id} reprise (admin), décompte relancé.",
        level="info",
        station_id=session.station_id,
        session_id=session.id,
    )
    return RedirectResponse(url="/admin/sessions", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), "delta": timedelta(seconds=0).total_seconds()}
