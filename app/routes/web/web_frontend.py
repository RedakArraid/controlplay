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


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next_url: str = Query("", alias="next"),
):
    if request.session.get("user_id"):
        target = login_next_safe(next_url or "/admin")
        return RedirectResponse(url=target, status_code=303)
    from spa import spa_index_response

    return spa_index_response(login_next=next_url or "/admin")

@router.post("/login")
def login_post(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    next_url: str = Form("/admin", alias="next"),
    db: Session = Depends(get_db),
):
    nxt = login_next_safe(next_url)
    ident = identifier.strip()
    pwd = password or ""
    user = find_user_for_login(db, ident)
    if not user or not verify_password(pwd, user.password_hash):
        # 200 (pas 401/403) : évite la page « HTTP ERROR » vide du navigateur ; le message reste dans le HTML.
        return HTMLResponse(
            html_login_page(nxt, error="Identifiants incorrects. Vérifiez l’email ou le téléphone et le mot de passe."),
            status_code=200,
        )
    if not user_can_access_admin(db, user):
        return HTMLResponse(
            html_login_page(
                nxt,
                error=(
                    "Ce compte n’a pas accès à l’administration. Il faut le rôle super_admin global "
                    "ou le rôle global « admin de salle », ou un rôle sur au moins une salle (salle_admin, responsable ou gérant). "
                    "Un super admin peut vous attribuer un rôle depuis la page utilisateurs de la salle. "
                    "Compte propriétaire : créez-le avec « make ensure-super-admin » (identifiant e-mail par défaut, pas le téléphone)."
                ),
            ),
            status_code=200,
        )
    request.session["user_id"] = user.id
    return RedirectResponse(url=nxt, status_code=303)

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@router.get("/", response_class=HTMLResponse)
def home():
    from spa import spa_index_response

    return spa_index_response()

@router.get("/salle/{salle_code}", response_class=HTMLResponse)
def salle_page(salle_code: str, db: Session = Depends(get_db)):
    salle = db.query(Salle).filter(Salle.code == salle_code).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    stations = (
        db.query(Station)
        .filter(Station.salle_id == salle.id, Station.is_active.is_(True))
        .order_by(Station.id.desc())
        .all()
    )

    rows = "".join(
        [
            "<li>"
            f"<strong>{html_lib.escape(s.name)}</strong> "
            f"<span class='cp-muted'>({html_lib.escape(s.code)})</span><br/>"
            f"<a href='/s/{html_lib.escape(s.code)}'>Ouvrir la page station</a> · "
            f"<a href='/qr/{html_lib.escape(s.code)}.png'>QR</a>"
            "</li>"
            for s in stations
        ]
    )

    body = (
        "<header class='cp-client-topbar'>"
        "<a class='cp-client-logo' href='/'>ControlPlay</a>"
        "</header>"
        "<main class='cp-client-main'>"
        f"<h1>{html_lib.escape(salle.name)}</h1>"
        "<p class='cp-client-lead'>Stations rattachées à ce lieu.</p>"
        f"<ul class='cp-station-list'>{rows}</ul>"
        "<p class='cp-client-links'><a href='/'>Accueil ControlPlay</a></p>"
        "</main>"
    )
    return _pub(f"Salle {salle.name}", body)

@router.get("/s/{station_code}", response_class=HTMLResponse)
def station_page(station_code: str, db: Session = Depends(get_db)):
    # Migration progressive : tunnel station servi par la SPA, tout en gardant
    # les endpoints POST historiques (/checkout, /extend/checkout).
    if os.getenv("PUBLIC_STATION_SPA", "1").strip() == "1":
        from spa import spa_index_response

        return spa_index_response()

    station = db.query(Station).filter(Station.code == station_code).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")
    active_session = get_active_session_by_station(db, station.id)
    station_offers = (
        db.query(Offer)
        .join(StationOffer, StationOffer.offer_id == Offer.id)
        .filter(
            StationOffer.station_id == station.id,
            StationOffer.is_active.is_(True),
            Offer.is_active.is_(True),
        )
        .all()
    )
    salle_offers = []
    if station.salle_id is not None:
        salle_offers = (
            db.query(Offer)
            .join(SalleOffer, SalleOffer.offer_id == Offer.id)
            .filter(
                SalleOffer.salle_id == station.salle_id,
                SalleOffer.is_active.is_(True),
                Offer.is_active.is_(True),
            )
            .all()
        )
    # On affiche au plus 1 offre par (durée, prix).
    # Priorité d'affichage (et dédup) : Paystack si activé, sinon CinétPay.
    if paystack_enabled():
        provider_priority = {"paystack": 0, "cinetpay": 1}
    else:
        provider_priority = {"paystack": 1, "cinetpay": 0}
    offers_by_duration_price = {}
    for offer in [*station_offers, *salle_offers]:
        key = (offer.duration_minutes, offer.price_xof)
        current = offers_by_duration_price.get(key)
        if current is None:
            offers_by_duration_price[key] = offer
            continue
        if provider_priority.get(offer.provider, 99) < provider_priority.get(current.provider, 99):
            offers_by_duration_price[key] = offer

    offers = sorted(offers_by_duration_price.values(), key=lambda o: (o.duration_minutes, o.price_xof))
    esc_station_code = html_lib.escape(station_code)
    offer_cards = []
    for offer in offers:
        on = html_lib.escape(offer.name)
        offer_cards.append(
            "<article class='cp-offer-card'>"
            "<div class='cp-offer-meta'>"
            f"<h2 class='cp-offer-title'>{on}</h2>"
            f"<p class='cp-offer-price'><strong>{offer.price_xof} XOF</strong> · {offer.duration_minutes} min</p>"
            "</div>"
            "<form method='post' action='/checkout' class='cp-offer-form'>"
            f"<input type='hidden' name='station_code' value='{esc_station_code}'/>"
            f"<input type='hidden' name='offer_id' value='{offer.id}'/>"
            "<div class='cp-form-row'>"
            "<label>Email<input type='email' name='email' placeholder='optionnel' autocomplete='email'/></label>"
            "<label class='cp-form-connect'><input type='checkbox' name='connect' value='1'/> "
            "Lier un compte (téléphone requis)</label>"
            "<label>Téléphone<input type='tel' name='phone' placeholder='+225…' autocomplete='tel'/></label>"
            "</div>"
            "<button type='submit'>Payer</button>"
            "</form>"
            "</article>"
        )
    offers_section = (
        "<section class='cp-offers' aria-label='Jeux disponibles'>"
        + "<h2 class='cp-section-title'>Jeux disponibles</h2>"
        + "".join(offer_cards)
        + "</section>"
    )

    extension_section = ""
    if active_session:
        ext_cards = []
        for offer in offers:
            on = html_lib.escape(offer.name)
            ext_cards.append(
                "<article class='cp-offer-card'>"
                "<div class='cp-offer-meta'>"
                f"<h2 class='cp-offer-title'>+ {offer.duration_minutes} min · {on}</h2>"
                f"<p class='cp-offer-price'><strong>{offer.price_xof} XOF</strong></p>"
                "</div>"
                "<form method='post' action='/extend/checkout' class='cp-offer-form'>"
                f"<input type='hidden' name='station_code' value='{esc_station_code}'/>"
                f"<input type='hidden' name='offer_id' value='{offer.id}'/>"
                "<div class='cp-form-row'>"
                "<label>Email<input type='email' name='email' placeholder='optionnel' autocomplete='email'/></label>"
                "<label class='cp-form-connect'><input type='checkbox' name='connect' value='1'/> "
                "Lier un compte (téléphone requis)</label>"
                "<label>Téléphone<input type='tel' name='phone' placeholder='+225…' autocomplete='tel'/></label>"
                "</div>"
                "<button type='submit'>Ajouter du temps</button>"
                "</form>"
                "</article>"
            )
        extension_section = (
            "<section class='cp-offers cp-offers--extend' aria-label='Prolongation'>"
            "<h2 class='cp-section-title'>Session en cours — ajouter du temps</h2>"
            + "".join(ext_cards)
            + "</section>"
        )

    retour_href = "/"
    if station.salle_id is not None:
        salle = db.query(Salle).filter(Salle.id == station.salle_id).first()
        if salle:
            retour_href = f"/salle/{salle.code}"

    composition_items: list[str] = []
    if station.tv_size_inches is not None:
        composition_items.append(f"TV {station.tv_size_inches} pouces")
    if station.console_model:
        composition_items.append(f"Console {html_lib.escape(station.console_model)}")
    if station.vr_headset_model:
        composition_items.append(f"VR {html_lib.escape(station.vr_headset_model)}")

    composition_section = ""
    if composition_items:
        pills = "".join(
            [f"<span class='cp-composition-pill'>{html_lib.escape(x)}</span>" for x in composition_items]
        )
        composition_section = (
            "<section class='cp-station-meta' aria-label='Composition de la station'>"
            "<h2 class='cp-section-title' style='margin-top:0.5rem'>Composition</h2>"
            f"<div class='cp-composition-grid'>{pills}</div>"
            "</section>"
        )

    body = (
        "<header class='cp-client-topbar'>"
        "<a class='cp-client-logo' href='/'>ControlPlay</a>"
        f"<span class='cp-client-badge'>{esc_station_code}</span>"
        "</header>"
        "<main class='cp-client-main'>"
        f"<h1>{html_lib.escape(station.name)}</h1>"
        "<p class='cp-client-lead'>Choisissez un jeu, complétez si besoin, puis payez en ligne.</p>"
        f"{composition_section}"
        f"{offers_section}"
        f"{extension_section}"
        "<p class='cp-client-links'>"
        f"<a href='/qr/{esc_station_code}.png'>QR de la station</a>"
        " · "
        f"<a href='{html_lib.escape(retour_href)}'>Retour</a>"
        "</p>"
        "</main>"
    )
    return _pub(station.name, body)

@router.get("/rental", response_class=HTMLResponse)
def rental_catalog_page(db: Session = Depends(get_db)):
    """Location console : catalogue et checkout (tunnel distinct du temps de jeu `/checkout`)."""
    plans = (
        db.query(RentalPlan)
        .filter(RentalPlan.is_active.is_(True))
        .order_by(RentalPlan.price_xof.asc(), RentalPlan.id.asc())
        .all()
    )
    consoles = (
        db.query(RentalConsole)
        .filter(RentalConsole.is_active.is_(True))
        .order_by(RentalConsole.code.asc())
        .all()
    )
    plan_options = "".join(
        [
            f"<option value='{p.id}'>{html_lib.escape(p.name)} — {p.price_xof} XOF ({html_lib.escape(p.duration_label)})</option>"
            for p in plans
        ]
    )
    console_options = "".join(
        [
            f"<option value='{html_lib.escape(c.code)}'>{html_lib.escape(c.code)} — {html_lib.escape(c.name)}</option>"
            for c in consoles
        ]
    )
    body = (
        "<header class='cp-client-topbar'>"
        "<a class='cp-client-logo' href='/'>ControlPlay</a>"
        "<span class='cp-client-badge'>Location</span>"
        "</header>"
        "<main class='cp-client-main cp-wrap'>"
        "<h1>Location console / matériel</h1>"
        "<p class='cp-client-lead'>Catalogue <strong>location ControlPlay</strong> (indépendant des salles de jeu / QR). "
        "Choisissez un forfait et une console de retrait.</p>"
        "<form method='post' action='/rental/checkout' class='cp-offer-card' style='max-width:520px'>"
        "<div class='cp-form-row' style='flex-direction:column;align-items:stretch'>"
        "<label>Forfait<select name='rental_plan_id' required>" + plan_options + "</select></label>"
        "<label>Console de retrait<select name='console_code' required>" + console_options + "</select></label>"
        "<label>Email<input type='email' name='email' placeholder='optionnel' autocomplete='email'/></label>"
        "<label class='cp-form-connect'><input type='checkbox' name='connect' value='1'/> "
        "Lier un compte (téléphone requis)</label>"
        "<label>Téléphone<input type='tel' name='phone' placeholder='+225…' autocomplete='tel'/></label>"
        "</div>"
        "<button type='submit' class='cp-offer-form' style='margin-top:12px'>Payer la location</button>"
        "</form>"
        "<p class='cp-client-links'><a href='/location'>← Vitrine location</a> · <a href='/'>Accueil</a></p>"
        "</main>"
    )
    return _pub("Location console", body)

@router.post("/rental/checkout")
def rental_checkout(
    rental_plan_id: int = Form(...),
    console_code: str = Form(...),
    connect: str = Form("0"),
    email: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    plan = (
        db.query(RentalPlan)
        .filter(RentalPlan.id == rental_plan_id, RentalPlan.is_active.is_(True))
        .first()
    )
    console = db.query(RentalConsole).filter(RentalConsole.code == console_code.strip()).first()
    if not plan or not console or not console.is_active:
        raise HTTPException(status_code=404, detail="Forfait ou console location introuvable")
    if plan.rental_console_id is not None and plan.rental_console_id != console.id:
        raise HTTPException(status_code=400, detail="Ce forfait n'est pas disponible sur ce point de retrait")

    if connect == "1":
        if not phone or not phone.strip():
            raise HTTPException(status_code=400, detail="Numéro de téléphone requis (connexion)")
        customer_phone = phone.strip()
        customer_email = (email or "").strip() or None
        user = get_or_create_user_by_phone(db, customer_phone, customer_email)
    else:
        user = get_default_user(db)
        customer_phone = None
        customer_email = None

    if not (is_paystack_configured() or is_cinetpay_configured()):
        chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
        reference = make_payment_reference(chosen_sim_provider)
        order = RentalOrder(
            rental_plan_id=plan.id,
            rental_console_id=console.id,
            user_id=user.id,
            payment_provider=chosen_sim_provider,
            payment_reference=reference,
            payment_status="pending",
            status="pending",
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        log_event(
            db,
            f"Location checkout (simulation) {reference} ({chosen_sim_provider})",
        )
        email_query = customer_email or ""
        return RedirectResponse(
            url=f"/simulate/pay/{reference}?status=success&email={email_query}",
            status_code=303,
        )

    if is_paystack_configured():
        paystack_email = get_paystack_email(customer_email, customer_phone)
        reference = make_payment_reference("paystack")
        try:
            authorization_url = init_paystack_payment(
                reference,
                email=paystack_email,
                amount_xof=plan.price_xof,
                callback_url=f"{get_base_url()}/payments/return/paystack/{reference}",
            )
            order = RentalOrder(
                rental_plan_id=plan.id,
                rental_console_id=console.id,
                user_id=user.id,
                payment_provider="paystack",
                payment_reference=reference,
                payment_status="pending",
                status="pending",
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            log_event(db, f"Location Paystack init {reference}")
            return RedirectResponse(url=authorization_url, status_code=303)
        except Exception as e:
            log_event(
                db,
                f"Location Paystack init echoue: {e}",
                level="warning",
            )

    if is_cinetpay_configured():
        reference = make_payment_reference("cinetpay")
        payment_url = init_cinetpay_payment(
            transaction_id=reference,
            amount_xof=plan.price_xof,
            description=plan.name,
        )
        order = RentalOrder(
            rental_plan_id=plan.id,
            rental_console_id=console.id,
            user_id=user.id,
            payment_provider="cinetpay",
            payment_reference=reference,
            payment_status="pending",
            status="pending",
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        log_event(db, f"Location CinetPay init {reference}")
        return RedirectResponse(url=payment_url, status_code=303)

    chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
    reference = make_payment_reference(chosen_sim_provider)
    order = RentalOrder(
        rental_plan_id=plan.id,
        rental_console_id=console.id,
        user_id=user.id,
        payment_provider=chosen_sim_provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_email=customer_email,
        customer_phone=customer_phone,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    email_query = customer_email or ""
    return RedirectResponse(
        url=f"/simulate/pay/{reference}?status=success&email={email_query}",
        status_code=303,
    )

@router.get("/qr/{station_code}.png")
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

@router.get("/admin")
@router.get("/admin/{path:path}")
def admin_spa(path: str = "", _: str = Depends(require_admin)):
    from spa import spa_index_response

    return spa_index_response()

@router.get("/super-admin")
@router.get("/super-admin/{path:path}")
def super_admin_spa(path: str = "", _: str = Depends(require_super_zone_or_staff)):
    from spa import spa_index_response

    return spa_index_response()

@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), "delta": timedelta(seconds=0).total_seconds()}
