import hashlib
import hmac
import io
import os
import re
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

import bcrypt
import qrcode
import requests
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import Base, engine, get_db, SessionLocal
from models import (
    EventLog,
    GameSession,
    Offer,
    PaymentProviderConfig,
    Salle,
    Role,
    SalleUser,
    SessionExtension,
    Station,
    StationOffer,
    SalleOffer,
    User,
    UserRole,
)
from tasks import activate_session, deactivate_session


app = FastAPI(title="ControlPlay")
admin_security = HTTPBasic()
if os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true":
    Base.metadata.create_all(bind=engine)


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


def require_admin(
    credentials: HTTPBasicCredentials = Depends(admin_security),
    db: Session = Depends(get_db),
) -> str:
    identifier = (credentials.username or "").strip()
    password = credentials.password or ""

    user = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .filter(or_(User.email == identifier, User.phone == identifier))
        .first()
    )

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Identifiants admin invalides",
            headers={"WWW-Authenticate": "Basic"},
        )

    is_admin = (
        db.query(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == user.id)
        .filter(Role.key == "admin")
        .first()
    )
    if not is_admin:
        raise HTTPException(
            status_code=401,
            detail="Identifiants admin invalides",
            headers={"WWW-Authenticate": "Basic"},
        )

    return str(user.id)


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
    now = datetime.utcnow().replace(microsecond=0)
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
            GameSession.status.in_(("pending", "active")),
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


@app.on_event("startup")
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
        stations_no_salle = db.query(Station).filter(Station.salle_id.is_(None)).all()

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

        # --- Auth / RBAC seed (users/roles) ---
        # On seed des roles minimaux + un admin global de bootstrap.
        role_seed = [
            ("admin", "Admin global"),
            ("manager", "Gérant"),
            ("responsable", "Responsable"),
            ("joueur", "Joueur"),
        ]
        for key, name in role_seed:
            if not db.query(Role).filter(Role.key == key).first():
                db.add(Role(key=key, name=name))

        admin_role = db.query(Role).filter(Role.key == "admin").first()
        if admin_role:
            admin_exists = db.query(UserRole).filter(UserRole.role_id == admin_role.id).first()
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

                    db.add(UserRole(user_id=existing_user.id, role_id=admin_role.id))

        db.commit()
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def home(db: Session = Depends(get_db)):
    salles = db.query(Salle).order_by(Salle.id.desc()).all()
    html = "<h1>ControlPlay</h1><h2>Salles</h2><ul>"
    for sl in salles:
        html += f"<li>{sl.name} ({sl.code}) - <a href='/salle/{sl.code}'>Voir stations</a></li>"
    html += "</ul><p><a href='/admin'>Administration</a></p>"
    return HTMLResponse(html)


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
            f"<li>{s.name} - <a href='/s/{s.code}'>Page client</a> - <a href='/qr/{s.code}.png'>QR</a></li>"
            for s in stations
        ]
    )

    return HTMLResponse(
        f"<h1>{salle.name}</h1>"
        f"<p>Stations :</p><ul>{rows}</ul>"
        "<p><a href='/'>Retour salles</a></p>"
    )


@app.get("/s/{station_code}", response_class=HTMLResponse)
def station_page(station_code: str, db: Session = Depends(get_db)):
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
    items = "".join(
        [
            f"<li>{offer.name} - {offer.price_xof} XOF"
            f"<form method='post' action='/checkout' style='display:inline;margin-left:10px'>"
            f"<input type='hidden' name='station_code' value='{station_code}'/>"
            f"<input type='hidden' name='offer_id' value='{offer.id}'/>"
            "<input type='email' name='email' placeholder='email (optionnel)'/>"
            "<label style='margin-left:10px'><input type='checkbox' name='connect' value='1'/> Connexion</label>"
            "<input type='tel' name='phone' placeholder='Numéro téléphone'/>"
            "<button type='submit'>Payer</button></form></li>"
            for offer in offers
        ]
    )
    extension_items = ""
    if active_session:
        extension_items = "".join(
            [
                f"<li>+ {offer.duration_minutes} minutes ({offer.price_xof} XOF)"
                f"<form method='post' action='/extend/checkout' style='display:inline;margin-left:10px'>"
                f"<input type='hidden' name='station_code' value='{station_code}'/>"
                f"<input type='hidden' name='offer_id' value='{offer.id}'/>"
                "<input type='email' name='email' placeholder='email (optionnel)'/>"
                "<label style='margin-left:10px'><input type='checkbox' name='connect' value='1'/> Connexion</label>"
                "<input type='tel' name='phone' placeholder='Numéro téléphone'/>"
                "<button type='submit'>Ajouter</button></form></li>"
                for offer in offers
            ]
        )
    retour_href = "/"
    if station.salle_id is not None:
        salle = db.query(Salle).filter(Salle.id == station.salle_id).first()
        if salle:
            retour_href = f"/salle/{salle.code}"

    return HTMLResponse(
        f"<h1>{station.name}</h1><p>Choisis une offre:</p><ul>{items}</ul>"
        f"{('<h2>Ajouter du temps à la session active</h2><ul>' + extension_items + '</ul>') if active_session else ''}"
        f"<p><a href='/qr/{station_code}.png'>QR de cette station</a></p>"
        f"<p><a href='{retour_href}'>Retour</a></p>"
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
        .filter(GameSession.station_id == station.id, GameSession.status.in_(("pending", "active")))
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
        return HTMLResponse("<h1>Extension refusée</h1><p>La session n'est plus active.</p><p><a href='/'>Retour</a></p>")
    return HTMLResponse(
        "<h1>Temps ajoute</h1><p>La TV reste sur HDMI2.</p><p><a href='/s/{station_code}'>Retour</a></p>"
    )


@app.get("/simulate/pay/{reference}", response_class=HTMLResponse)
def simulate_payment(reference: str, status: str, email: str = "", db: Session = Depends(get_db)):
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
            return HTMLResponse("<h1>Paiement echoue</h1><p>Aucun fallback disponible.</p><p><a href='/'>Retour accueil</a></p>")

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
            return HTMLResponse(
                f"<h1>Paiement valide (fallback)</h1><p>Reference initiale: {reference}</p><p>Reference fallback: {new_reference}</p>"
                "<p>Station actuellement occupee: activation differee.</p>"
                "<p><a href='/'>Retour accueil</a></p>"
            )

        station_code = new_session.station.code if new_session.station else None
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return HTMLResponse(
            f"<h1>Paiement valide (fallback)</h1><p>Reference initiale: {reference}</p><p>Reference fallback: {new_reference}</p>"
            "<p>La TV devrait basculer sur HDMI2.</p>"
            "<p><a href='/'>Retour accueil</a></p>"
        )

    activate_paid_session(db, session, "simulate", trusted=True)
    station_code = session.station.code if session.station else None
    if station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)
    return HTMLResponse(
        f"<h1>Paiement valide</h1><p>Reference: {reference}</p>"
        "<p>La TV devrait basculer sur HDMI2.</p>"
        "<p><a href='/'>Retour accueil</a></p>"
    )


@app.get("/payments/return/paystack/{reference}")
def paystack_return(reference: str, request: Request, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")

    callback_status = (request.query_params.get("status") or request.query_params.get("payment_status") or "").lower()
    station_code = session.station.code if session.station else None

    if session.payment_status == "paid" or session.status == "active":
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return HTMLResponse("<h1>Paiement confirme</h1><p>La TV sera activee.</p><p><a href='/'>Retour accueil</a></p>")

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

    return HTMLResponse("<h1>Paiement en attente</h1><p>Merci de patienter.</p><p><a href='/'>Retour accueil</a></p>")


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
        return HTMLResponse("<h1>Extension confirmée</h1><p>Temps ajouté.</p><p><a href='/'>Retour accueil</a></p>")

    if not is_paystack_api_configured():
        return HTMLResponse("<h1>Extension en attente</h1><p>Paystack non configuré.</p><p><a href='/'>Retour accueil</a></p>")

    if verify_paystack_transaction(reference):
        apply_paid_extension(db, extension, "paystack_extension_return", trusted=True)
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return HTMLResponse("<h1>Extension confirmée</h1><p>Temps ajouté.</p><p><a href='/'>Retour accueil</a></p>")

    extension.payment_status = "failed"
    extension.status = "failed"
    db.commit()
    return HTMLResponse("<h1>Extension refusée</h1><p>Paiement Paystack non confirmé.</p><p><a href='/'>Retour accueil</a></p>")

    # Après redirection Paystack : vérifier la transaction via l'API (ne pas attendre uniquement le webhook).
    if session.status == "pending" and session.payment_provider == "paystack" and is_paystack_api_configured():
        if verify_paystack_transaction(session.payment_reference):
            activate_paid_session(db, session, "paystack_return", trusted=False)
            db.refresh(session)
        if session.payment_status == "paid" or session.status == "active":
            return HTMLResponse("<h1>Paiement confirme</h1><p>La TV sera activee.</p><p><a href='/'>Retour accueil</a></p>")

    # En cas d'échec explicite, on bascule sur CinetPay.
    is_failure = callback_status in ("failed", "declined", "refused", "error")
    if not is_failure and session.status == "pending":
        return HTMLResponse("<h1>Paiement en cours</h1><p>Merci de patienter (validation via webhook).</p><p><a href='/'>Retour accueil</a></p>")

    if session.payment_provider != "paystack":
        return HTMLResponse("<h1>Paiement non confirme</h1><p>Activation impossible (provider different).</p><p><a href='/'>Retour accueil</a></p>")

    if not is_cinetpay_configured():
        return HTMLResponse("<h1>Paiement echoue</h1><p>CinetPay indisponible.</p><p><a href='/'>Retour accueil</a></p>")

    other_busy = (
        db.query(GameSession)
        .filter(
            and_(
                GameSession.station_id == session.station_id,
                GameSession.id != session.id,
                GameSession.status.in_(("pending", "active")),
            )
        )
        .first()
    )
    if other_busy:
        return HTMLResponse("<h1>Paiement echoue</h1><p>Station occupee: activation differee.</p><p><a href='/'>Retour accueil</a></p>")

    if session.status == "pending":
        session.payment_status = "failed"
        session.status = "failed"
        db.commit()

    alt_reference = make_payment_reference("cinetpay")
    payment_url = init_cinetpay_payment(
        transaction_id=alt_reference,
        amount_xof=session.offer.price_xof,
        description=session.offer.name,
    )

    new_session = GameSession(
        station_id=session.station_id,
        offer_id=session.offer.id,
        user_id=session.user_id,
        payment_provider="cinetpay",
        payment_reference=alt_reference,
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
        f"Fallback: Paystack({reference}) -> CinetPay({alt_reference})",
        station_id=session.station_id,
        session_id=new_session.id,
        level="warning",
    )
    return RedirectResponse(url=payment_url, status_code=303)


@app.api_route("/payments/return/cinetpay", methods=["GET", "POST"])
async def cinetpay_return(request: Request, db: Session = Depends(get_db)):
    transaction_id = request.query_params.get("transaction_id")
    if not transaction_id and request.method in ("POST",):
        form = await request.form()
        transaction_id = form.get("transaction_id")

    if not transaction_id:
        raise HTTPException(status_code=404, detail="transaction_id introuvable")

    session = db.query(GameSession).filter(GameSession.payment_reference == transaction_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")

    station_code = session.station.code if session.station else None
    if session.payment_status == "paid" or session.status == "active":
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return HTMLResponse("<h1>Paiement confirme</h1><p>La TV sera activee.</p><p><a href='/'>Retour accueil</a></p>")

    if station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)
    return HTMLResponse(
        "<h1>Paiement en attente / echoue</h1>"
        "<p>Merci de patienter (validation via webhook).</p>"
        "<p><a href='/'>Retour accueil</a></p>"
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
        return {"ok": True}

    if session:
        activate_paid_session(db, session, "cinetpay_webhook")
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


@app.get("/admin", response_class=HTMLResponse)
def admin_home(_: str = Depends(require_admin)):
    return HTMLResponse(
        "<h1>Admin</h1>"
        "<ul>"
        "<li><a href='/admin/salles'>Salles</a></li>"
        "<li><a href='/admin/users'>Users</a></li>"
        "<li><a href='/admin/offers'>Offres</a></li>"
        "<li><a href='/admin/stations'>Stations</a></li>"
        "<li><a href='/admin/sessions'>Sessions</a></li>"
        "<li><a href='/admin/providers'>Providers</a></li>"
        "</ul>"
    )


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    users = db.query(User).order_by(User.id.desc()).limit(200).all()

    admin_role = db.query(Role).filter(Role.key == "admin").first()
    admin_user_ids: set[int] = set()
    if admin_role:
        admin_user_ids = {r.user_id for r in db.query(UserRole).filter(UserRole.role_id == admin_role.id).all()}

    users_rows = "".join(
        [
            "<tr>"
            f"<td>{u.id}</td>"
            f"<td>{u.name}</td>"
            f"<td>{u.email or ''}</td>"
            f"<td>{u.phone or ''}</td>"
            f"<td>{'YES' if u.id in admin_user_ids else ''}</td>"
            f"<td>{u.is_active}</td>"
            "</tr>"
            for u in users
        ]
    )

    return HTMLResponse(
        "<h1>Admin Users</h1>"
        "<p>Au moins <b>email</b> ou <b>phone</b> doit être renseigné.</p>"
        "<form method='post' action='/admin/users'>"
        "<input name='name' placeholder='Nom' required/>"
        "<input name='email' placeholder='Email (optionnel)'/>"
        "<input name='phone' placeholder='Téléphone (optionnel)'/>"
        "<input name='password' placeholder='Mot de passe' type='password' required/>"
        "<label><input type='checkbox' name='is_active' value='1' checked/> Actif</label>"
        "<label><input type='checkbox' name='is_admin' value='1'/> Admin global</label>"
        "<button type='submit'>Créer user</button>"
        "</form>"
        "<table border='1' style='margin-top:12px'>"
        "<tr><th>ID</th><th>Nom</th><th>Email</th><th>Phone</th><th>Admin</th><th>Actif</th></tr>"
        f"{users_rows}</table>"
        "<p><a href='/admin'>Retour</a></p>"
    )


@app.post("/admin/users")
def create_user(
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    is_admin: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    email_v = email.strip() or None
    phone_v = phone.strip() or None

    if not email_v and not phone_v:
        raise HTTPException(status_code=400, detail="Email ou phone requis")
    if not password or not password.strip():
        raise HTTPException(status_code=400, detail="Mot de passe requis")

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
            admin_role = db.query(Role).filter(Role.key == "admin").first()
            if not admin_role:
                raise HTTPException(status_code=500, detail="Role admin manquant")
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))

        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return RedirectResponse(url="/admin/users", status_code=303)


@app.get("/admin/providers", response_class=HTMLResponse)
def admin_providers(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    cfg = db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    if not cfg:
        cfg = PaymentProviderConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    paystack_checked = "checked" if cfg.paystack_enabled else ""
    cinetpay_checked = "checked" if cfg.cinetpay_enabled else ""

    return HTMLResponse(
        "<h1>Providers</h1>"
        "<p>Contrôle admin du provider à tenter en priorité. Si Paystack est désactivé, on bascule vers CinetPay.</p>"
        "<form method='post' action='/admin/providers'>"
        f"<label><input type='checkbox' name='paystack_enabled' value='1' {paystack_checked}/> Paystack enabled</label><br/>"
        f"<label><input type='checkbox' name='cinetpay_enabled' value='1' {cinetpay_checked}/> CinetPay enabled</label><br/>"
        "<input type='hidden' name='paystack_enabled' value='0'/>"
        "<input type='hidden' name='cinetpay_enabled' value='0'/>"
        "<button type='submit'>Sauvegarder</button>"
        "</form>"
        "<p><a href='/admin'>Retour</a></p>"
    )


@app.post("/admin/providers")
def update_providers(
    paystack_enabled: str = Form("0"),
    cinetpay_enabled: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    cfg = db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    if not cfg:
        cfg = PaymentProviderConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    cfg.paystack_enabled = paystack_enabled == "1"
    cfg.cinetpay_enabled = cinetpay_enabled == "1"
    db.commit()
    return RedirectResponse(url="/admin/providers", status_code=303)


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    now = datetime.utcnow().replace(microsecond=0)

    paystack_flag = paystack_enabled()
    cinetpay_flag = cinetpay_enabled()

    stations = db.query(Station).filter(Station.is_active.is_(True)).order_by(Station.id.desc()).all()

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

        remaining_s = ""
        if active_session and active_session.end_at:
            remaining_s = f"{max(0, int((active_session.end_at - now).total_seconds()))}s"

        rows.append(
            "<tr>"
            f"<td>{st.code}</td>"
            f"<td>{st.name}</td>"
            f"<td>{'ACTIVE' if active_session else ('PENDING' if pending_session else 'OK')}</td>"
            f"<td>{remaining_s}</td>"
            f"<td>{active_session.offer.duration_minutes if active_session and active_session.offer else ''}</td>"
            f"<td>{active_session.offer.price_xof if active_session and active_session.offer else ''}</td>"
            f"<td>{active_session.payment_provider if active_session else ''}</td>"
            f"<td><a href='/admin/stations/{st.id}/offers'>Offres</a></td>"
            f"<td><a href='/admin/stations/{st.id}/edit'>Edit</a></td>"
            "</tr>"
        )

    return HTMLResponse(
        "<h1>Dashboard admin</h1>"
        f"<p>Paystack: <b>{'ON' if paystack_flag else 'OFF'}</b> - CinetPay: <b>{'ON' if cinetpay_flag else 'OFF'}</b></p>"
        "<table border='1'>"
        "<tr><th>Code</th><th>Nom</th><th>Etat</th><th>Temps restants</th><th>Duree (min)</th><th>Prix (XOF)</th><th>Provider</th><th>Offres</th><th>Edit</th></tr>"
        f"{''.join(rows)}"
        "</table>"
        "<p><a href='/admin'>Retour</a></p>"
    )


@app.get("/admin/offers", response_class=HTMLResponse)
def admin_offers(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    used_station_offer_ids = (
        db.query(StationOffer.offer_id).filter(StationOffer.is_active.is_(True)).distinct().subquery()
    )
    used_salle_offer_ids = (
        db.query(SalleOffer.offer_id).filter(SalleOffer.is_active.is_(True)).distinct().subquery()
    )

    offers = (
        db.query(Offer)
        .filter(Offer.is_active.is_(True))
        .filter(
            or_(
                Offer.station_id.is_(None),  # offres globales (legacy)
                Offer.id.in_(used_station_offer_ids),
                Offer.id.in_(used_salle_offer_ids),
            )
        )
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

    return HTMLResponse(
        "<h1>Admin Offres</h1>"
        "<p>Les offres sont des <b>templates</b>. Le rattachement se fait via les pages <b>Offres</b> des stations et des salles.</p>"
        "<form method='post' action='/admin/offers'>"
        "<input name='name' placeholder='Nom offre' required/>"
        "<input name='duration_minutes' type='number' placeholder='Duree minutes' required/>"
        "<input name='price_xof' type='number' placeholder='Prix XOF' required/>"
        "<button type='submit'>Creer offre</button></form>"
        "<table border='1'><tr><th>ID</th><th>Nom</th><th>Scope</th><th>Duree</th><th>Prix</th><th>Provider</th><th>Active</th><th></th><th></th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>"
    )


@app.post("/admin/offers")
def create_offer(
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
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


@app.get("/admin/offers/{offer_id}/edit", response_class=HTMLResponse)
def edit_offer(offer_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    active_checked = "checked" if offer.is_active else ""

    return HTMLResponse(
        "<h1>Edit Offre</h1>"
        f"<form method='post' action='/admin/offers/{offer_id}/update'>"
        f"<input name='name' placeholder='Nom offre' required value='{offer.name}'/>"
        f"<input name='duration_minutes' type='number' placeholder='Duree minutes' required value='{offer.duration_minutes}'/>"
        f"<input name='price_xof' type='number' placeholder='Prix XOF' required value='{offer.price_xof}'/>"
        f"<input type='hidden' name='is_active' value='0'/>"
        f"<label><input type='checkbox' name='is_active' value='1' {active_checked}/> Active</label>"
        f"<button type='submit'>Mettre à jour</button>"
        f"</form>"
        f"<p><a href='/admin/offers'>Retour</a></p>"
    )


@app.post("/admin/offers/{offer_id}/update")
def update_offer(
    offer_id: int,
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
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
    _: str = Depends(require_admin),
):
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
    _: str = Depends(require_admin),
):
    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return HTMLResponse("<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>")

    target_stations = db.query(Station).filter(Station.is_active.is_(True)).all()
    if not target_stations:
        return HTMLResponse("<h1>Aucune station active</h1><p><a href='/admin/offers'>Retour</a></p>")

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
    return HTMLResponse(
        "<h1>Dupliquer terminé</h1>"
        f"<p>Rattachements créés (station_offers): {created}</p>"
        f"<p>Rattachements réactivés: {updated}</p>"
        "<p><a href='/admin/offers'>Retour</a></p>"
    )


@app.post("/admin/offers/clone-global-to-station/{station_id}")
def clone_global_offers_to_station(
    station_id: int,
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return HTMLResponse("<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>")

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
    _: str = Depends(require_admin),
):
    salle = db.query(Salle).filter(Salle.code == salle_code).first()
    if not salle:
        return HTMLResponse("<h1>Salle introuvable</h1><p><a href='/admin/offers'>Retour</a></p>")

    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return HTMLResponse("<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>")

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
    return HTMLResponse(
        "<h1>Dupliquer terminé</h1>"
        f"<p>Salle: {salle_code}</p>"
        f"<p>Rattachements créés (salle_offers): {created}</p>"
        f"<p>Rattachements réactivés: {updated}</p>"
        "<p><a href='/admin/offers'>Retour</a></p>"
    )


@app.get("/admin/stations", response_class=HTMLResponse)
def admin_stations(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    stations = db.query(Station).order_by(Station.id.desc()).all()
    salles = db.query(Salle).order_by(Salle.id.desc()).all()
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
    return HTMLResponse(
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
        "<table border='1'><tr><th>ID</th><th>Code</th><th>Nom</th><th>IP</th><th>Salle</th><th>Sessions</th><th>Offres</th><th></th><th></th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>"
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
    _: str = Depends(require_admin),
):
    existing = db.query(Station).filter(Station.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Code station deja utilise")
    salle_id = None
    if salle_code:
        salle = db.query(Salle).filter(Salle.code == salle_code).first()
        if not salle:
            raise HTTPException(status_code=404, detail="Salle introuvable")
        salle_id = salle.id
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


@app.get("/admin/stations/{station_id}/edit", response_class=HTMLResponse)
def edit_station(station_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    salles = db.query(Salle).order_by(Salle.id.desc()).all()
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

    return HTMLResponse(
        "<h1>Edit Station</h1>"
        f"<form method='post' action='/admin/stations/{station_id}/update'>"
        f"<input name='code' required value='{station.code}'/>"
        f"<input name='name' required value='{station.name}'/>"
        f"<input name='broadlink_ip' required value='{station.broadlink_ip}'/>"
        f"<input name='ir_code_hdmi1' required value='{station.ir_code_hdmi1 or ''}'/>"
        f"<input name='ir_code_hdmi2' required value='{station.ir_code_hdmi2 or ''}'/>"
        f"<select name='salle_code'>{salle_options}</select>"
        "<input type='hidden' name='is_active' value='0'/>"
        f"<label><input type='checkbox' name='is_active' value='1' {active_checked}/> Active</label>"
        "<button type='submit'>Mettre à jour</button>"
        "</form>"
        "<p><a href='/admin/stations'>Retour</a></p>"
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
    _: str = Depends(require_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    station.salle_id = None
    if salle_code:
        salle = db.query(Salle).filter(Salle.code == salle_code).first()
        if not salle:
            raise HTTPException(status_code=404, detail="Salle introuvable")
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
    _: str = Depends(require_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    active_ids_rows = (
        db.query(GameSession.id)
        .filter(
            GameSession.station_id == station_id,
            GameSession.status.in_(("pending", "active")),
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
def delete_station(station_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    used = db.query(GameSession).filter(GameSession.station_id == station_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="Station utilisée par des sessions : suppression refusée")

    db.query(StationOffer).filter(StationOffer.station_id == station_id).delete()
    db.delete(station)
    db.commit()
    return RedirectResponse(url="/admin/stations", status_code=303)


@app.get("/admin/stations/{station_id}/offers", response_class=HTMLResponse)
def admin_station_offers(station_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    offers = (
        db.query(Offer)
        .filter(Offer.provider == "paystack")
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

    return HTMLResponse(
        "<h1>Offres de la station</h1>"
        f"<p>Station: {station.code} - {station.name}</p>"
        f"<form method='post' action='/admin/offers/clone-global-to-station/{station_id}' style='margin-bottom:12px'>"
        "<label><input type='checkbox' name='override_existing' value='1'/> Remplacer si existe</label>"
        "<button type='submit'>Dupliquer offres globales vers cette station</button>"
        "</form>"
        f"<form method='post' action='/admin/stations/{station_id}/offers'>"
        "<table border='1'><tr><th>ID</th><th>Nom</th><th>Duree</th><th>Prix</th><th>Provider</th><th>Attacher</th></tr>"
        f"{offers_rows}</table>"
        "<button type='submit' style='margin-top:12px'>Enregistrer</button></form>"
        "<p><a href='/admin/stations'>Retour</a></p>"
    )


@app.post("/admin/stations/{station_id}/offers")
async def admin_station_offers_post(station_id: int, request: Request, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    form = await request.form()
    raw_ids = form.getlist("offer_ids")
    offer_ids = [int(x) for x in raw_ids if str(x).isdigit()]

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


@app.get("/admin/salles", response_class=HTMLResponse)
def admin_salles(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    salles = db.query(Salle).order_by(Salle.id.desc()).all()

    manager_role_key = "manager"
    responsable_role_key = "responsable"
    salle_ids = [s.id for s in salles]

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

    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.id.desc()).all()
    manager_choices = "".join(
        [
            f"<label><input type='checkbox' name='manager_user_ids' value='{u.id}'/> {u.name}</label><br/>"
            for u in users
        ]
    )
    responsable_choices = "".join(
        [
            f"<label><input type='checkbox' name='responsable_user_ids' value='{u.id}'/> {u.name}</label><br/>"
            for u in users
        ]
    )

    rows = "".join(
        [
            f"<tr>"
            f"<td>{sl.id}</td>"
            f"<td>{sl.code}</td>"
            f"<td>{sl.name}</td>"
            f"<td>{', '.join(names_by_salle_role.get((sl.id, manager_role_key), []))}</td>"
            f"<td>{', '.join(names_by_salle_role.get((sl.id, responsable_role_key), []))}</td>"
            f"<td><a href='/admin/salles/{sl.id}/offers'>Offres</a></td>"
            f"<td><a href='/admin/salles/{sl.id}/stations'>Stations</a></td>"
            f"<td><a href='/admin/salles/{sl.id}/edit'>Edit</a></td>"
            f"<td>"
            f"<form method='post' action='/admin/salles/{sl.id}/delete' onsubmit=\"return confirm('Supprimer cette salle ?');\">"
            f"<button type='submit'>Delete</button>"
            f"</form>"
            f"</td>"
            f"</tr>"
            for sl in salles
        ]
    )
    return HTMLResponse(
        "<h1>Admin Salles</h1>"
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
        "<table border='1'><tr><th>ID</th><th>Code</th><th>Nom</th><th>Gérant</th><th>Responsable</th><th>Offres</th><th>Stations</th><th></th><th></th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>"
    )


@app.get("/admin/salles/{salle_id}/stations", response_class=HTMLResponse)
def admin_salle_stations(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

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

    return HTMLResponse(
        f"<h1>Stations - {salle.code}</h1>"
        f"<p>{salle.name}</p>"
        f"<form method='post' action='/admin/salles/{salle_id}/reset-sessions' onsubmit=\"return confirm('Supprimer les sessions pending/active pour toutes les stations de cette salle ?');\">"
        "<button type='submit' style='margin-bottom:12px'>Reset sessions (salle)</button>"
        "</form>"
        "<table border='1'><tr><th>ID</th><th>Code</th><th>Nom</th><th>IP</th><th>Actif</th><th>Offres</th><th>Edit</th><th>Reset</th></tr>"
        f"{rows}</table>"
        "<p><a href='/admin/salles'>Retour</a></p>"
    )


@app.post("/admin/salles/{salle_id}/reset-sessions")
def reset_salle_sessions(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    station_ids = [r[0] for r in db.query(Station.id).filter(Station.salle_id == salle_id).all()]
    if not station_ids:
        return RedirectResponse(url=f"/admin/salles/{salle_id}/stations", status_code=303)

    session_ids_rows = (
        db.query(GameSession.id)
        .filter(GameSession.station_id.in_(station_ids), GameSession.status.in_(("pending", "active")))
        .all()
    )
    session_ids = [r[0] for r in session_ids_rows]

    if session_ids:
        db.query(EventLog).filter(EventLog.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(SessionExtension).filter(SessionExtension.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(GameSession).filter(GameSession.id.in_(session_ids)).delete(synchronize_session=False)
        db.commit()

    return RedirectResponse(url=f"/admin/salles/{salle_id}/stations", status_code=303)


@app.post("/admin/salles")
async def create_salle(
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
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


@app.get("/admin/salles/{salle_id}/edit", response_class=HTMLResponse)
def edit_salle(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

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

    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.id.desc()).all()
    manager_choices = "".join(
        [
            f"<label><input type='checkbox' name='manager_user_ids' value='{u.id}' {'checked' if u.id in assigned_manager_ids else ''}/> {u.name}</label><br/>"
            for u in users
        ]
    )
    responsable_choices = "".join(
        [
            f"<label><input type='checkbox' name='responsable_user_ids' value='{u.id}' {'checked' if u.id in assigned_responsable_ids else ''}/> {u.name}</label><br/>"
            for u in users
        ]
    )

    return HTMLResponse(
        "<h1>Edit Salle</h1>"
        f"<form method='post' action='/admin/salles/{salle_id}/update'>"
        f"<input name='code' required value='{salle.code}'/>"
        f"<input name='name' required value='{salle.name}'/>"
        f"<input name='latitude' placeholder='Latitude' value='{salle.latitude or ''}'/>"
        f"<input name='longitude' placeholder='Longitude' value='{salle.longitude or ''}'/>"
        "<div><b>Gérants</b></div>"
        f"{manager_choices}"
        "<div style='margin-top:8px'><b>Responsables</b></div>"
        f"{responsable_choices}"
        "<button type='submit'>Mettre à jour</button>"
        "</form>"
        "<p><a href='/admin/salles'>Retour</a></p>"
    )


@app.post("/admin/salles/{salle_id}/update")
async def update_salle(
    salle_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
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

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")
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
def delete_salle(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")
    used = db.query(Station).filter(Station.salle_id == salle_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="Salle utilisée par des stations : suppression refusée")

    db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id).delete()
    db.query(SalleUser).filter(SalleUser.salle_id == salle_id).delete(synchronize_session=False)
    db.delete(salle)
    db.commit()
    return RedirectResponse(url="/admin/salles", status_code=303)


@app.get("/admin/salles/{salle_id}/offers", response_class=HTMLResponse)
def admin_salle_offers(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    offers = (
        db.query(Offer)
        .filter(Offer.provider == "paystack")
        .filter(Offer.is_active.is_(True))
        .order_by(Offer.duration_minutes.asc(), Offer.price_xof.asc(), Offer.id.asc())
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

    return HTMLResponse(
        "<h1>Offres de la salle</h1>"
        f"<p>Salle: {salle.code} - {salle.name}</p>"
        f"<form method='post' action='/admin/salles/{salle_id}/offers'>"
        "<table border='1'><tr><th>ID</th><th>Nom</th><th>Duree</th><th>Prix</th><th>Provider</th><th>Attacher</th></tr>"
        f"{offers_rows}</table>"
        "<button type='submit' style='margin-top:12px'>Enregistrer</button></form>"
        "<p><a href='/admin/salles'>Retour</a></p>"
    )


@app.post("/admin/salles/{salle_id}/offers")
async def admin_salle_offers_post(salle_id: int, request: Request, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    form = await request.form()
    raw_ids = form.getlist("offer_ids")
    offer_ids = [int(x) for x in raw_ids if str(x).isdigit()]

    active_ids = {
        o.id
        for o in db.query(Offer).filter(Offer.id.in_(offer_ids), Offer.is_active.is_(True)).all()
    }

    db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id).delete()
    for oid in active_ids:
        db.add(SalleOffer(salle_id=salle_id, offer_id=oid, is_active=True))
    db.commit()
    return RedirectResponse(url=f"/admin/salles/{salle_id}/offers", status_code=303)


@app.get("/admin/sessions", response_class=HTMLResponse)
def admin_sessions(db: Session = Depends(get_db), _: str = Depends(require_admin)):
    sessions = db.query(GameSession).order_by(GameSession.id.desc()).limit(100).all()
    rows_parts = []
    for s in sessions:
        if s.status == "active":
            extend_cell = (
                f"<td><form method='post' action='/admin/sessions/{s.id}/extend'>"
                "<input name='minutes' type='number' min='1' required value='10'/>"
                "<button type='submit'>+10m</button></form></td>"
            )
        else:
            extend_cell = "<td></td>"

        rows_parts.append(
            "<tr>"
            f"<td>{s.id}</td>"
            f"<td>{s.payment_reference}</td>"
            f"<td>{s.payment_provider}</td>"
            f"<td>{s.payment_status}</td>"
            f"<td>{s.status}</td>"
            f"<td>{s.started_at}</td>"
            f"<td>{s.end_at}</td>"
            f"{extend_cell}"
            "</tr>"
        )
    rows = "".join(rows_parts)
    return HTMLResponse(
        "<h1>Admin Sessions</h1>"
        "<table border='1'><tr><th>ID</th><th>Reference</th><th>Provider</th><th>Pay</th><th>Status</th><th>Start</th><th>End</th><th>Extend</th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>"
    )


@app.post("/admin/sessions/{session_id}/extend")
def admin_extend_session(
    session_id: int,
    minutes: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status != "active":
        raise HTTPException(status_code=400, detail="Session non active")
    extend_session_end_at(db, session, minutes, source="admin")
    return RedirectResponse(url="/admin/sessions", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(), "delta": timedelta(seconds=0).total_seconds()}
