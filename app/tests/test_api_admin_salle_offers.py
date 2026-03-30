"""API admin JSON : offres rattachées à une salle (SPA salle d'abord)."""
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


def test_api_admin_salle_offers_attach_and_detach(client: TestClient) -> None:
    _login_admin(client)

    salle_code = f"api-salle-offers-{uuid.uuid4().hex[:8]}"
    r_salle = client.post(
        "/api/admin/salles",
        json={"code": salle_code, "name": "Salle Offres API", "latitude": None, "longitude": None},
    )
    assert r_salle.status_code == 200
    salle_id = r_salle.json()["salle"]["id"]

    offer_1_name = f"offer1-{uuid.uuid4().hex[:6]}"
    r_offer1 = client.post(
        "/api/admin/offers",
        json={
            "name": offer_1_name,
            "duration_minutes": 15,
            "price_xof": 120,
            "is_active": True,
        },
    )
    assert r_offer1.status_code == 200
    offer1_id = r_offer1.json()["offer"]["id"]

    offer_2_name = f"offer2-{uuid.uuid4().hex[:6]}"
    r_offer2 = client.post(
        "/api/admin/offers",
        json={
            "name": offer_2_name,
            "duration_minutes": 30,
            "price_xof": 200,
            "is_active": True,
        },
    )
    assert r_offer2.status_code == 200
    offer2_id = r_offer2.json()["offer"]["id"]

    r_get_0 = client.get(f"/api/admin/salles/{salle_id}/offers")
    assert r_get_0.status_code == 200
    assert all(not o["attached"] for o in r_get_0.json()["offers"])

    r_put = client.put(
        f"/api/admin/salles/{salle_id}/offers",
        json={"offer_ids": [offer1_id]},
    )
    assert r_put.status_code == 200

    r_get_1 = client.get(f"/api/admin/salles/{salle_id}/offers")
    data1 = r_get_1.json()
    assert any(o["id"] == offer1_id and o["attached"] for o in data1["offers"])
    assert any(o["id"] == offer2_id and not o["attached"] for o in data1["offers"])

    # Update à deux offres
    r_put2 = client.put(
        f"/api/admin/salles/{salle_id}/offers",
        json={"offer_ids": [offer1_id, offer2_id]},
    )
    assert r_put2.status_code == 200

    r_get_2 = client.get(f"/api/admin/salles/{salle_id}/offers")
    data2 = r_get_2.json()["offers"]
    assert all(
        (o["id"] != offer1_id and o["id"] != offer2_id) or o["attached"]
        for o in data2
    )

