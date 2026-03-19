import hashlib
import hmac
import io
import os
from datetime import datetime, timedelta
from uuid import uuid4

import qrcode
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import EventLog, GameSession, Offer, Station
from tasks import activate_session


app = FastAPI(title="ControlPlay")
Base.metadata.create_all(bind=engine)


def log_event(db: Session, message: str, level: str = "info", station_id=None, session_id=None):
    db.add(
        EventLog(
            message=message,
            level=level,
            station_id=station_id,
            session_id=session_id,
        )
    )
    db.commit()


@app.on_event("startup")
def seed_default_data() -> None:
    db = next(get_db())
    try:
        if db.query(Station).count() == 0:
            station = Station(
                code="station-1",
                name="Station 1",
                broadlink_ip=os.getenv("BROADLINK_IP", "192.168.1.250"),
                ir_code_hdmi1=os.getenv("IR_CODE_HDMI1", "hdmi1_code_placeholder"),
                ir_code_hdmi2=os.getenv("IR_CODE_HDMI2", "hdmi2_code_placeholder"),
            )
            db.add(station)
            db.commit()
        if db.query(Offer).count() == 0:
            db.add_all(
                [
                    Offer(name="30 minutes", duration_minutes=30, price_xof=1000, provider="paystack"),
                    Offer(name="60 minutes", duration_minutes=60, price_xof=1800, provider="paystack"),
                ]
            )
            db.commit()
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def home(db: Session = Depends(get_db)):
    stations = db.query(Station).filter(Station.is_active.is_(True)).all()
    html = "<h1>ControlPlay</h1><h2>Stations</h2><ul>"
    for station in stations:
        html += f'<li>{station.name} - <a href="/s/{station.code}">Page client</a> - <a href="/qr/{station.code}.png">QR</a></li>'
    html += "</ul><p><a href='/admin'>Administration</a></p>"
    return HTMLResponse(html)


@app.get("/s/{station_code}", response_class=HTMLResponse)
def station_page(station_code: str, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.code == station_code).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")
    offers = db.query(Offer).filter(Offer.is_active.is_(True)).all()
    items = "".join(
        [
            f"<li>{offer.name} - {offer.price_xof} XOF ({offer.provider})"
            f"<form method='post' action='/checkout' style='display:inline;margin-left:10px'>"
            f"<input type='hidden' name='station_code' value='{station_code}'/>"
            f"<input type='hidden' name='offer_id' value='{offer.id}'/>"
            "<input type='email' name='email' placeholder='email' required/>"
            "<button type='submit'>Payer</button></form></li>"
            for offer in offers
        ]
    )
    return HTMLResponse(
        f"<h1>{station.name}</h1><p>Choisis une offre:</p><ul>{items}</ul>"
        f"<p><a href='/qr/{station_code}.png'>QR de cette station</a></p>"
    )


@app.post("/checkout")
def checkout(
    station_code: str = Form(...),
    offer_id: int = Form(...),
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    station = db.query(Station).filter(Station.code == station_code).first()
    offer = db.query(Offer).filter(Offer.id == offer_id, Offer.is_active.is_(True)).first()
    if not station or not offer:
        raise HTTPException(status_code=404, detail="Station ou offre introuvable")

    reference = f"cp_{uuid4().hex[:18]}"
    session = GameSession(
        station_id=station.id,
        offer_id=offer.id,
        payment_provider=offer.provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    log_event(db, f"Checkout cree {reference} ({offer.provider})", station_id=station.id, session_id=session.id)

    # MVP: lien de paiement simule (en attendant cles et integration PSP complete).
    fake_url = f"/simulate/pay/{reference}?status=success&email={email}"
    return RedirectResponse(url=fake_url, status_code=303)


@app.get("/simulate/pay/{reference}", response_class=HTMLResponse)
def simulate_payment(reference: str, status: str, email: str = "", db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")
    if status != "success":
        session.payment_status = "failed"
        session.status = "failed"
        db.commit()
        return HTMLResponse("<h1>Paiement echoue</h1>")

    session.payment_status = "paid"
    db.commit()
    activate_session.delay(session.id)
    return HTMLResponse(
        f"<h1>Paiement valide</h1><p>Reference: {reference}</p>"
        "<p>La TV devrait basculer sur HDMI2.</p>"
        "<p><a href='/'>Retour accueil</a></p>"
    )


@app.post("/webhooks/paystack")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    secret = os.getenv("PAYSTACK_WEBHOOK_SECRET", "")
    if secret:
        expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
        if signature != expected:
            raise HTTPException(status_code=401, detail="Signature invalide")
    data = await request.json()
    reference = data.get("data", {}).get("reference")
    if not reference:
        return {"ok": True}
    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    if session and session.status == "pending":
        session.payment_status = "paid"
        db.commit()
        activate_session.delay(session.id)
    return {"ok": True}


@app.post("/webhooks/cinetpay")
async def cinetpay_webhook(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    reference = form.get("cpm_trans_id")
    if not reference:
        return {"ok": True}
    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    if session and session.status == "pending":
        session.payment_status = "paid"
        db.commit()
        activate_session.delay(session.id)
    return {"ok": True}


@app.get("/qr/{station_code}.png")
def station_qr(station_code: str):
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    url = f"{base_url}/s/{station_code}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/admin", response_class=HTMLResponse)
def admin_home():
    return HTMLResponse(
        "<h1>Admin</h1>"
        "<ul>"
        "<li><a href='/admin/offers'>Offres</a></li>"
        "<li><a href='/admin/stations'>Stations</a></li>"
        "<li><a href='/admin/sessions'>Sessions</a></li>"
        "</ul>"
    )


@app.get("/admin/offers", response_class=HTMLResponse)
def admin_offers(db: Session = Depends(get_db)):
    offers = db.query(Offer).order_by(Offer.id.desc()).all()
    rows = "".join(
        [
            f"<tr><td>{o.id}</td><td>{o.name}</td><td>{o.duration_minutes}</td><td>{o.price_xof}</td><td>{o.provider}</td><td>{o.is_active}</td></tr>"
            for o in offers
        ]
    )
    return HTMLResponse(
        "<h1>Admin Offres</h1>"
        "<form method='post' action='/admin/offers'>"
        "<input name='name' placeholder='Nom offre' required/>"
        "<input name='duration_minutes' type='number' placeholder='Duree minutes' required/>"
        "<input name='price_xof' type='number' placeholder='Prix XOF' required/>"
        "<select name='provider'><option value='paystack'>paystack</option><option value='cinetpay'>cinetpay</option></select>"
        "<button type='submit'>Creer offre</button></form>"
        "<table border='1'><tr><th>ID</th><th>Nom</th><th>Duree</th><th>Prix</th><th>Provider</th><th>Active</th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>"
    )


@app.post("/admin/offers")
def create_offer(
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    provider: str = Form(...),
    db: Session = Depends(get_db),
):
    if provider not in ("paystack", "cinetpay"):
        raise HTTPException(status_code=400, detail="Provider invalide")
    offer = Offer(
        name=name,
        duration_minutes=duration_minutes,
        price_xof=price_xof,
        provider=provider,
        is_active=True,
    )
    db.add(offer)
    db.commit()
    return RedirectResponse(url="/admin/offers", status_code=303)


@app.get("/admin/stations", response_class=HTMLResponse)
def admin_stations(db: Session = Depends(get_db)):
    stations = db.query(Station).order_by(Station.id.desc()).all()
    rows = "".join(
        [
            f"<tr><td>{s.id}</td><td>{s.code}</td><td>{s.name}</td><td>{s.broadlink_ip}</td></tr>"
            for s in stations
        ]
    )
    return HTMLResponse(
        "<h1>Admin Stations</h1>"
        "<form method='post' action='/admin/stations'>"
        "<input name='code' placeholder='station-2' required/>"
        "<input name='name' placeholder='Nom station' required/>"
        "<input name='broadlink_ip' placeholder='192.168.1.250' required/>"
        "<input name='ir_code_hdmi1' placeholder='code hdmi1' required/>"
        "<input name='ir_code_hdmi2' placeholder='code hdmi2' required/>"
        "<button type='submit'>Creer station</button></form>"
        "<table border='1'><tr><th>ID</th><th>Code</th><th>Nom</th><th>IP</th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>"
    )


@app.post("/admin/stations")
def create_station(
    code: str = Form(...),
    name: str = Form(...),
    broadlink_ip: str = Form(...),
    ir_code_hdmi1: str = Form(...),
    ir_code_hdmi2: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(Station).filter(Station.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Code station deja utilise")
    station = Station(
        code=code,
        name=name,
        broadlink_ip=broadlink_ip,
        ir_code_hdmi1=ir_code_hdmi1,
        ir_code_hdmi2=ir_code_hdmi2,
        is_active=True,
    )
    db.add(station)
    db.commit()
    return RedirectResponse(url="/admin/stations", status_code=303)


@app.get("/admin/sessions", response_class=HTMLResponse)
def admin_sessions(db: Session = Depends(get_db)):
    sessions = db.query(GameSession).order_by(GameSession.id.desc()).limit(100).all()
    rows = "".join(
        [
            "<tr>"
            f"<td>{s.id}</td>"
            f"<td>{s.payment_reference}</td>"
            f"<td>{s.payment_provider}</td>"
            f"<td>{s.payment_status}</td>"
            f"<td>{s.status}</td>"
            f"<td>{s.started_at}</td>"
            f"<td>{s.end_at}</td>"
            "</tr>"
            for s in sessions
        ]
    )
    return HTMLResponse(
        "<h1>Admin Sessions</h1>"
        "<table border='1'><tr><th>ID</th><th>Reference</th><th>Provider</th><th>Pay</th><th>Status</th><th>Start</th><th>End</th></tr>"
        f"{rows}</table><p><a href='/admin'>Retour</a></p>"
    )


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(), "delta": timedelta(seconds=0).total_seconds()}
