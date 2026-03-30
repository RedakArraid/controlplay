"""API super-admin : réinitialisation de mots de passe en masse."""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main as main_module  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(main_module.app) as c:
        yield c


def _login_super(client: TestClient) -> None:
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


def test_api_super_admin_bulk_password_reset_then_login(client: TestClient) -> None:
    _login_super(client)
    email = f"bulk-pw-{uuid.uuid4().hex[:10]}@test.com"
    r_create = client.post(
        "/api/super-admin/users",
        json={
            "name": "Bulk PW Target",
            "email": email,
            "phone": None,
            "password": "OldPassword123!",
            "is_active": True,
            "global_roles": ["salle_admin"],
        },
    )
    assert r_create.status_code == 200
    user_id = r_create.json()["user_id"]

    r_reset = client.post(
        "/api/super-admin/users/bulk-password-reset",
        json={"user_ids": [user_id]},
    )
    assert r_reset.status_code == 200
    data = r_reset.json()
    assert data["ok"] is True
    assert len(data["results"]) == 1
    row = data["results"][0]
    assert row["user_id"] == user_id
    assert len(row["password"]) >= 8

    new_pw = row["password"]
    client.get("/logout", follow_redirects=False)
    r_login = client.post(
        "/login",
        data={
            "identifier": email,
            "password": new_pw,
            "next": "/admin",
        },
        follow_redirects=False,
    )
    assert r_login.status_code == 303


def test_api_super_admin_users_filter_sort_and_pagination(client: TestClient) -> None:
    _login_super(client)
    uniq = uuid.uuid4().hex[:8]
    payloads = [
        {
            "name": f"Zed {uniq}",
            "email": f"zed-{uniq}@test.com",
            "phone": None,
            "password": "Pass12345!",
            "is_active": True,
            "global_roles": ["admin"],
        },
        {
            "name": f"Ana {uniq}",
            "email": f"ana-{uniq}@test.com",
            "phone": None,
            "password": "Pass12345!",
            "is_active": True,
            "global_roles": ["salle_admin"],
        },
        {
            "name": f"Moe {uniq}",
            "email": f"moe-{uniq}@test.com",
            "phone": None,
            "password": "Pass12345!",
            "is_active": False,
            "global_roles": ["admin"],
        },
    ]
    for body in payloads:
        r_create = client.post("/api/super-admin/users", json=body)
        assert r_create.status_code == 200

    r = client.get(
        "/api/super-admin/users",
        params={
            "q": uniq,
            "status": "active",
            "role": "admin",
            "sort_by": "name",
            "sort_dir": "asc",
            "page": 1,
            "page_size": 1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert len(data["users"]) == 1
    row = data["users"][0]
    assert uniq in row["name"]
    assert row["is_active"] is True
    assert "admin" in row["global_roles"]
