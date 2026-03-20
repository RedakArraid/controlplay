import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Les modules du projet ne sont pas packagés : on ajoute `app/` au sys.path.
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)

import database as database_module  # noqa: E402
import main as main_module  # noqa: E402
import models as models_module  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    database_module.Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_get_equivalent_offer_station_then_salle(db_session):
    Salle = models_module.Salle
    Station = models_module.Station
    Offer = models_module.Offer
    StationOffer = models_module.StationOffer
    SalleOffer = models_module.SalleOffer

    salle = Salle(code="salle-x", name="Salle X")
    db_session.add(salle)
    db_session.commit()

    st = Station(
        salle_id=salle.id,
        code="station-x",
        name="Station X",
        broadlink_ip="192.168.1.200",
        ir_code_hdmi1="hdmi1",
        ir_code_hdmi2="hdmi2",
        is_active=True,
    )
    db_session.add(st)
    db_session.commit()

    salle_offer = Offer(name="salle_offer", duration_minutes=15, price_xof=100, provider="paystack", station_id=None, is_active=True)
    station_offer = Offer(
        name="station_offer",
        duration_minutes=15,
        price_xof=100,
        provider="paystack",
        station_id=None,
        is_active=True,
    )
    db_session.add_all([salle_offer, station_offer])
    db_session.commit()

    db_session.add(SalleOffer(salle_id=salle.id, offer_id=salle_offer.id, is_active=True))
    db_session.add(StationOffer(station_id=st.id, offer_id=station_offer.id, is_active=True))
    db_session.commit()

    # Doit retourner l'offre station (prioritaire)
    picked = main_module.get_equivalent_offer(db_session, st.id, station_offer, "paystack")
    assert picked is not None
    assert picked.id == station_offer.id


def test_activate_paid_session_idempotent(db_session, monkeypatch):
    GameSession = models_module.GameSession
    Station = models_module.Station
    Offer = models_module.Offer
    User = models_module.User

    called = {"n": 0}

    def fake_delay(_id):
        called["n"] += 1

    monkeypatch.setattr(main_module.activate_session, "delay", fake_delay)

    st = Station(
        salle_id=None,
        code="station-1",
        name="S1",
        broadlink_ip="192.168.1.200",
        ir_code_hdmi1="hdmi1",
        ir_code_hdmi2="hdmi2",
        is_active=True,
    )
    off = Offer(name="o", duration_minutes=15, price_xof=100, provider="paystack", station_id=None, is_active=True)
    db_session.add_all([st, off])
    db_session.commit()

    u = User(
        name="Test User",
        email="test_user@example.com",
        phone=None,
        avatar=None,
        password_hash=main_module.hash_password("test-pass"),
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    sess = GameSession(
        station_id=st.id,
        offer_id=off.id,
        user_id=u.id,
        payment_provider="paystack",
        payment_reference="cp_testref_1",
        payment_status="pending",
        status="pending",
        started_at=None,
        end_at=None,
        customer_email=None,
        customer_phone=None,
    )
    db_session.add(sess)
    db_session.commit()
    db_session.refresh(sess)

    ok1 = main_module.activate_paid_session(db_session, sess, source="test", trusted=True)
    ok2 = main_module.activate_paid_session(db_session, sess, source="test", trusted=True)

    assert ok1 is True
    assert ok2 is False
    assert called["n"] == 1


def test_apply_paid_extension_idempotent(db_session, monkeypatch):
    GameSession = models_module.GameSession
    SessionExtension = models_module.SessionExtension
    Station = models_module.Station
    Offer = models_module.Offer
    User = models_module.User

    called = {"n": 0}

    def fake_apply_async(*_args, **_kwargs):
        called["n"] += 1

    monkeypatch.setattr(main_module.deactivate_session, "apply_async", fake_apply_async)

    st = Station(
        salle_id=None,
        code="station-1",
        name="S1",
        broadlink_ip="192.168.1.200",
        ir_code_hdmi1="hdmi1",
        ir_code_hdmi2="hdmi2",
        is_active=True,
    )
    off = Offer(name="o", duration_minutes=15, price_xof=100, provider="paystack", station_id=None, is_active=True)
    db_session.add_all([st, off])
    db_session.commit()

    u = User(
        name="Test User",
        email="test_user2@example.com",
        phone=None,
        avatar=None,
        password_hash=main_module.hash_password("test-pass"),
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    sess = GameSession(
        station_id=st.id,
        offer_id=off.id,
        user_id=u.id,
        payment_provider="paystack",
        payment_reference="cp_testref_sess",
        payment_status="paid",
        status="active",
        started_at=None,
        end_at=None,
        customer_email=None,
        customer_phone=None,
    )
    db_session.add(sess)
    db_session.commit()
    db_session.refresh(sess)

    ext = SessionExtension(
        session_id=sess.id,
        user_id=u.id,
        extra_minutes=15,
        payment_provider="paystack",
        payment_reference="cp_testref_ext_1",
        payment_status="pending",
        status="pending",
    )
    db_session.add(ext)
    db_session.commit()
    db_session.refresh(ext)

    ok1 = main_module.apply_paid_extension(db_session, ext, source="test", trusted=True)
    ok2 = main_module.apply_paid_extension(db_session, ext, source="test", trusted=True)

    assert ok1 is True
    assert ok2 is False
    assert called["n"] == 1


def test_checkout_guest_allows_no_email_no_phone(db_session, monkeypatch):
    # On force la simulation (pas de provider externe)
    monkeypatch.setattr(main_module, "is_paystack_configured", lambda: False)
    monkeypatch.setattr(main_module, "is_cinetpay_configured", lambda: False)
    monkeypatch.setattr(main_module, "paystack_enabled", lambda: False)

    Station = models_module.Station
    Offer = models_module.Offer
    StationOffer = models_module.StationOffer

    st = Station(
        salle_id=None,
        code="station-1",
        name="S1",
        broadlink_ip="192.168.1.200",
        ir_code_hdmi1="hdmi1",
        ir_code_hdmi2="hdmi2",
        is_active=True,
    )
    off = Offer(name="o", duration_minutes=15, price_xof=100, provider="paystack", station_id=None, is_active=True)
    db_session.add_all([st, off])
    db_session.commit()

    db_session.add(StationOffer(station_id=st.id, offer_id=off.id, is_active=True))
    db_session.commit()

    # Invité : pas de connexion => aucun email / téléphone requis
    resp = main_module.checkout(
        station_code=st.code,
        offer_id=off.id,
        email="",
        phone="",
        connect="0",
        db=db_session,
    )
    assert resp.status_code in (303, 307)

    # Connecté mais téléphone vide => erreur
    with pytest.raises(main_module.HTTPException) as excinfo:
        main_module.checkout(
            station_code=st.code,
            offer_id=off.id,
            email="",
            phone="",
            connect="1",
            db=db_session,
        )
    assert excinfo.value.status_code == 400

