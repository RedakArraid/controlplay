"""API admin JSON : stations (CRUD de base)."""
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


def test_api_admin_stations_create_then_update(client: TestClient) -> None:
    _login_admin(client)

    salle_code = f"api-station-salle-{uuid.uuid4().hex[:8]}"
    r_salle = client.post(
        "/api/admin/salles",
        json={
            "code": salle_code,
            "name": "Salle API JSON",
            "latitude": 5.1,
            "longitude": -4.2,
        },
    )
    assert r_salle.status_code == 200
    salle_id = r_salle.json()["salle"]["id"]
    assert salle_id > 0

    station_code = f"api-station-{uuid.uuid4().hex[:8]}"
    r_create = client.post(
        "/api/admin/stations",
        json={
            "code": station_code,
            "name": "Station API JSON",
            "broadlink_ip": "192.168.0.123",
            "salle_code": salle_code,
            "is_active": True,
            "ir_code_hdmi1": None,
            "ir_code_hdmi2": None,
        },
    )
    assert r_create.status_code == 200
    created = r_create.json()["station"]
    assert created["code"] == station_code
    assert created["salle_code"] == salle_code
    assert created["is_active"] is True
    assert created.get("usage_kind") == "game_room"

    station_id = created["id"]
    r_update = client.put(
        f"/api/admin/stations/{station_id}",
        json={
            "code": station_code,
            "name": "Station API JSON MAJ",
            "broadlink_ip": "192.168.0.124",
            "salle_code": salle_code,
            "is_active": False,
            "ir_code_hdmi1": None,
            "ir_code_hdmi2": None,
        },
    )
    assert r_update.status_code == 200
    updated = r_update.json()["station"]
    assert updated["name"] == "Station API JSON MAJ"
    assert updated["broadlink_ip"] == "192.168.0.124"
    assert updated["is_active"] is False


def test_api_admin_station_rejects_rental_usage_kind(client: TestClient) -> None:
    """La location se déclare via rental-consoles, pas comme ligne ``stations``."""
    _login_admin(client)

    code = f"rent-st-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/admin/stations",
        json={
            "code": code,
            "name": "Tentative location",
            "usage_kind": "rental",
            "broadlink_ip": "192.168.1.50",
            "salle_code": None,
            "is_active": True,
            "ir_code_hdmi1": None,
            "ir_code_hdmi2": None,
        },
    )
    assert r.status_code == 400, r.text

