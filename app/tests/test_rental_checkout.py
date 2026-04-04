"""Tunnel de location (/rental) — distinct du checkout temps de jeu."""
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
from models import RentalConsole, RentalOrder, RentalPlan  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(main_module.app) as c:
        yield c


def test_rental_checkout_simulation_paid_redirects_to_location(client: TestClient) -> None:
    db = SessionLocal()
    try:
        st = (
            db.query(RentalConsole)
            .filter(RentalConsole.is_active.is_(True))
            .order_by(RentalConsole.id.asc())
            .first()
        )
        if st is None:
            st = RentalConsole(
                code="rental-st-1",
                name="Rental Station 1",
                is_active=True,
            )
            db.add(st)
            db.commit()
            db.refresh(st)
        plan = (
            db.query(RentalPlan)
            .filter(RentalPlan.is_active.is_(True))
            .order_by(RentalPlan.id.asc())
            .first()
        )
        assert plan is not None
        console_code = st.code
        rental_plan_id = plan.id
    finally:
        db.close()

    r = client.post(
        "/rental/checkout",
        data={
            "rental_plan_id": str(rental_plan_id),
            "console_code": console_code,
            "connect": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    sim_url = r.headers.get("location") or ""
    assert "/simulate/pay/" in sim_url
    parsed = urlparse(sim_url)
    ref = parsed.path.rstrip("/").split("/")[-1]
    qs = parse_qs(parsed.query)
    assert qs.get("status") == ["success"]

    r2 = client.get(sim_url, follow_redirects=False)
    assert r2.status_code == 303
    assert r2.headers.get("location") == "/location"

    db = SessionLocal()
    try:
        order = db.query(RentalOrder).filter(RentalOrder.payment_reference == ref).first()
        assert order is not None
        assert order.payment_status == "paid"
        assert order.status == "paid"
    finally:
        db.close()


def test_simulate_pay_rental_failure_marks_order_failed(client: TestClient) -> None:
    db = SessionLocal()
    try:
        st = (
            db.query(RentalConsole)
            .filter(RentalConsole.is_active.is_(True))
            .order_by(RentalConsole.id.asc())
            .first()
        )
        if st is None:
            st = RentalConsole(
                code="rental-st-2",
                name="Rental Station 2",
                is_active=True,
            )
            db.add(st)
            db.commit()
            db.refresh(st)
        plan = (
            db.query(RentalPlan)
            .filter(RentalPlan.is_active.is_(True))
            .order_by(RentalPlan.id.asc())
            .first()
        )
        assert plan is not None
        console_code = st.code
        rental_plan_id = plan.id
    finally:
        db.close()

    r = client.post(
        "/rental/checkout",
        data={
            "rental_plan_id": str(rental_plan_id),
            "console_code": console_code,
            "connect": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    sim_ok = r.headers.get("location") or ""
    parsed = urlparse(sim_ok)
    ref = parsed.path.rstrip("/").split("/")[-1]

    fail_url = f"/simulate/pay/{ref}?status=failed"
    r2 = client.get(fail_url)
    assert r2.status_code == 200
    assert "refus" in (r2.text or "").lower()

    db = SessionLocal()
    try:
        order = db.query(RentalOrder).filter(RentalOrder.payment_reference == ref).first()
        assert order is not None
        assert order.payment_status == "failed"
        assert order.status == "failed"
    finally:
        db.close()
