"""API admin JSON : CRUD de base des salles (phase P1 SPA)."""
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


def test_api_admin_salles_create_then_update(client: TestClient) -> None:
    _login_admin(client)
    code = f"api-salle-{uuid.uuid4().hex[:8]}"

    r_create = client.post(
        "/api/admin/salles",
        json={
            "code": code,
            "name": "Salle API JSON",
            "latitude": 5.355,
            "longitude": -4.012,
        },
    )
    assert r_create.status_code == 200
    created = r_create.json()["salle"]
    assert created["code"] == code
    assert created["latitude"] == pytest.approx(5.355)
    assert created["longitude"] == pytest.approx(-4.012)

    salle_id = created["id"]
    r_update = client.put(
        f"/api/admin/salles/{salle_id}",
        json={
            "code": code,
            "name": "Salle API JSON MAJ",
            "latitude": 5.4,
            "longitude": -3.98,
        },
    )
    assert r_update.status_code == 200
    updated = r_update.json()["salle"]
    assert updated["name"] == "Salle API JSON MAJ"
    assert updated["latitude"] == pytest.approx(5.4)
    assert updated["longitude"] == pytest.approx(-3.98)
