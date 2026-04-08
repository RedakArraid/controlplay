import os
import re
import secrets
import requests
from uuid import uuid4

from sqlalchemy.orm import Session

from dependencies import hash_password
from models import Role, User, UserRole

DEFAULT_USER_EMAIL = "default_user@controlplay.local"
DEFAULT_PAYSTACK_EMAIL_DOMAIN = "example.com"

def get_paystack_email(customer_email: str | None, customer_phone: str | None) -> str:
    if customer_email and customer_email.strip():
        return customer_email.strip()
    if customer_phone and customer_phone.strip():
        local_part = re.sub(r"\D+", "", customer_phone.strip())
        if local_part: return f"{local_part}@{DEFAULT_PAYSTACK_EMAIL_DOMAIN}"
    return f"default_user@{DEFAULT_PAYSTACK_EMAIL_DOMAIN}"

def verify_paystack_transaction(reference: str) -> bool:
    secret_key = os.getenv("PAYSTACK_SECRET_KEY", "")
    if not secret_key or "xxx" in secret_key: return False
    try:
        response = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers={"Authorization": f"Bearer {secret_key}"}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("status")) and payload.get("data", {}).get("status") == "success"
    except requests.RequestException:
        return False

def verify_cinetpay_transaction(reference: str) -> bool:
    api_key = os.getenv("CINETPAY_API_KEY", "")
    site_id = os.getenv("CINETPAY_SITE_ID", "")
    if not api_key or not site_id or "xxx" in api_key: return False
    try:
        response = requests.post("https://api-checkout.cinetpay.com/v2/payment/check", json={"apikey": api_key, "site_id": site_id, "transaction_id": reference}, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", {})
        return str(data.get("status", "")).upper() == "ACCEPTED"
    except requests.RequestException:
        return False

def verify_transaction(provider: str, reference: str) -> bool:
    if provider == "paystack": return verify_paystack_transaction(reference)
    if provider == "cinetpay": return verify_cinetpay_transaction(reference)
    return False

def is_paystack_api_configured() -> bool:
    secret = os.getenv("PAYSTACK_SECRET_KEY", "")
    return bool(secret) and "xxx" not in secret.lower()

def is_paystack_webhook_secret_configured() -> bool:
    wh = os.getenv("PAYSTACK_WEBHOOK_SECRET", "")
    return bool(wh) and "xxx" not in wh.lower()

def is_paystack_configured() -> bool:
    return is_paystack_api_configured()

def is_cinetpay_configured() -> bool:
    api_key = os.getenv("CINETPAY_API_KEY", "")
    site_id = os.getenv("CINETPAY_SITE_ID", "")
    return bool(api_key) and bool(site_id) and "xxx" not in api_key and "xxx" not in site_id

def is_cinetpay_webhook_secret_configured() -> bool:
    secret = os.getenv("CINETPAY_SECRET_KEY", "")
    return bool(secret) and "xxx" not in secret.lower()

def make_payment_reference(provider: str) -> str:
    base = uuid4().hex[:18]
    if provider == "cinetpay": return f"cp{base}"
    return f"ps-{base}"

def get_base_url() -> str:
    return os.getenv("BASE_URL", "http://localhost:8000")

def paystack_amount_units(amount_main: int) -> int:
    mult = int(os.getenv("PAYSTACK_AMOUNT_MULTIPLIER", "100"))
    return int(amount_main) * mult

def init_paystack_payment(reference: str, email: str | None, amount_xof: int, callback_url: str | None = None) -> str:
    if not is_paystack_api_configured(): raise RuntimeError("Paystack non configuré")
    secret_key = os.getenv("PAYSTACK_SECRET_KEY", "")
    if callback_url is None: callback_url = f"{get_base_url()}/payments/return/paystack/{reference}"
    payload = {
        "amount": paystack_amount_units(amount_xof),
        "reference": reference,
        "currency": os.getenv("PAYSTACK_CURRENCY", "XOF"),
        "callback_url": callback_url,
    }
    if email: payload["email"] = email
    response = requests.post("https://api.paystack.co/transaction/initialize", headers={"Authorization": f"Bearer {secret_key}"}, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    authorization_url = (data.get("data") or {}).get("authorization_url")
    if not data.get("status") or not authorization_url: raise RuntimeError(f"Paystack init invalide: {data}")
    return authorization_url

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


def init_cinetpay_payment(transaction_id: str, amount_xof: int, description: str) -> str:
    if not is_cinetpay_configured(): raise RuntimeError("CinetPay non configuré")
    if amount_xof % 5 != 0: raise RuntimeError("Le montant CinetPay doit être un multiple de 5")
    payload = {
        "apikey": os.getenv("CINETPAY_API_KEY", ""),
        "site_id": os.getenv("CINETPAY_SITE_ID", ""),
        "transaction_id": transaction_id,
        "amount": int(amount_xof),
        "currency": "XOF",
        "description": description,
        "notify_url": f"{get_base_url()}/webhooks/cinetpay",
        "return_url": f"{get_base_url()}/payments/return/cinetpay",
        "channels": "ALL",
    }
    response = requests.post("https://api-checkout.cinetpay.com/v2/payment", json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    payment_url = (data.get("data") or {}).get("payment_url")
    if not data.get("code") or not payment_url: raise RuntimeError(f"CinetPay init invalide: {data}")
    return payment_url
