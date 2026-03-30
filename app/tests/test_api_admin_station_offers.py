"""API admin JSON : offres rattachées à une station (SPA station d'abord)."""
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


def _find_offer(offers: list[dict], offer_id: int) -> dict:
    return next(o for o in offers if o["id"] == offer_id)


def test_api_admin_station_offers_attach_and_detach(client: TestClient) -> None:
    _login_admin(client)

    salle_code = f"api-station-offers-salle-{uuid.uuid4().hex[:8]}"
    r_salle = client.post(
        "/api/admin/salles",
        json={
            "code": salle_code,
            "name": "Salle Station Offers API",
            "latitude": None,
            "longitude": None,
        },
    )
    assert r_salle.status_code == 200
    salle_id = r_salle.json()["salle"]["id"]
    assert salle_id > 0

    station_code = f"api-station-offers-{uuid.uuid4().hex[:8]}"
    r_station = client.post(
        "/api/admin/stations",
        json={
            "code": station_code,
            "name": "Station Station Offers API",
            "broadlink_ip": "192.168.0.123",
            "salle_code": salle_code,
            "is_active": True,
            "ir_code_hdmi1": None,
            "ir_code_hdmi2": None,
        },
    )
    assert r_station.status_code == 200
    station_id = r_station.json()["station"]["id"]
    assert station_id > 0

    offer_1_name = f"offer1-station-{uuid.uuid4().hex[:6]}"
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

    offer_2_name = f"offer2-station-{uuid.uuid4().hex[:6]}"
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

    r_get_0 = client.get(f"/api/admin/stations/{station_id}/offers")
    assert r_get_0.status_code == 200
    offers0 = r_get_0.json()["offers"]
    assert not _find_offer(offers0, offer1_id)["attached"]
    assert not _find_offer(offers0, offer2_id)["attached"]

    r_put = client.put(
        f"/api/admin/stations/{station_id}/offers",
        json={"offer_ids": [offer1_id]},
    )
    assert r_put.status_code == 200

    r_get_1 = client.get(f"/api/admin/stations/{station_id}/offers")
    offers1 = r_get_1.json()["offers"]
    assert _find_offer(offers1, offer1_id)["attached"] is True
    assert _find_offer(offers1, offer2_id)["attached"] is False

    r_put2 = client.put(
        f"/api/admin/stations/{station_id}/offers",
        json={"offer_ids": [offer1_id, offer2_id]},
    )
    assert r_put2.status_code == 200

    r_get_2 = client.get(f"/api/admin/stations/{station_id}/offers")
    offers2 = r_get_2.json()["offers"]
    assert _find_offer(offers2, offer1_id)["attached"] is True
    assert _find_offer(offers2, offer2_id)["attached"] is True

