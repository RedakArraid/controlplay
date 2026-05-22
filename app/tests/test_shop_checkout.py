"""Tunnel boutique POST /shop/checkout (simulation, comme location)."""
from __future__ import annotations

import os
import sys
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main as main_module  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import ShopOrder, ShopProduct  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(main_module.app) as c:
        yield c


def test_shop_checkout_simulation_paid_redirects(client: TestClient) -> None:
    db = SessionLocal()
    try:
        prod = (
            db.query(ShopProduct).filter(ShopProduct.is_active.is_(True)).order_by(ShopProduct.id.asc()).first()
        )
        if prod is None:
            prod = ShopProduct(
                name="pytest produit",
                description="test",
                price_xof=1234,
                provider="paystack",
                sort_order=0,
                is_active=True,
            )
            db.add(prod)
            db.commit()
            db.refresh(prod)
        pid = prod.id
    finally:
        db.close()

    r = client.post(
        "/shop/checkout",
        data={
            "shop_product_id": str(pid),
            "connect": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    sim_url = r.headers.get("location") or ""
    assert "/simulate/pay/" in sim_url
    parsed = urlparse(sim_url)
    ref = parsed.path.rstrip("/").split("/")[-1]

    r2 = client.get(sim_url, follow_redirects=False)
    assert r2.status_code == 303
    assert r2.headers.get("location") == "/boutique?commande=ok"

    db = SessionLocal()
    try:
        order = db.query(ShopOrder).filter(ShopOrder.payment_reference == ref).first()
        assert order is not None
        assert order.payment_status == "paid"
        assert order.status == "paid"
    finally:
        db.close()
