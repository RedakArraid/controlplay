"""
Paiements : Paystack (PSP primaire), CinetPay (secours).
Une seule source de vérité pour clés env, vérif API et flags base (PaymentProviderConfig).
"""
from __future__ import annotations

import os
import re
import secrets
from uuid import uuid4

import requests
from sqlalchemy.orm import Session

from database import SessionLocal
from dependencies import hash_password
from models import PaymentProviderConfig, Role, User, UserRole

DEFAULT_USER_EMAIL = "default_user@controlplay.local"
DEFAULT_PAYSTACK_EMAIL_DOMAIN = "example.com"


def _env_looks_placeholder(value: str) -> bool:
    v = value.strip().lower()
    return not v or "xxx" in v or v in ("changeme", "change-me")


def get_payment_provider_config() -> PaymentProviderConfig | None:
    """Lit la ligne de config PSP (activation Paystack / CinetPay depuis /super-admin/providers)."""
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


def get_paystack_email(customer_email: str | None, customer_phone: str | None) -> str:
    if customer_email and customer_email.strip():
        return customer_email.strip()
    if customer_phone and customer_phone.strip():
        local_part = re.sub(r"\D+", "", customer_phone.strip())
        if local_part:
            return f"{local_part}@{DEFAULT_PAYSTACK_EMAIL_DOMAIN}"
    return f"default_user@{DEFAULT_PAYSTACK_EMAIL_DOMAIN}"


def verify_paystack_transaction(reference: str) -> bool:
    secret_key = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    if _env_looks_placeholder(secret_key):
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
    api_key = os.getenv("CINETPAY_API_KEY", "").strip()
    site_id = os.getenv("CINETPAY_SITE_ID", "").strip()
    if _env_looks_placeholder(api_key) or not site_id or _env_looks_placeholder(site_id):
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


def is_paystack_api_configured() -> bool:
    """Clé secrète suffisante pour initialize + verify Paystack."""
    if not paystack_enabled():
        return False
    secret = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    return bool(secret) and not _env_looks_placeholder(secret)


def is_paystack_webhook_secret_configured() -> bool:
    """Secret dashboard Paystack pour valider x-paystack-signature (recommandé en prod)."""
    if not paystack_enabled():
        return False
    wh = os.getenv("PAYSTACK_WEBHOOK_SECRET", "").strip()
    return bool(wh) and not _env_looks_placeholder(wh)


def is_paystack_configured() -> bool:
    """Paiement Paystack utilisable : activé en base + clé API valide."""
    return is_paystack_api_configured()


def is_cinetpay_configured() -> bool:
    if not cinetpay_enabled():
        return False
    api_key = os.getenv("CINETPAY_API_KEY", "").strip()
    site_id = os.getenv("CINETPAY_SITE_ID", "").strip()
    if not api_key or not site_id:
        return False
    return not _env_looks_placeholder(api_key) and not _env_looks_placeholder(site_id)


def is_cinetpay_webhook_secret_configured() -> bool:
    """CINETPAY_SECRET_KEY pour valider le header x-token du webhook."""
    if not cinetpay_enabled():
        return False
    secret = os.getenv("CINETPAY_SECRET_KEY", "").strip()
    return bool(secret) and not _env_looks_placeholder(secret)


def make_payment_reference(provider: str) -> str:
    """
    Références pour retrouver les transactions (webhooks / retours navigateur).
    Paystack accepte mal certains caractères → préfixe ps-<hex>.
    CinetPay → cp<hex>.
    """
    base = uuid4().hex[:18]
    if provider == "cinetpay":
        return f"cp{base}"
    return f"ps-{base}"


def get_base_url() -> str:
    return os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")


def paystack_amount_units(amount_main: int) -> int:
    """Montant envoyé à Paystack (entier). XOF défaut × PAYSTACK_AMOUNT_MULTIPLIER."""
    mult = int(os.getenv("PAYSTACK_AMOUNT_MULTIPLIER", "100"))
    return int(amount_main) * mult


def init_paystack_payment(
    reference: str,
    email: str | None,
    amount_xof: int,
    callback_url: str | None = None,
) -> str:
    if not is_paystack_api_configured():
        raise RuntimeError("Paystack non configuré (PAYSTACK_SECRET_KEY)")
    secret_key = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    if callback_url is None:
        callback_url = f"{get_base_url()}/payments/return/paystack/{reference}"
    currency = os.getenv("PAYSTACK_CURRENCY", "XOF")
    payload = {
        "amount": paystack_amount_units(amount_xof),
        "reference": reference,
        "currency": currency,
        "callback_url": callback_url,
    }
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
    if not is_cinetpay_configured():
        raise RuntimeError("CinetPay non configuré")
    api_key = os.getenv("CINETPAY_API_KEY", "").strip()
    site_id = os.getenv("CINETPAY_SITE_ID", "").strip()
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


def get_default_user(db: Session) -> User:
    user = db.query(User).filter(User.email == DEFAULT_USER_EMAIL).first()
    if user:
        return user
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
        if email_v and not user.email:
            user.email = email_v
            db.commit()
        return user
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
    joueur_role = db.query(Role).filter(Role.key == "joueur").first()
    if joueur_role:
        db.add(UserRole(user_id=user.id, role_id=joueur_role.id))
        db.commit()
    return user
