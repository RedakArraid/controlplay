from datetime import datetime, timedelta

from celery_app import celery_app
from broadlink_service import send_ir_command
from database import SessionLocal
from models import EventLog, GameSession


@celery_app.task(name="tasks.activate_session")
def activate_session(session_id: int) -> None:
    db = SessionLocal()
    try:
        session = db.query(GameSession).filter(GameSession.id == session_id).first()
        if not session or session.status == "active":
            return
        station = session.station
        offer = session.offer
        send_ir_command(station.broadlink_ip, station.ir_code_hdmi2)
        now = datetime.utcnow().replace(microsecond=0)
        session.status = "active"
        session.payment_status = "paid"
        session.started_at = now
        session.end_at = now + timedelta(minutes=offer.duration_minutes)
        db.add(
            EventLog(
                level="info",
                message=f"Session {session.id} activee et TV basculee sur HDMI2.",
                station_id=station.id,
                session_id=session.id,
            )
        )
        db.commit()
        deactivate_session.apply_async(args=[session.id], countdown=offer.duration_minutes * 60)
    finally:
        db.close()


@celery_app.task(name="tasks.deactivate_session")
def deactivate_session(session_id: int) -> None:
    db = SessionLocal()
    try:
        session = db.query(GameSession).filter(GameSession.id == session_id).first()
        if not session or session.status != "active":
            return
        station = session.station
        send_ir_command(station.broadlink_ip, station.ir_code_hdmi1)
        session.status = "expired"
        db.add(
            EventLog(
                level="info",
                message=f"Session {session.id} terminee et TV revenue sur HDMI1.",
                station_id=station.id,
                session_id=session.id,
            )
        )
        db.commit()
    finally:
        db.close()
