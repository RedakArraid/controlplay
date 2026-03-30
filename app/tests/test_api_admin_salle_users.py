"""API admin JSON : gestion des users rattachés à une salle (gérant / responsable)."""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import database as database_module  # noqa: E402
import main as main_module  # noqa: E402
import models  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(main_module.app) as c:
        yield c


def _login_admin(client: TestClient) -> None:
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


def test_api_admin_salle_users_assign_and_update(client: TestClient) -> None:
    _login_admin(client)

    code = f"api-salle-users-{uuid.uuid4().hex[:8]}"
    r_salle = client.post(
        "/api/admin/salles",
        json={
            "code": code,
            "name": "Salle API Users",
            "latitude": None,
            "longitude": None,
        },
    )
    assert r_salle.status_code == 200
    salle_id = r_salle.json()["salle"]["id"]

    # Créer deux users directement en base (Test env).
    db = database_module.SessionLocal()
    try:
        u1 = models.User(
            name="User Manager",
            email=f"u1-{uuid.uuid4().hex[:8]}@test.local",
            phone=None,
            avatar=None,
            password_hash=main_module.hash_password("pw-123"),
            is_active=True,
            created_by_user_id=None,
        )
        u2 = models.User(
            name="User Responsable",
            email=f"u2-{uuid.uuid4().hex[:8]}@test.local",
            phone=None,
            avatar=None,
            password_hash=main_module.hash_password("pw-123"),
            is_active=True,
            created_by_user_id=None,
        )
        db.add(u1)
        db.add(u2)
        db.flush()
        db.commit()
        u1_id = u1.id
        u2_id = u2.id
    finally:
        db.close()

    # Assigner : u1 gérant, u2 responsable.
    r_put = client.put(
        f"/api/admin/salles/{salle_id}/users",
        json={"manager_user_ids": [u1_id], "responsable_user_ids": [u2_id]},
    )
    assert r_put.status_code == 200
    assert r_put.json()["ok"] is True

    r_get = client.get(f"/api/admin/salles/{salle_id}/users")
    assert r_get.status_code == 200
    data = r_get.json()

    u1_row = next(u for u in data["users"] if u["id"] == u1_id)
    u2_row = next(u for u in data["users"] if u["id"] == u2_id)
    assert u1_row["is_manager"] is True
    assert u1_row["is_responsable"] is False
    assert u2_row["is_responsable"] is True
    assert u2_row["is_manager"] is False

    # Mise à jour : retirer le gérant.
    r_put2 = client.put(
        f"/api/admin/salles/{salle_id}/users",
        json={"manager_user_ids": [], "responsable_user_ids": [u2_id]},
    )
    assert r_put2.status_code == 200
    assert r_put2.json()["ok"] is True

    r_get2 = client.get(f"/api/admin/salles/{salle_id}/users")
    assert r_get2.status_code == 200
    data2 = r_get2.json()
    u1_row2 = next(u for u in data2["users"] if u["id"] == u1_id)
    u2_row2 = next(u for u in data2["users"] if u["id"] == u2_id)
    assert u1_row2["is_manager"] is False
    assert u2_row2["is_responsable"] is True

