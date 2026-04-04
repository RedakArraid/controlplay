from datetime import datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

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
        if session.payment_status != "paid":
            return
        other_active = (
            db.query(GameSession)
            .filter(
                and_(
                    GameSession.station_id == session.station_id,
                    GameSession.id != session.id,
                    GameSession.status.in_(("active", "paused")),
                )
            )
            .first()
        )
        if other_active:
            db.add(
                EventLog(
                    level="warning",
                    message=(
                        f"Activation ignoree pour session {session.id}: "
                        f"station deja active (session {other_active.id})."
                    ),
                    station_id=session.station_id,
                    session_id=session.id,
                )
            )
            db.commit()
            return
        station = session.station
        offer = session.offer
        ir_sent = (
            station.usage_kind == "game_room"
            and station.broadlink_ip
            and station.ir_code_hdmi2
        )
        if ir_sent:
            send_ir_command(station.broadlink_ip, station.ir_code_hdmi2)
        else:
            db.add(
                EventLog(
                    level="warning",
                    message=(
                        f"Session {session.id}: activation sans commande IR "
                        f"(station location ou Broadlink / code HDMI2 manquant)."
                    ),
                    station_id=station.id,
                    session_id=session.id,
                )
            )
        now = datetime.utcnow().replace(microsecond=0)
        session.status = "active"
        session.payment_status = "paid"
        session.started_at = now
        session.end_at = now + timedelta(minutes=offer.duration_minutes)
        db.add(
            EventLog(
                level="info",
                message=f"Session {session.id} activee"
                + (" ; TV sur HDMI2 (IR)." if ir_sent else " (pas d'IR)."),
                station_id=station.id,
                session_id=session.id,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            # Contrainte DB: une autre session occupe déjà la station.
            db.rollback()
            return
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
        now = datetime.utcnow().replace(microsecond=0)
        # Si une extension a été ajoutée, end_at peut être dans le futur.
        # On ne bascule HDMI1 que quand la session est réellement expirée.
        if session.end_at and session.end_at > now:
            remaining_s = max(0, int((session.end_at - now).total_seconds()))
            deactivate_session.apply_async(args=[session.id], countdown=remaining_s)
            return

        station = session.station
        ir_sent = (
            station.usage_kind == "game_room"
            and station.broadlink_ip
            and station.ir_code_hdmi1
        )
        if ir_sent:
            send_ir_command(station.broadlink_ip, station.ir_code_hdmi1)
        else:
            db.add(
                EventLog(
                    level="warning",
                    message=(
                        f"Session {session.id}: fin de session sans commande IR retour HDMI1."
                    ),
                    station_id=station.id,
                    session_id=session.id,
                )
            )
        session.status = "expired"
        db.add(
            EventLog(
                level="info",
                message=f"Session {session.id} terminee"
                + (" ; TV sur HDMI1 (IR)." if ir_sent else " (pas d'IR)."),
                station_id=station.id,
                session_id=session.id,
            )
        )
        db.commit()
    finally:
        db.close()
