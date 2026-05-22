import hashlib
import hmac
import os

from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from tasks import activate_session, deactivate_session
from models import *
from ui_theme import *
from dependencies import *
from payment_utils import *
import html as html_lib
import collections

router = APIRouter()


def _pub(title: str, inner_html: str) -> HTMLResponse:
    return HTMLResponse(public_page_html(title, inner_html))


def _activate_paid_session(db, session, source: str, trusted: bool = False):
    import main as m

    return m.activate_paid_session(db, session, source, trusted=trusted)


def _activate_paid_rental(db, rental, source: str, trusted: bool = False):
    import main as m

    return m.activate_paid_rental(db, rental, source, trusted=trusted)


def _activate_paid_shop(db, order, source: str, trusted: bool = False):
    import main as m

    return m.activate_paid_shop(db, order, source, trusted=trusted)


def _apply_paid_extension(db, extension, source: str, trusted: bool = False):
    import main as m

    return m.apply_paid_extension(db, extension, source, trusted=trusted)


@router.post("/checkout")
def checkout(
    station_code: str = Form(...),
    offer_id: int = Form(...),
    connect: str = Form("0"),
    email: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    station = db.query(Station).filter(Station.code == station_code).first()
    offer = db.query(Offer).filter(Offer.id == offer_id, Offer.is_active.is_(True)).first()
    if not station or not offer:
        raise HTTPException(status_code=404, detail="Station ou offre introuvable")

    if connect == "1":
        if not phone or not phone.strip():
            raise HTTPException(status_code=400, detail="Numéro de téléphone requis (connexion)")
        customer_phone = phone.strip()
        customer_email = (email or "").strip() or None
        user = get_or_create_user_by_phone(db, customer_phone, customer_email)
    else:
        # Mode “invité” : aucun email/phone requis.
        user = get_default_user(db)
        customer_phone = None
        customer_email = None

    station_allowed = (
        db.query(StationOffer)
        .filter(
            StationOffer.station_id == station.id,
            StationOffer.offer_id == offer.id,
            StationOffer.is_active.is_(True),
        )
        .first()
    )
    salle_allowed = None
    if station.salle_id is not None:
        salle_allowed = (
            db.query(SalleOffer)
            .filter(
                SalleOffer.salle_id == station.salle_id,
                SalleOffer.offer_id == offer.id,
                SalleOffer.is_active.is_(True),
            )
            .first()
        )
    if not station_allowed and not salle_allowed:
        raise HTTPException(status_code=400, detail="Offre non disponible pour cette station")
    station_busy = (
        db.query(GameSession)
        .filter(
            GameSession.station_id == station.id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .first()
    )
    if station_busy:
        raise HTTPException(status_code=409, detail="Station deja occupee")

    # Si PSP non configuré (MVP/dev), on conserve la simulation.
    if not (is_paystack_configured() or is_cinetpay_configured()):
        chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
        reference = make_payment_reference(chosen_sim_provider)
        session = GameSession(
            station_id=station.id,
            offer_id=offer.id,
            user_id=user.id,
            payment_provider=chosen_sim_provider,
            payment_reference=reference,
            payment_status="pending",
            status="pending",
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.add(session)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Station deja occupee")
        db.refresh(session)
        log_event(db, f"Checkout (simulation) cree {reference} ({chosen_sim_provider})", station_id=station.id, session_id=session.id)
        email_query = customer_email or ""
        fake_url = f"/simulate/pay/{reference}?status=success&email={email_query}"
        return RedirectResponse(url=fake_url, status_code=303)

    # Mode paiements réels:
    # - Paystack en priorité tant qu'il est activé (admin) et configuré (clés)
    # - Si Paystack échoue ou est désactivé, on bascule sur CinetPay
    if is_paystack_configured():
        paystack_email = get_paystack_email(customer_email, customer_phone)
        reference = make_payment_reference("paystack")
        try:
            authorization_url = init_paystack_payment(
                reference,
                email=paystack_email,
                amount_xof=offer.price_xof,
            )
            session = GameSession(
                station_id=station.id,
                offer_id=offer.id,
                user_id=user.id,
                payment_provider="paystack",
                payment_reference=reference,
                payment_status="pending",
                status="pending",
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
            db.add(session)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(status_code=409, detail="Station deja occupee")
            db.refresh(session)
            log_event(db, f"Checkout Paystack init {reference}", station_id=station.id, session_id=session.id)
            return RedirectResponse(url=authorization_url, status_code=303)
        except Exception as e:
            log_event(
                db,
                f"Paystack init echoue, fallback vers cinetpay: {e}",
                level="warning",
                station_id=station.id,
            )

    # Fallback direct vers CinetPay (init réussie ou Paystack désactivé/indisponible)
    if is_cinetpay_configured():
        reference = make_payment_reference("cinetpay")
        payment_url = init_cinetpay_payment(
            transaction_id=reference,
            amount_xof=offer.price_xof,
            description=offer.name,
        )
        session = GameSession(
            station_id=station.id,
            offer_id=offer.id,
            user_id=user.id,
            payment_provider="cinetpay",
            payment_reference=reference,
            payment_status="pending",
            status="pending",
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.add(session)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Station deja occupee")
        db.refresh(session)
        log_event(db, f"Checkout CinetPay init {reference}", station_id=station.id, session_id=session.id)
        return RedirectResponse(url=payment_url, status_code=303)

    # Si on arrive ici: aucun provider réel utilisable => simulation.
    chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
    reference = make_payment_reference(chosen_sim_provider)
    session = GameSession(
        station_id=station.id,
        offer_id=offer.id,
        user_id=user.id,
        payment_provider=chosen_sim_provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_email=customer_email,
        customer_phone=customer_phone,
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Station deja occupee")
    db.refresh(session)
    log_event(
        db,
        f"Checkout (simulation fallback) cree {reference} ({chosen_sim_provider})",
        station_id=station.id,
        session_id=session.id,
    )
    email_query = customer_email or ""
    fake_url = f"/simulate/pay/{reference}?status=success&email={email_query}"
    return RedirectResponse(url=fake_url, status_code=303)

@router.post("/extend/checkout")
def extend_checkout(
    station_code: str = Form(...),
    offer_id: int = Form(...),
    connect: str = Form("0"),
    email: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    station = db.query(Station).filter(Station.code == station_code).first()
    offer = db.query(Offer).filter(Offer.id == offer_id, Offer.is_active.is_(True)).first()
    if not station or not offer:
        raise HTTPException(status_code=404, detail="Station ou offre introuvable")

    station_allowed = (
        db.query(StationOffer)
        .filter(
            StationOffer.station_id == station.id,
            StationOffer.offer_id == offer.id,
            StationOffer.is_active.is_(True),
        )
        .first()
    )
    salle_allowed = None
    if station.salle_id is not None:
        salle_allowed = (
            db.query(SalleOffer)
            .filter(
                SalleOffer.salle_id == station.salle_id,
                SalleOffer.offer_id == offer.id,
                SalleOffer.is_active.is_(True),
            )
            .first()
        )
    if not station_allowed and not salle_allowed:
        raise HTTPException(status_code=400, detail="Offre non disponible pour cette station")

    active_session = get_active_session_by_station(db, station.id)
    if not active_session:
        raise HTTPException(status_code=409, detail="Aucune session active à prolonger")

    if connect == "1":
        if not phone or not phone.strip():
            raise HTTPException(status_code=400, detail="Numéro de téléphone requis (connexion)")
        customer_phone = phone.strip()
        customer_email = (email or "").strip() or None
    else:
        customer_phone = None
        customer_email = None

    reference = make_payment_reference(offer.provider)
    extension = SessionExtension(
        session_id=active_session.id,
        extra_minutes=offer.duration_minutes,
        user_id=active_session.user_id,
        payment_provider=offer.provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_phone=customer_phone,
    )
    db.add(extension)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Station deja occupee")
    db.refresh(extension)

    # Pour l'instant, on ne supporte le paiement d'extension que via Paystack.
    # En prod, si Paystack est configuré mais l'offre n'est pas paystack, on refuse (pas d'extension gratuite).
    if is_paystack_api_configured():
        if extension.payment_provider != "paystack":
            raise HTTPException(status_code=501, detail="Extension paystack uniquement pour l'instant")
        callback = f"{get_base_url()}/payments/return/extension/paystack/{reference}"
        paystack_email = get_paystack_email(customer_email, customer_phone)
        authorization_url = init_paystack_payment(
            reference,
            email=paystack_email,
            amount_xof=offer.price_xof,
            callback_url=callback,
        )
        return RedirectResponse(url=authorization_url, status_code=303)

    # Si Paystack est désactivé/indisponible mais CinetPay est disponible,
    # on refuse pour l'instant car le flux "extension cinetpay" n'existe pas.
    if is_cinetpay_configured():
        raise HTTPException(status_code=501, detail="Extension CinetPay non supportée pour l'instant")

    # MVP/dev: si aucun provider réel n'est disponible, on applique directement.
    applied = _apply_paid_extension(db, extension, "extend_simulate", trusted=True)
    if not applied:
        return _pub(
            "Extension",
            "<h1>Extension refusée</h1><p>La session n'est plus active.</p><p><a href='/'>Retour</a></p>",
        )
    return _pub(
        "Extension",
        f"<h1>Temps ajoute</h1><p>La TV reste sur HDMI2.</p><p><a href='/s/{html_lib.escape(station_code)}'>Retour</a></p>",
    )

@router.get("/simulate/pay/{reference}", response_class=HTMLResponse)
def simulate_payment(reference: str, status: str, email: str = "", db: Session = Depends(get_db)):
    rental_order = db.query(RentalOrder).filter(RentalOrder.payment_reference == reference).first()
    if rental_order:
        if status != "success":
            if rental_order.payment_status != "paid":
                rental_order.payment_status = "failed"
                rental_order.status = "failed"
                db.commit()
            return _pub(
                "Location",
                "<h1>Paiement location refuse</h1>"
                "<p><a href='/rental'>Nouvelle tentative</a></p>"
                "<p><a href='/location/reserver'>Réservation (interface adaptée)</a></p>",
            )
        if rental_order.payment_status == "paid" and rental_order.status == "paid":
            return RedirectResponse(url="/location", status_code=303)
        activated = _activate_paid_rental(db, rental_order, "simulate", trusted=True)
        if not activated:
            db.refresh(rental_order)
            if rental_order.payment_status == "paid":
                return RedirectResponse(url="/location", status_code=303)
            return _pub(
                "Location",
                "<h1>Location non validee</h1>"
                "<p>Impossible de confirmer le paiement.</p>"
                "<p><a href='/rental'>Retour location</a></p>",
            )
        return RedirectResponse(url="/location", status_code=303)

    shop_order = db.query(ShopOrder).filter(ShopOrder.payment_reference == reference).first()
    if shop_order:
        if status != "success":
            if shop_order.payment_status != "paid":
                shop_order.payment_status = "failed"
                shop_order.status = "failed"
                db.commit()
            return _pub(
                "Boutique",
                "<h1>Paiement boutique refuse</h1>"
                "<p><a href='/boutique/commande'>Nouvelle tentative</a></p>"
                "<p><a href='/boutique'>Accueil boutique</a></p>",
            )
        if shop_order.payment_status == "paid" and shop_order.status == "paid":
            return RedirectResponse(url="/boutique?commande=ok", status_code=303)
        activated = _activate_paid_shop(db, shop_order, "simulate", trusted=True)
        if not activated:
            db.refresh(shop_order)
            if shop_order.payment_status == "paid":
                return RedirectResponse(url="/boutique?commande=ok", status_code=303)
            return _pub(
                "Boutique",
                "<h1>Commande non validee</h1>"
                "<p><a href='/boutique/commande'>Retour boutique</a></p>",
            )
        return RedirectResponse(url="/boutique?commande=ok", status_code=303)

    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")
    if status != "success":
        original_offer = session.offer
        session.payment_status = "failed"
        session.status = "failed"
        db.commit()

        # Fallback simulation: paystack d'abord, sinon cinetpay. On ne repasse pas sur paystack automatiquement.
        if session.payment_provider != "paystack":
            return _pub(
                "Paiement",
                "<h1>Paiement echoue</h1><p>Aucun fallback disponible.</p><p><a href='/'>Retour accueil</a></p>",
            )

        new_reference = make_payment_reference("cinetpay")
        new_session = GameSession(
            station_id=session.station_id,
            offer_id=original_offer.id,
            user_id=session.user_id,
            payment_provider="cinetpay",
            payment_reference=new_reference,
            payment_status="pending",
            status="pending",
            customer_email=session.customer_email,
            customer_phone=session.customer_phone,
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        log_event(
            db,
            f"Fallback paiement simulation: {reference} ({session.payment_provider}) -> {new_reference} (cinetpay)",
            level="warning",
            station_id=session.station_id,
            session_id=new_session.id,
        )

        activated = _activate_paid_session(db, new_session, "simulate_fallback", trusted=True)
        if not activated:
            return _pub(
                "Paiement",
                f"<h1>Paiement valide (fallback)</h1><p>Reference initiale: {html_lib.escape(reference)}</p>"
                f"<p>Reference fallback: {html_lib.escape(new_reference)}</p>"
                "<p>Station actuellement occupee: activation differee.</p>"
                "<p><a href='/'>Retour accueil</a></p>",
            )

        station_code = new_session.station.code if new_session.station else None
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Paiement",
            f"<h1>Paiement valide (fallback)</h1><p>Reference initiale: {html_lib.escape(reference)}</p>"
            f"<p>Reference fallback: {html_lib.escape(new_reference)}</p>"
            "<p>La TV devrait basculer sur HDMI2.</p>"
            "<p><a href='/'>Retour accueil</a></p>",
        )

    _activate_paid_session(db, session, "simulate", trusted=True)
    station_code = session.station.code if session.station else None
    if station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)
    return _pub(
        "Paiement",
        f"<h1>Paiement valide</h1><p>Reference: {html_lib.escape(reference)}</p>"
        "<p>La TV devrait basculer sur HDMI2.</p>"
        "<p><a href='/'>Retour accueil</a></p>",
    )

@router.get("/payments/return/paystack/{reference}")
def paystack_return(reference: str, request: Request, db: Session = Depends(get_db)):
    rental = db.query(RentalOrder).filter(RentalOrder.payment_reference == reference).first()
    if rental:
        if rental.payment_status == "paid":
            return RedirectResponse(url="/location", status_code=303)
        if (
            rental.payment_provider == "paystack"
            and is_paystack_api_configured()
            and rental.status == "pending"
            and rental.payment_status != "paid"
        ):
            if verify_paystack_transaction(reference):
                _activate_paid_rental(db, rental, "paystack_return", trusted=False)
                db.refresh(rental)
        if rental.payment_status == "paid":
            return RedirectResponse(url="/location", status_code=303)
        return _pub(
            "Location",
            "<h1>Paiement location en attente</h1>"
            "<p>La confirmation peut arriver par notification (webhook).</p>"
            "<p><a href='/location'>Vitrine location</a></p>",
        )

    shop_ord = db.query(ShopOrder).filter(ShopOrder.payment_reference == reference).first()
    if shop_ord:
        if shop_ord.payment_status == "paid":
            return RedirectResponse(url="/boutique?commande=ok", status_code=303)
        if (
            shop_ord.payment_provider == "paystack"
            and is_paystack_api_configured()
            and shop_ord.status == "pending"
            and shop_ord.payment_status != "paid"
        ):
            if verify_paystack_transaction(reference):
                _activate_paid_shop(db, shop_ord, "paystack_return", trusted=False)
                db.refresh(shop_ord)
        if shop_ord.payment_status == "paid":
            return RedirectResponse(url="/boutique?commande=ok", status_code=303)
        return _pub(
            "Boutique",
            "<h1>Paiement boutique en attente</h1>"
            "<p>La confirmation peut arriver par notification (webhook).</p>"
            "<p><a href='/boutique'>Boutique</a></p>",
        )

    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")

    callback_status = (request.query_params.get("status") or request.query_params.get("payment_status") or "").lower()
    station_code = session.station.code if session.station else None

    if session.payment_status == "paid" or session.status == "active":
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Paiement",
            "<h1>Paiement confirme</h1><p>La TV sera activee.</p><p><a href='/'>Retour accueil</a></p>",
        )

    # En général, l'activation réelle arrive via webhook.
    # Mais Paystack “return” peut arriver sans `status=` (ex: seulement `trxref`/`reference`).
    # Donc on tente une vérification + activation côté serveur ici aussi.
    if (
        session.payment_provider == "paystack"
        and is_paystack_api_configured()
        and session.status == "pending"
        and session.payment_status != "paid"
    ):
        if verify_paystack_transaction(reference):
            _activate_paid_session(db, session, "paystack_return", trusted=False)
            db.refresh(session)

    # Si on a réussi, on renvoie sur la page de la station.
    if (session.payment_status == "paid" or session.status == "active") and station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)

    # Sinon, on redirige quand même sur la station (pour que l'utilisateur puisse
    # voir la session et attendre l'activation via webhook/worker).
    if station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)

    return _pub(
        "Paiement",
        "<h1>Paiement en attente</h1><p>Merci de patienter.</p><p><a href='/'>Retour accueil</a></p>",
    )

@router.get("/payments/return/extension/paystack/{reference}", response_class=HTMLResponse)
def paystack_extension_return(reference: str, request: Request, db: Session = Depends(get_db)):
    extension = db.query(SessionExtension).filter(SessionExtension.payment_reference == reference).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Reference introuvable")

    station_code = None
    if extension.session and extension.session.station:
        station_code = extension.session.station.code

    if extension.status == "applied" or extension.payment_status == "paid":
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Extension",
            "<h1>Extension confirmée</h1><p>Temps ajouté.</p><p><a href='/'>Retour accueil</a></p>",
        )

    if not is_paystack_api_configured():
        return _pub(
            "Extension",
            "<h1>Extension en attente</h1><p>Paystack non configuré.</p><p><a href='/'>Retour accueil</a></p>",
        )

    if verify_paystack_transaction(reference):
        _apply_paid_extension(db, extension, "paystack_extension_return", trusted=True)
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Extension",
            "<h1>Extension confirmée</h1><p>Temps ajouté.</p><p><a href='/'>Retour accueil</a></p>",
        )

    extension.payment_status = "failed"
    extension.status = "failed"
    db.commit()
    return _pub(
        "Extension",
        "<h1>Extension refusée</h1><p>Paiement Paystack non confirmé.</p><p><a href='/'>Retour accueil</a></p>",
    )

@router.api_route("/payments/return/cinetpay", methods=["GET", "POST"])
async def cinetpay_return(request: Request, db: Session = Depends(get_db)):
    transaction_id = request.query_params.get("transaction_id")
    if not transaction_id and request.method in ("POST",):
        form = await request.form()
        transaction_id = form.get("transaction_id")

    if not transaction_id:
        raise HTTPException(status_code=404, detail="transaction_id introuvable")

    rental = db.query(RentalOrder).filter(RentalOrder.payment_reference == transaction_id).first()
    if rental:
        if rental.payment_status == "paid":
            return RedirectResponse(url="/location", status_code=303)
        return _pub(
            "Location",
            "<h1>Paiement location en attente</h1>"
            "<p>Merci de patienter (validation via webhook CinetPay).</p>"
            "<p><a href='/location'>Vitrine location</a></p>",
        )

    shop_o = db.query(ShopOrder).filter(ShopOrder.payment_reference == transaction_id).first()
    if shop_o:
        if shop_o.payment_status == "paid":
            return RedirectResponse(url="/boutique?commande=ok", status_code=303)
        return _pub(
            "Boutique",
            "<h1>Paiement boutique en attente</h1>"
            "<p>Merci de patienter (validation via webhook CinetPay).</p>"
            "<p><a href='/boutique'>Boutique</a></p>",
        )

    session = db.query(GameSession).filter(GameSession.payment_reference == transaction_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Reference introuvable")

    station_code = session.station.code if session.station else None
    if session.payment_status == "paid" or session.status == "active":
        if station_code:
            return RedirectResponse(url=f"/s/{station_code}", status_code=303)
        return _pub(
            "Paiement",
            "<h1>Paiement confirme</h1><p>La TV sera activee.</p><p><a href='/'>Retour accueil</a></p>",
        )

    if station_code:
        return RedirectResponse(url=f"/s/{station_code}", status_code=303)
    return _pub(
        "Paiement",
        "<h1>Paiement en attente / echoue</h1>"
        "<p>Merci de patienter (validation via webhook).</p>"
        "<p><a href='/'>Retour accueil</a></p>",
    )

@router.post("/webhooks/paystack")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    secret = os.getenv("PAYSTACK_WEBHOOK_SECRET", "")
    if secret:
        expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
        if signature != expected:
            raise HTTPException(status_code=401, detail="Signature invalide")
    data = await request.json()
    event = data.get("event", "")
    reference = data.get("data", {}).get("reference")
    if not reference:
        return {"ok": True}
    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    extension = db.query(SessionExtension).filter(SessionExtension.payment_reference == reference).first()
    rental_w = db.query(RentalOrder).filter(RentalOrder.payment_reference == reference).first()
    shop_w = db.query(ShopOrder).filter(ShopOrder.payment_reference == reference).first()

    # En cas d'événement non-success, on libère la station / commande.
    if event and event != "charge.success":
        if session and session.status == "pending":
            session.payment_status = "failed"
            session.status = "failed"
            db.commit()
            log_event(
                db,
                f"Paystack event {event}: session echouee pour {reference}",
                level="warning",
                station_id=session.station_id,
                session_id=session.id,
            )
        if extension and extension.status == "pending":
            extension.payment_status = "failed"
            extension.status = "failed"
            db.commit()
        if rental_w and rental_w.status == "pending":
            rental_w.payment_status = "failed"
            rental_w.status = "failed"
            db.commit()
            log_event(
                db,
                f"Paystack event {event}: location echouee pour {reference}",
                level="warning",
            )
        if shop_w and shop_w.status == "pending":
            shop_w.payment_status = "failed"
            shop_w.status = "failed"
            db.commit()
            log_event(
                db,
                f"Paystack event {event}: boutique echouee pour {reference}",
                level="warning",
            )
        return {"ok": True}

    if session:
        _activate_paid_session(db, session, "paystack_webhook")
    elif extension:
        _apply_paid_extension(db, extension, "paystack_webhook")
    elif rental_w:
        _activate_paid_rental(db, rental_w, "paystack_webhook", trusted=False)
    elif shop_w:
        _activate_paid_shop(db, shop_w, "paystack_webhook", trusted=False)
    return {"ok": True}

@router.post("/webhooks/cinetpay")
async def cinetpay_webhook(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    received_token = request.headers.get("x-token", "") or request.headers.get("X-Token", "")
    secret_key = os.getenv("CINETPAY_SECRET_KEY", "")

    # Vérification x-token (HMAC SHA256) si la clé secrète est configurée.
    if secret_key and received_token:
        # Concaténation exacte des champs dans l'ordre demandé par la doc CinetPay.
        # Voir: https://docs.cinetpay.com/api/1.0-en/checkout/hmac
        data_str = (
            str(form.get("cpm_site_id", ""))
            + str(form.get("cpm_trans_id", ""))
            + str(form.get("cpm_trans_date", ""))
            + str(form.get("cpm_amount", ""))
            + str(form.get("cpm_currency", ""))
            + str(form.get("signature", ""))
            + str(form.get("payment_method", ""))
            + str(form.get("cel_phone_num", ""))
            + str(form.get("cpm_phone_prefixe", ""))
            + str(form.get("cpm_language", ""))
            + str(form.get("cpm_version", ""))
            + str(form.get("cpm_payment_config", ""))
            + str(form.get("cpm_page_action", ""))
            + str(form.get("cpm_custom", ""))
            + str(form.get("cpm_designation", ""))
            + str(form.get("cpm_error_message", ""))
        )
        generated_token = hmac.new(
            secret_key.encode("utf-8"),
            data_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(received_token, generated_token):
            raise HTTPException(status_code=401, detail="x-token invalide")

    reference = form.get("cpm_trans_id")
    payment_status = (form.get("cpm_result") or form.get("status") or "").lower()
    if not reference:
        return {"ok": True}
    session = db.query(GameSession).filter(GameSession.payment_reference == reference).first()
    rental_order = db.query(RentalOrder).filter(RentalOrder.payment_reference == reference).first()
    shop_order = db.query(ShopOrder).filter(ShopOrder.payment_reference == reference).first()

    if payment_status and payment_status not in ("00", "accepted", "success"):
        if session and session.status == "pending":
            session.payment_status = "failed"
            session.status = "failed"
            db.commit()
            log_event(
                db,
                f"CinetPay status {payment_status}: session echouee pour {reference}",
                level="warning",
                station_id=session.station_id,
                session_id=session.id,
            )
        if rental_order and rental_order.status == "pending":
            rental_order.payment_status = "failed"
            rental_order.status = "failed"
            db.commit()
            log_event(
                db,
                f"CinetPay status {payment_status}: location echouee pour {reference}",
                level="warning",
            )
        if shop_order and shop_order.status == "pending":
            shop_order.payment_status = "failed"
            shop_order.status = "failed"
            db.commit()
            log_event(
                db,
                f"CinetPay status {payment_status}: boutique echouee pour {reference}",
                level="warning",
            )
        return {"ok": True}

    if session:
        _activate_paid_session(db, session, "cinetpay_webhook")
    elif rental_order:
        _activate_paid_rental(db, rental_order, "cinetpay_webhook", trusted=False)
    elif shop_order:
        _activate_paid_shop(db, shop_order, "cinetpay_webhook", trusted=False)
    return {"ok": True}
