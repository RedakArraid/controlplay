import html as html_lib
import re
import os
import secrets
import bcrypt
import requests
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from uuid import uuid4

from database import get_db, SessionLocal
from models import Role, SalleUser, UserRole, User, UserStaffPermission, Station, Offer, StationOffer, SalleOffer, PaymentProviderConfig
from ui_theme import html_shell_login

def log_event(db: Session, message: str, level: str = "info", station_id=None, session_id=None):
    from models import EventLog
    db.add(EventLog(message=message, level=level, station_id=station_id, session_id=session_id))
    db.commit()

def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")

def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False

def is_global_salle_admin(db: Session, user_id: int) -> bool:
    return db.query(UserRole).join(Role, Role.id == UserRole.role_id)\
        .filter(UserRole.user_id == user_id, Role.key == "salle_admin").first() is not None

def is_global_platform_staff(db: Session, user_id: int) -> bool:
    return db.query(UserRole).join(Role, Role.id == UserRole.role_id)\
        .filter(UserRole.user_id == user_id, Role.key == "admin").first() is not None

def user_can_access_admin(db: Session, user: User) -> bool:
    ga = db.query(UserRole).join(Role, Role.id == UserRole.role_id).filter(UserRole.user_id == user.id, Role.key == "super_admin").first()
    if ga: return True
    if is_global_platform_staff(db, user.id): return True
    if is_global_salle_admin(db, user.id): return True
    sa = db.query(SalleUser).join(Role, Role.id == SalleUser.role_id)\
        .filter(SalleUser.user_id == user.id, Role.key.in_(("salle_admin", "manager", "responsable"))).first()
    return sa is not None

def get_authenticated_admin_user_id(request: Request, db: Session) -> int:
    raw = request.session.get("user_id")
    if raw is None:
        raise HTTPException(status_code=401, detail="Non connecté")
    try: uid = int(raw)
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

def is_global_super_admin(db: Session, user_id: int) -> bool:
    return db.query(UserRole).join(Role, Role.id == UserRole.role_id)\
        .filter(UserRole.user_id == user_id, Role.key == "super_admin").first() is not None

def require_super_admin(request: Request, db: Session = Depends(get_db)) -> str:
    uid = get_authenticated_admin_user_id(request, db)
    if not is_global_super_admin(db, uid):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur")
    return str(uid)

STAFF_PERM_OPERATIONS = "operations"
STAFF_PERM_USERS = "users"
_STAFF_PERM_KEYS: frozenset[str] = frozenset((STAFF_PERM_OPERATIONS, STAFF_PERM_USERS))

def staff_permission_keys(db: Session, user_id: int) -> set[str]:
    if is_global_super_admin(db, user_id): return set(_STAFF_PERM_KEYS)
    if not is_global_platform_staff(db, user_id): return set()
    rows = db.query(UserStaffPermission.permission_key).filter(UserStaffPermission.user_id == user_id).all()
    return {r[0] for r in rows if r[0] in _STAFF_PERM_KEYS}

def has_staff_operations_access(db: Session, user_id: int) -> bool:
    if is_global_super_admin(db, user_id): return True
    return STAFF_PERM_OPERATIONS in staff_permission_keys(db, user_id)

def has_platform_operations_scope(db: Session, user_id: int) -> bool:
    return is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id)

def can_use_super_admin_zone(db: Session, user_id: int) -> bool:
    if is_global_super_admin(db, user_id): return True
    if not is_global_platform_staff(db, user_id): return False
    return bool(staff_permission_keys(db, user_id))

def require_super_zone_or_staff(request: Request, db: Session = Depends(get_db)) -> str:
    uid = get_authenticated_admin_user_id(request, db)
    if not can_use_super_admin_zone(db, uid):
        raise HTTPException(status_code=403, detail="Accès à l’espace super administrateur refusé.")
    return str(uid)

def has_staff_users_access(db: Session, user_id: int) -> bool:
    if is_global_super_admin(db, user_id): return True
    return STAFF_PERM_USERS in staff_permission_keys(db, user_id)

def require_staff_users_or_super(request: Request, db: Session = Depends(get_db)) -> str:
    uid = get_authenticated_admin_user_id(request, db)
    if not (is_global_super_admin(db, uid) or has_staff_users_access(db, uid)):
        raise HTTPException(status_code=403, detail="Accès réservé à la gestion des comptes.")
    return str(uid)

def get_scoped_salle_ids(db: Session, user_id: int) -> list[int]:
    rows = db.query(SalleUser.salle_id).join(Role, Role.id == SalleUser.role_id)\
        .filter(SalleUser.user_id == user_id, Role.key.in_(("salle_admin", "manager", "responsable"))).all()
    return [r[0] for r in rows]

def get_salle_admin_salle_ids(db: Session, user_id: int) -> list[int]:
    rows = db.query(SalleUser.salle_id).join(Role, Role.id == SalleUser.role_id)\
        .filter(SalleUser.user_id == user_id, Role.key == "salle_admin").all()
    return [r[0] for r in rows]

def effective_salle_admin_salle_ids(db: Session, user_id: int) -> set[int]:
    ids = set(get_salle_admin_salle_ids(db, user_id))
    if is_global_salle_admin(db, user_id): ids |= set(get_scoped_salle_ids(db, user_id))
    return ids

def is_effective_salle_admin_for_salle(db: Session, user_id: int, salle_id: int) -> bool:
    if is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id): return True
    return salle_id in effective_salle_admin_salle_ids(db, user_id)

def get_allowed_station_ids(db: Session, user_id: int) -> list[int]:
    if is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id):
        rows = db.query(Station.id).all()
        return [r[0] for r in rows]
    allowed_salles = get_scoped_salle_ids(db, user_id)
    if not allowed_salles: return []
    rows = db.query(Station.id).filter(Station.salle_id.in_(allowed_salles)).all()
    return [r[0] for r in rows]

def session_station_allowed_for_user(db: Session, user_id: int, station_id: int | None) -> bool:
    if not station_id: return False
    if is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id): return True
    return station_id in get_allowed_station_ids(db, user_id)

def user_salle_role_keys(db: Session, user_id: int) -> set[str]:
    rows = db.query(Role.key).join(SalleUser, SalleUser.role_id == Role.id).filter(SalleUser.user_id == user_id).all()
    return {r[0] for r in rows}

def is_session_gerant_only(db: Session, user_id: int) -> bool:
    if is_global_super_admin(db, user_id): return False
    if is_global_salle_admin(db, user_id): return False
    keys = user_salle_role_keys(db, user_id)
    if not keys: return False
    if "salle_admin" in keys or "responsable" in keys: return False
    return "manager" in keys

def require_config_admin(request: Request, db: Session = Depends(get_db)) -> str:
    uid = get_authenticated_admin_user_id(request, db)
    if is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé : compte gérant.")
    return str(uid)

def get_allowed_offer_ids_for_user(db: Session, user_id: int) -> set[int]:
    if is_global_super_admin(db, user_id) or has_staff_operations_access(db, user_id):
        rows = db.query(Offer.id).filter(Offer.is_active.is_(True)).all()
        return {r[0] for r in rows}
    allowed_salles = get_scoped_salle_ids(db, user_id)
    allowed_stations = get_allowed_station_ids(db, user_id)
    if not allowed_salles or not allowed_stations: return set()
    offer_ids_station = db.query(StationOffer.offer_id).filter(StationOffer.is_active.is_(True), StationOffer.station_id.in_(allowed_stations)).all()
    offer_ids_salle = db.query(SalleOffer.offer_id).filter(SalleOffer.is_active.is_(True), SalleOffer.salle_id.in_(allowed_salles)).all()
    return {r[0] for r in (offer_ids_station + offer_ids_salle)}

def get_payment_provider_config() -> PaymentProviderConfig | None:
    db = SessionLocal()
    try: return db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    finally: db.close()

def paystack_enabled() -> bool:
    cfg = get_payment_provider_config()
    return cfg.paystack_enabled if cfg else True

def cinetpay_enabled() -> bool:
    cfg = get_payment_provider_config()
    return cfg.cinetpay_enabled if cfg else True

def user_visible_to_salle_admin(db: Session, viewer_salle_admin_id: int, target: User, salle_id: int) -> bool:
    cb = target.created_by_user_id
    if cb is None or cb == viewer_salle_admin_id or is_global_super_admin(db, cb): return True
    return False

def can_use_mes_utilisateurs_page(db: Session, user_id: int) -> bool:
    if is_global_super_admin(db, user_id): return False
    return is_global_salle_admin(db, user_id) or bool(get_salle_admin_salle_ids(db, user_id))

def _user_ids_created_by_salle_admin(db: Session, viewer_id: int) -> set[int]:
    return {r[0] for r in db.query(User.id).filter(User.created_by_user_id == viewer_id).all()}

def _user_ids_allowed_for_manager_responsable_form(db: Session, viewer_id: int, salle_id: int, *, super_admin: bool) -> set[int] | None:
    if super_admin: return None
    allowed = _user_ids_created_by_salle_admin(db, viewer_id)
    mgr = db.query(Role).filter(Role.key == "manager").first()
    resp = db.query(Role).filter(Role.key == "responsable").first()
    role_ids = [rid for rid in (mgr.id if mgr else None, resp.id if resp else None) if rid is not None]
    if role_ids:
        for (uid,) in db.query(SalleUser.user_id).filter(SalleUser.salle_id == salle_id, SalleUser.role_id.in_(role_ids)).distinct().all():
            allowed.add(uid)
    return allowed

def _salle_admin_may_use_existing_user_for_assignment(db: Session, viewer_id: int, target: User) -> bool:
    cb = target.created_by_user_id
    if cb is None or cb == viewer_id or is_global_super_admin(db, cb): return True
    return False

def _filter_manager_responsable_ids(db: Session, viewer_id: int, salle_id: int, manager_ids: list[int], responsable_ids: list[int], *, super_admin: bool) -> tuple[list[int], list[int]]:
    allowed = _user_ids_allowed_for_manager_responsable_form(db, viewer_id, salle_id, super_admin=super_admin)
    if allowed is None: return manager_ids, responsable_ids
    return [i for i in manager_ids if i in allowed], [i for i in responsable_ids if i in allowed]


def safe_internal_redirect(url: str, default: str) -> str:
    u = (url or default).strip() or default
    if not u.startswith("/") or u.startswith("//"):
        return default
    return u


def get_role_ids(db: Session, role_keys: list[str]) -> dict[str, int]:
    roles = db.query(Role).filter(Role.key.in_(role_keys)).all()
    return {r.key: r.id for r in roles}


def login_next_safe(raw: str) -> str:
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


def find_user_for_login(db: Session, identifier: str) -> User | None:
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


def html_login_page(next_internal: str, *, error: str | None = None) -> str:
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

