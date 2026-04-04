"""API admin JSON : CRUD forfaits location."""
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


def test_api_admin_rental_plans_crud(client: TestClient) -> None:
    _login_admin(client)
    r_st = client.get("/api/admin/rental-consoles")
    assert r_st.status_code == 200
    stations = r_st.json()["consoles"]
    assert stations
    console_id = stations[0]["id"]

    r_create = client.post(
        "/api/admin/rental-plans",
        json={
            "name": f"Pack {uuid.uuid4().hex[:6]}",
            "description": "Test API rental plan",
            "duration_label": "2 heures",
            "price_xof": 8000,
            "provider": "paystack",
            "rental_console_id": console_id,
            "is_active": True,
        },
    )
    assert r_create.status_code == 200
    plan_id = r_create.json()["id"]

    r_list = client.get("/api/admin/rental-plans")
    assert r_list.status_code == 200
    assert any(p["id"] == plan_id for p in r_list.json()["plans"])

    r_up = client.put(
        f"/api/admin/rental-plans/{plan_id}",
        json={
            "name": "Pack Maj",
            "description": "Maj",
            "duration_label": "3 heures",
            "price_xof": 12000,
            "provider": "paystack",
            "rental_console_id": console_id,
            "is_active": True,
        },
    )
    assert r_up.status_code == 200

    r_del = client.post(f"/api/admin/rental-plans/{plan_id}/delete")
    assert r_del.status_code == 200
