"""API feedback public + administration."""
from __future__ import annotations

import os
import sys

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


def test_public_feedback_submit_then_admin_process(client: TestClient) -> None:
    r_st = client.get("/api/public/stations")
    assert r_st.status_code == 200
    stations = r_st.json()["stations"]
    assert stations
    station_code = stations[0]["code"]

    r_fb = client.post(
        "/api/public/feedback",
        json={
            "station_code": station_code,
            "rating": 4,
            "category": "experience",
            "comment": "Très bonne immersion VR",
            "contact_email": "feedback@test.com",
        },
    )
    assert r_fb.status_code == 200
    fb_id = r_fb.json()["feedback_id"]

    _login_admin(client)
    r_list = client.get("/api/admin/feedback", params={"status": "new", "page_size": 50})
    assert r_list.status_code == 200
    payload = r_list.json()
    assert payload["total"] >= 1
    row = next((x for x in payload["items"] if x["id"] == fb_id), None)
    assert row is not None
    assert row["station_code"] == station_code
    assert row["rating"] == 4

    r_set = client.put(f"/api/admin/feedback/{fb_id}/status", json={"status": "resolved"})
    assert r_set.status_code == 200

    r_list2 = client.get("/api/admin/feedback", params={"status": "resolved", "page_size": 50})
    assert r_list2.status_code == 200
    assert any(x["id"] == fb_id for x in r_list2.json()["items"])
