"""Tests HTTP : login par session, /admin, /super-admin, logout."""
from __future__ import annotations

import os
import sys
import urllib.parse
import uuid

import pytest
from fastapi.testclient import TestClient

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import database as database_module  # noqa: E402
import main as main_module  # noqa: E402
import models as models_module  # noqa: E402
from main import hash_password  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(main_module.app) as c:
        yield c


def test_admin_redirects_to_login_without_session(client: TestClient) -> None:
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers.get("location", "")
    assert loc.startswith("/login?next=")


def test_super_admin_redirects_to_login_without_session(client: TestClient) -> None:
    r = client.get("/super-admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location", "").startswith("/login?next=")


def test_login_page_returns_form(client: TestClient) -> None:
    r = client.get("/login")
    assert r.status_code == 200
    assert "Connexion" in r.text
    assert "name='identifier'" in r.text or 'name="identifier"' in r.text


def test_login_bad_password_returns_200_with_error(client: TestClient) -> None:
    r = client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": "definitely-wrong-password",
            "next": "/admin",
        },
    )
    assert r.status_code == 200
    assert "Identifiants incorrects" in r.text


def test_connexion_page_admin_avec_next_vers_panel(client: TestClient) -> None:
    """GET /login?next=/admin affiche le formulaire avec next ; POST → /admin (compte seed super_admin)."""
    # Utiliser params= pour encoder correctement next=/admin (sinon certains clients parsent mal le « / »).
    r_page = client.get("/login", params={"next": "/admin"})
    assert r_page.status_code == 200
    assert 'name="next"' in r_page.text or "name='next'" in r_page.text
    assert "/admin" in r_page.text

    r = client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/admin",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers.get("location") == "/admin"
    r_admin = client.get("/admin")
    assert r_admin.status_code == 200
    assert "admin" in r_admin.text.lower()


def test_connexion_page_super_admin_avec_next_vers_espace(client: TestClient) -> None:
    """GET /login?next=/super-admin puis POST → /super-admin (hub super admin)."""
    r_page = client.get("/login?next=" + urllib.parse.quote("/super-admin"))
    assert r_page.status_code == 200
    assert "/super-admin" in r_page.text

    r = client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/super-admin",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers.get("location") == "/super-admin"
    r_hub = client.get("/super-admin")
    assert r_hub.status_code == 200
    assert (
        "super administrateur" in r_hub.text.lower()
        or "super admin" in r_hub.text.lower()
    )


def test_connexion_salle_admin_seule_next_super_admin_redirige_mais_hub_403(
    client: TestClient,
) -> None:
    """Compte uniquement salle_admin : POST next=/super-admin pose la session ; GET /super-admin → 403."""
    db = database_module.SessionLocal()
    try:
        role = db.query(models_module.Role).filter_by(key="salle_admin").first()
        assert role is not None
        salle = db.query(models_module.Salle).first()
        assert salle is not None
        u = models_module.User(
            name="Salle next super",
            email="salle_next_super@test.com",
            phone=None,
            password_hash=hash_password("salleNextPw1"),
            is_active=True,
        )
        db.add(u)
        db.flush()
        db.add(
            models_module.SalleUser(
                salle_id=salle.id,
                user_id=u.id,
                role_id=role.id,
            )
        )
        db.commit()
    finally:
        db.close()

    client.get("/logout", follow_redirects=True)

    r_post = client.post(
        "/login",
        data={
            "identifier": "salle_next_super@test.com",
            "password": "salleNextPw1",
            "next": "/super-admin",
        },
        follow_redirects=False,
    )
    assert r_post.status_code == 303
    assert r_post.headers.get("location") == "/super-admin"

    r_hub = client.get("/super-admin", follow_redirects=False)
    assert r_hub.status_code == 403

    r_admin = client.get("/admin")
    assert r_admin.status_code == 200


def test_login_success_redirects_and_admin_accessible(client: TestClient) -> None:
    r = client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/admin",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers.get("location") == "/admin"

    r2 = client.get("/admin")
    assert r2.status_code == 200
    assert "Admin" in r2.text or "admin" in r2.text.lower()


def test_super_admin_hub_after_login(client: TestClient) -> None:
    client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/super-admin",
        },
        follow_redirects=True,
    )
    r = client.get("/super-admin")
    assert r.status_code == 200
    assert "super administrateur" in r.text.lower() or "Super admin" in r.text


def test_super_admin_users_page_contains_nav(client: TestClient) -> None:
    client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/admin",
        },
        follow_redirects=True,
    )
    r = client.get("/super-admin/users")
    assert r.status_code == 200
    assert "/super-admin/providers" in r.text
    assert "Utilisateurs" in r.text


def test_logout_clears_session(client: TestClient) -> None:
    client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/admin",
        },
        follow_redirects=True,
    )
    r_out = client.get("/logout", follow_redirects=False)
    assert r_out.status_code == 303
    assert r_out.headers.get("location") == "/login"

    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location", "").startswith("/login?next=")


def test_salle_scoped_only_gets_403_on_super_admin(client: TestClient) -> None:
    db = database_module.SessionLocal()
    try:
        role = db.query(models_module.Role).filter_by(key="salle_admin").first()
        assert role is not None
        salle = db.query(models_module.Salle).first()
        assert salle is not None
        u = models_module.User(
            name="Salle only",
            email="salle_only_auth@test.com",
            phone=None,
            password_hash=hash_password("sallepw123"),
            is_active=True,
        )
        db.add(u)
        db.flush()
        db.add(
            models_module.SalleUser(
                salle_id=salle.id,
                user_id=u.id,
                role_id=role.id,
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/login",
        data={
            "identifier": "salle_only_auth@test.com",
            "password": "sallepw123",
            "next": "/admin",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r2 = client.get("/super-admin", follow_redirects=False)
    assert r2.status_code == 403


def test_gerant_ne_peut_pas_etre_manager_sur_deux_salles(client: TestClient) -> None:
    """Un compte déjà gérant sur une salle ne peut pas être gérant sur une autre."""
    db = database_module.SessionLocal()
    try:
        s2 = models_module.Salle(code=f"s2-{uuid.uuid4().hex[:8]}", name="Salle 2 test")
        db.add(s2)
        db.commit()
        db.refresh(s2)
        s2_id = s2.id
        s1 = db.query(models_module.Salle).filter(models_module.Salle.id != s2_id).first()
        assert s1 is not None
        s1_id = s1.id
    finally:
        db.close()

    client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/admin",
        },
        follow_redirects=True,
    )
    email_g = f"gerant_{uuid.uuid4().hex}@pytest.local"
    r1 = client.post(
        f"/admin/salles/{s1_id}/users",
        data={
            "name": "Gérant test",
            "email": email_g,
            "password": "gerantpw123",
            "is_active": "1",
            "make_manager": "1",
        },
        follow_redirects=False,
    )
    assert r1.status_code == 303

    r2 = client.post(
        f"/admin/salles/{s2_id}/users",
        data={
            "name": "Gérant test",
            "email": email_g,
            "password": "gerantpw123",
            "is_active": "1",
            "make_manager": "1",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 400


def test_post_admin_providers_duplicate_keys_last_wins(client: TestClient) -> None:
    """Documente Starlette : même nom plusieurs fois → .get() retient la dernière valeur."""
    client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/admin",
        },
        follow_redirects=True,
    )
    client.post(
        "/admin/providers",
        data={
            "paystack_enabled": "1",
            "cinetpay_enabled": "1",
            "redirect_after": "/admin/providers",
        },
        follow_redirects=False,
    )
    body = urllib.parse.urlencode(
        [
            ("paystack_enabled", "1"),
            ("paystack_enabled", "0"),
            ("cinetpay_enabled", "1"),
            ("cinetpay_enabled", "0"),
            ("redirect_after", "/admin/providers"),
        ]
    )
    r = client.post(
        "/admin/providers",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = database_module.SessionLocal()
    try:
        cfg = (
            db.query(models_module.PaymentProviderConfig)
            .order_by(models_module.PaymentProviderConfig.id.asc())
            .first()
        )
        assert cfg is not None
        assert cfg.paystack_enabled is False
        assert cfg.cinetpay_enabled is False
    finally:
        db.close()


def test_post_admin_providers_checkbox_values_persist(client: TestClient) -> None:
    """Régression : hidden name=paystack_enabled après la case écrasait la valeur (dernière clé gagne)."""
    client.post(
        "/login",
        data={
            "identifier": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
            "next": "/admin",
        },
        follow_redirects=True,
    )
    r_on = client.post(
        "/admin/providers",
        data={
            "paystack_enabled": "1",
            "cinetpay_enabled": "1",
            "redirect_after": "/admin/providers",
        },
        follow_redirects=False,
    )
    assert r_on.status_code == 303
    db = database_module.SessionLocal()
    try:
        cfg = (
            db.query(models_module.PaymentProviderConfig)
            .order_by(models_module.PaymentProviderConfig.id.asc())
            .first()
        )
        assert cfg is not None
        assert cfg.paystack_enabled is True
        assert cfg.cinetpay_enabled is True
    finally:
        db.close()

    r_off = client.post(
        "/admin/providers",
        data={"redirect_after": "/admin/providers"},
        follow_redirects=False,
    )
    assert r_off.status_code == 303
    db = database_module.SessionLocal()
    try:
        cfg = (
            db.query(models_module.PaymentProviderConfig)
            .order_by(models_module.PaymentProviderConfig.id.asc())
            .first()
        )
        assert cfg is not None
        assert cfg.paystack_enabled is False
        assert cfg.cinetpay_enabled is False
    finally:
        db.close()
