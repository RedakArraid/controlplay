"""API publique JSON (/api/public/*)."""
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


def test_public_salles_returns_shape(client: TestClient) -> None:
    r = client.get("/api/public/salles")
    assert r.status_code == 200
    data = r.json()
    assert "salles" in data
    assert isinstance(data["salles"], list)
    for s in data["salles"]:
        assert "id" in s and "code" in s and "name" in s
        assert "latitude" in s and "longitude" in s


def test_public_jeux_returns_shape(client: TestClient) -> None:
    r = client.get("/api/public/jeux")
    assert r.status_code == 200
    data = r.json()
    assert "jeux" in data
    assert isinstance(data["jeux"], list)
    for j in data["jeux"]:
        assert "id" in j
        assert "name" in j
        assert "duration_minutes" in j
        assert "price_xof" in j
        assert "provider" in j
        assert "attached" in j


def test_public_stations_returns_shape(client: TestClient) -> None:
    r = client.get("/api/public/stations")
    assert r.status_code == 200
    data = r.json()
    assert "stations" in data
    assert isinstance(data["stations"], list)
    for s in data["stations"]:
        assert "id" in s and "code" in s and "name" in s
        assert s.get("usage_kind") == "game_room"
        assert "tv_size_inches" in s
        assert "console_model" in s
        assert "vr_headset_model" in s
        assert "games" in s
        assert isinstance(s["games"], list)


def test_public_shop_products_returns_shape(client: TestClient) -> None:
    r = client.get("/api/public/shop-products")
    assert r.status_code == 200
    data = r.json()
    assert "products" in data
    assert isinstance(data["products"], list)


def test_public_rental_catalog_returns_shape(client: TestClient) -> None:
    r = client.get("/api/public/rental-catalog")
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data and "consoles" in data
    assert isinstance(data["plans"], list)
    assert isinstance(data["consoles"], list)

