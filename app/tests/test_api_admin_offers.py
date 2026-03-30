"""API admin JSON : CRUD de base des offres (templates)."""
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


def test_api_admin_offers_create_then_update_then_delete(client: TestClient) -> None:
    _login_admin(client)

    offer_name = f"offer-api-{uuid.uuid4().hex[:8]}"
    r_create = client.post(
        "/api/admin/offers",
        json={
            "name": offer_name,
            "duration_minutes": 30,
            "price_xof": 250,
            "is_active": True,
        },
    )
    assert r_create.status_code == 200
    offer_id = r_create.json()["offer"]["id"]

    r_update = client.put(
        f"/api/admin/offers/{offer_id}",
        json={
            "name": offer_name + "-maj",
            "duration_minutes": 45,
            "price_xof": 300,
            "is_active": True,
        },
    )
    assert r_update.status_code == 200
    assert r_update.json()["offer"]["duration_minutes"] == 45

    r_del = client.post(f"/api/admin/offers/{offer_id}/delete")
    assert r_del.status_code == 200
    # Pas de vérif GET ici : l'endpoint liste ne retourne que les offres is_active=True.

