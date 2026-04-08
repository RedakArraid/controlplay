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


def _main():
    import main as m

    return m


def _find_or_create_user(*args, **kwargs):
    return _main()._find_or_create_user(*args, **kwargs)


def _batch_user_roles_maps(*args, **kwargs):
    return _main()._batch_user_roles_maps(*args, **kwargs)


def _count_global_super_admins(db):
    return _main()._count_global_super_admins(db)


# LEFTOVERS
@router.post("/admin/users")
def create_user(
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    is_admin: str = Form("0"),
    global_salle_admin: str = Form("0"),
    assign_salle_id: str = Form(""),
    assign_salle_role: str = Form(""),
    redirect_after: str = Form("/admin/users"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    email_v = email.strip() or None
    phone_v = phone.strip() or None

    if not email_v and not phone_v:
        raise HTTPException(status_code=400, detail="Email ou phone requis")
    if not password or not password.strip():
        raise HTTPException(status_code=400, detail="Mot de passe requis")

    assign_sid_raw = (assign_salle_id or "").strip()
    assign_rk = (assign_salle_role or "").strip()
    if (assign_sid_raw and not assign_rk) or (assign_rk and not assign_sid_raw):
        raise HTTPException(
            status_code=400,
            detail="Pour un rôle sur salle, choisissez à la fois la salle et le rôle (ou laissez les deux vides).",
        )
    assign_sid: int | None = None
    if assign_sid_raw:
        if not assign_sid_raw.isdigit():
            raise HTTPException(status_code=400, detail="Identifiant de salle invalide.")
        assign_sid = int(assign_sid_raw)

    user = User(
        name=name.strip(),
        email=email_v,
        phone=phone_v,
        avatar=None,
        password_hash=hash_password(password.strip()),
        is_active=is_active == "1",
    )
    try:
        db.add(user)
        db.flush()

        if is_admin == "1":
            super_role = db.query(Role).filter(Role.key == "super_admin").first()
            if not super_role:
                raise HTTPException(status_code=500, detail="Role super_admin manquant")
            db.add(UserRole(user_id=user.id, role_id=super_role.id))

        if global_salle_admin == "1":
            sar = db.query(Role).filter(Role.key == "salle_admin").first()
            if not sar:
                raise HTTPException(status_code=500, detail="Role salle_admin manquant")
            exists_sa = (
                db.query(UserRole)
                .filter(UserRole.user_id == user.id, UserRole.role_id == sar.id)
                .first()
            )
            if not exists_sa:
                db.add(UserRole(user_id=user.id, role_id=sar.id))

        if assign_sid is not None and assign_rk:
            err = _apply_salle_role_for_user(db, user.id, assign_sid, assign_rk)
            if err:
                db.rollback()
                raise HTTPException(status_code=400, detail=err)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return RedirectResponse(
        url=safe_internal_redirect(redirect_after, "/admin/users"),
        status_code=303,
    )
@router.post("/admin/mes-utilisateurs")
def admin_mes_utilisateurs_post(
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    viewer_id = int(_)
    if not can_use_mes_utilisateurs_page(db, viewer_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    email_v = email.strip() or None
    phone_v = phone.strip() or None
    if not email_v and not phone_v:
        raise HTTPException(status_code=400, detail="Email ou téléphone requis")
    if not password.strip():
        raise HTTPException(status_code=400, detail="Mot de passe requis")
    user = User(
        name=name.strip(),
        email=email_v,
        phone=phone_v,
        avatar=None,
        password_hash=hash_password(password.strip()),
        is_active=is_active == "1",
        created_by_user_id=viewer_id,
    )
    try:
        db.add(user)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Email ou téléphone déjà utilisé : {e}")
    return RedirectResponse(url="/admin/mes-utilisateurs", status_code=303)
@router.post("/admin/mes-utilisateurs/{child_user_id}/update")
def admin_mes_utilisateurs_update(
    child_user_id: int,
    name: str = Form(...),
    password: str = Form(""),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    viewer_id = int(_)
    if not can_use_mes_utilisateurs_page(db, viewer_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    child = db.query(User).filter(User.id == child_user_id).first()
    if not child or child.created_by_user_id != viewer_id:
        raise HTTPException(status_code=403, detail="Compte introuvable ou non créé par vous.")
    child.name = name.strip()
    child.is_active = is_active == "1"
    pwd = password.strip()
    if pwd:
        child.password_hash = hash_password(pwd)
    db.add(child)
    db.commit()
    return RedirectResponse(url="/admin/mes-utilisateurs", status_code=303)
@router.post("/admin/providers")
def update_providers(
    paystack_enabled: str = Form("0"),
    cinetpay_enabled: str = Form("0"),
    redirect_after: str = Form("/admin/providers"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    cfg = db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    if not cfg:
        cfg = PaymentProviderConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    cfg.paystack_enabled = paystack_enabled == "1"
    cfg.cinetpay_enabled = cinetpay_enabled == "1"
    db.commit()
    return RedirectResponse(
        url=safe_internal_redirect(redirect_after, "/admin/providers"),
        status_code=303,
    )
@router.get("/super-admin/users/{target_user_id}/roles")
def super_admin_edit_user_roles_get(
    target_user_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    uid = int(_)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not is_global_super_admin(db, uid):
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            raise HTTPException(status_code=403, detail="Profil réservé au super administrateur")
    return _html_super_admin_user_roles_editor(
        db, u, viewer_is_super=is_global_super_admin(db, uid)
    )
@router.post("/super-admin/users/{target_user_id}/roles/super-admin")
def super_admin_edit_user_roles_super_admin(
    target_user_id: int,
    grant: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if grant not in ("0", "1"):
        return _html_super_admin_user_roles_editor(db, u, error="Paramètre grant invalide.")

    super_role = db.query(Role).filter(Role.key == "super_admin").first()
    if not super_role:
        return _html_super_admin_user_roles_editor(db, u, error="Rôle super_admin introuvable en base.")

    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == super_role.id)
        .first()
    )

    if grant == "1":
        if not existing:
            db.add(UserRole(user_id=target_user_id, role_id=super_role.id))
            db.commit()
    else:
        if existing:
            if _count_global_super_admins(db) <= 1:
                return _html_super_admin_user_roles_editor(
                    db,
                    u,
                    error="Impossible de retirer le dernier super administrateur de la plateforme.",
                )
            db.delete(existing)
            db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/super-admin/users/{target_user_id}/roles/global-salle-admin")
def super_admin_edit_user_roles_global_salle_admin(
    target_user_id: int,
    grant: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if grant not in ("0", "1"):
        return _html_super_admin_user_roles_editor(db, u, error="Paramètre grant invalide.")

    salle_adm_role = db.query(Role).filter(Role.key == "salle_admin").first()
    if not salle_adm_role:
        return _html_super_admin_user_roles_editor(db, u, error="Rôle salle_admin introuvable en base.")

    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == salle_adm_role.id)
        .first()
    )

    if grant == "1":
        if not existing:
            db.add(UserRole(user_id=target_user_id, role_id=salle_adm_role.id))
            db.commit()
    else:
        if existing:
            db.delete(existing)
            db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/super-admin/users/{target_user_id}/roles/global-remove")
def super_admin_edit_user_roles_global_remove(
    target_user_id: int,
    role_key: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    rk = (role_key or "").strip()
    if rk not in _SUPER_ADMIN_REMOVABLE_GLOBAL_ROLE_KEYS:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Ce rôle global ne peut pas être retiré depuis cette action.",
        )
    role = db.query(Role).filter(Role.key == rk).first()
    if not role:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error=f"Rôle « {rk} » introuvable en base.",
        )
    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == role.id)
        .first()
    )
    if not existing:
        return RedirectResponse(
            url=f"/super-admin/users/{target_user_id}/roles",
            status_code=303,
        )
    if rk == "super_admin" and _count_global_super_admins(db) <= 1:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Impossible de retirer le dernier super administrateur de la plateforme.",
        )
    db.delete(existing)
    db.commit()
    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/super-admin/users/{target_user_id}/roles/salle-set")
def super_admin_edit_user_roles_salle_set(
    target_user_id: int,
    salle_id: int = Form(...),
    role_key: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    viewer_uid = int(_)
    v_super = is_global_super_admin(db, viewer_uid)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not v_super:
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            return _html_super_admin_user_roles_editor(
                db,
                u,
                error="Profil réservé au super administrateur.",
                viewer_is_super=False,
            )

    allowed_keys = {rk for rk, _ in _SUPER_ADMIN_EDITABLE_SALLE_ROLES}
    if role_key not in allowed_keys:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Rôle de salle non autorisé.",
            viewer_is_super=v_super,
        )

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        return _html_super_admin_user_roles_editor(
            db, u, error="Salle introuvable.", viewer_is_super=v_super
        )

    role = db.query(Role).filter(Role.key == role_key).first()
    if not role:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error=f"Rôle « {role_key} » introuvable en base.",
            viewer_is_super=v_super,
        )

    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    if role_key == "manager" and mgr_role:
        existing_other = (
            db.query(SalleUser)
            .filter(
                SalleUser.user_id == target_user_id,
                SalleUser.role_id == mgr_role.id,
                SalleUser.salle_id != salle_id,
            )
            .first()
        )
        if existing_other:
            return _html_super_admin_user_roles_editor(
                db,
                u,
                error="Ce compte est déjà gérant d’une autre salle ; un gérant n’est lié qu’à une seule salle.",
                viewer_is_super=v_super,
            )

    su = (
        db.query(SalleUser)
        .filter(SalleUser.user_id == target_user_id, SalleUser.salle_id == salle_id)
        .first()
    )
    if su:
        su.role_id = role.id
    else:
        db.add(SalleUser(salle_id=salle_id, user_id=target_user_id, role_id=role.id))
    # Assignation par le super admin : rendre le compte visible pour les admins de salle (règle created_by).
    tu = db.query(User).filter(User.id == target_user_id).first()
    if tu and tu.created_by_user_id is not None and not is_global_super_admin(
        db, tu.created_by_user_id
    ):
        tu.created_by_user_id = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Impossible d’enregistrer (contrainte base de données).",
            viewer_is_super=v_super,
        )

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/super-admin/users/{target_user_id}/roles/salle-remove")
def super_admin_edit_user_roles_salle_remove(
    target_user_id: int,
    salle_id: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    viewer_uid = int(_)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not is_global_super_admin(db, viewer_uid):
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            raise HTTPException(status_code=403, detail="Profil réservé au super administrateur")

    su = (
        db.query(SalleUser)
        .filter(SalleUser.user_id == target_user_id, SalleUser.salle_id == salle_id)
        .first()
    )
    if su:
        db.delete(su)
        db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/admin/offers")
def create_offer(
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    offer = Offer(
        name=name,
        duration_minutes=duration_minutes,
        price_xof=price_xof,
        provider="paystack",
        station_id=None,
        is_active=True,
    )
    db.add(offer)
    db.commit()
    return RedirectResponse(url="/admin/offers", status_code=303)
@router.post("/admin/offers/{offer_id}/update")
def update_offer(
    offer_id: int,
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    offer.name = name
    offer.duration_minutes = duration_minutes
    offer.price_xof = price_xof
    offer.provider = "paystack"
    offer.station_id = None
    offer.is_active = is_active == "1"
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")
    return RedirectResponse(url="/admin/offers", status_code=303)
@router.post("/admin/offers/{offer_id}/delete")
def delete_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    # Comportement souhaité:
    # - l'offre disparaît immédiatement des stations (liaisons supprimées)
    # - on évite de casser les FK vers game_sessions/session_extensions en faisant
    #   un soft delete (is_active=false) au lieu de supprimer physiquement la ligne.
    db.query(StationOffer).filter(StationOffer.offer_id == offer_id).delete()
    db.query(SalleOffer).filter(SalleOffer.offer_id == offer_id).delete()
    offer.is_active = False
    db.commit()
    return RedirectResponse(url="/admin/offers", status_code=303)
@router.post("/admin/offers/clone-global-to-all")
def clone_global_offers_to_all(
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    target_stations = db.query(Station).filter(Station.is_active.is_(True)).all()
    if not target_stations:
        return admin_page_response(
            "<h1>Aucune station active</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0
    for st in target_stations:
        for go in global_offers:
            existing = (
                db.query(StationOffer)
                .filter(
                    and_(
                        StationOffer.station_id == st.id,
                        StationOffer.offer_id == go.id,
                    )
                )
                .first()
            )
            if not existing:
                db.add(StationOffer(station_id=st.id, offer_id=go.id, is_active=True))
                created += 1
            elif override and not existing.is_active:
                existing.is_active = True
                updated += 1

    db.commit()
    return admin_page_response(
        "<h1>Dupliquer terminé</h1>"
        f"<p>Rattachements créés (station_offers): {created}</p>"
        f"<p>Rattachements réactivés: {updated}</p>"
        "<p><a href='/admin/offers'>Retour</a></p>",
        title="Offres",
    )
@router.post("/admin/offers/clone-global-to-station/{station_id}")
def clone_global_offers_to_station(
    station_id: int,
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0

    for go in global_offers:
        existing = (
            db.query(StationOffer)
            .filter(and_(StationOffer.station_id == station_id, StationOffer.offer_id == go.id))
            .first()
        )
        if not existing:
            db.add(StationOffer(station_id=station_id, offer_id=go.id, is_active=True))
            created += 1
        elif override and not existing.is_active:
            existing.is_active = True
            updated += 1

    db.commit()
    return RedirectResponse(url=f"/admin/stations/{station_id}/offers", status_code=303)
@router.post("/admin/offers/clone-global-to-salle")
def clone_global_offers_to_salle(
    salle_code: str = Form(...),
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    salle = db.query(Salle).filter(Salle.code == salle_code).first()
    if not salle:
        return admin_page_response(
            "<h1>Salle introuvable</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle.id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0

    # "Global -> salle" = rattacher les templates à la salle via salle_offers.
    # Les stations de cette salle recevront automatiquement les offres (car station_page regarde salle_offers).
    for go in global_offers:
        existing = (
            db.query(SalleOffer)
            .filter(
                and_(
                    SalleOffer.salle_id == salle.id,
                    SalleOffer.offer_id == go.id,
                )
            )
            .first()
        )
        if not existing:
            db.add(SalleOffer(salle_id=salle.id, offer_id=go.id, is_active=True))
            created += 1
        elif override and not existing.is_active:
            existing.is_active = True
            updated += 1

    db.commit()
    return admin_page_response(
        "<h1>Dupliquer terminé</h1>"
        f"<p>Salle: {html_lib.escape(salle_code)}</p>"
        f"<p>Rattachements créés (salle_offers): {created}</p>"
        f"<p>Rattachements réactivés: {updated}</p>"
        "<p><a href='/admin/offers'>Retour</a></p>",
        title="Offres",
    )
@router.post("/admin/stations")
def create_station(
    code: str = Form(...),
    name: str = Form(...),
    broadlink_ip: str = Form(...),
    ir_code_hdmi1: str = Form(...),
    ir_code_hdmi2: str = Form(...),
    salle_code: str = Form(""),
    is_active: str = Form("1"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    existing = db.query(Station).filter(Station.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Code station deja utilise")
    salle_id = None
    if salle_code:
        salle = db.query(Salle).filter(Salle.code == salle_code).first()
        if not salle:
            raise HTTPException(status_code=404, detail="Salle introuvable")
        if not super_admin:
            allowed_salles = get_scoped_salle_ids(db, user_id)
            if not allowed_salles or salle.id not in allowed_salles:
                raise HTTPException(status_code=403, detail="Accès refusé")
        salle_id = salle.id
    else:
        if not super_admin:
            raise HTTPException(status_code=403, detail="Salle requise pour un admin scopé")
    station = Station(
        code=code,
        name=name,
        broadlink_ip=broadlink_ip,
        ir_code_hdmi1=ir_code_hdmi1,
        ir_code_hdmi2=ir_code_hdmi2,
        salle_id=salle_id,
        is_active=is_active == "1",
    )
    db.add(station)
    db.commit()
    return RedirectResponse(url="/admin/stations", status_code=303)
@router.post("/admin/stations/{station_id}/update")
def update_station(
    station_id: int,
    code: str = Form(...),
    name: str = Form(...),
    broadlink_ip: str = Form(...),
    ir_code_hdmi1: str = Form(...),
    ir_code_hdmi2: str = Form(...),
    salle_code: str = Form(""),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    allowed_salles = None
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        if not salle_code:
            raise HTTPException(status_code=403, detail="Salle requise")

    station.salle_id = None
    if salle_code:
        salle = db.query(Salle).filter(Salle.code == salle_code).first()
        if not salle:
            raise HTTPException(status_code=404, detail="Salle introuvable")
        if not super_admin and salle.id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        station.salle_id = salle.id

    station.code = code
    station.name = name
    station.broadlink_ip = broadlink_ip
    station.ir_code_hdmi1 = ir_code_hdmi1
    station.ir_code_hdmi2 = ir_code_hdmi2
    station.is_active = is_active == "1"

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return RedirectResponse(url="/admin/stations", status_code=303)
@router.post("/admin/stations/{station_id}/reset-sessions")
def reset_station_sessions(
    station_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    active_ids_rows = (
        db.query(GameSession.id)
        .filter(
            GameSession.station_id == station_id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .all()
    )
    active_session_ids = [r[0] for r in active_ids_rows]
    if active_session_ids:
        db.query(EventLog).filter(EventLog.session_id.in_(active_session_ids)).delete(synchronize_session=False)
        db.query(SessionExtension).filter(SessionExtension.session_id.in_(active_session_ids)).delete(synchronize_session=False)
        db.query(GameSession).filter(GameSession.id.in_(active_session_ids)).delete(synchronize_session=False)
        db.commit()

    return RedirectResponse(url="/admin/stations", status_code=303)
@router.post("/admin/stations/{station_id}/delete")
def delete_station(station_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    used = db.query(GameSession).filter(GameSession.station_id == station_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="Station utilisée par des sessions : suppression refusée")

    db.query(StationOffer).filter(StationOffer.station_id == station_id).delete()
    db.delete(station)
    db.commit()
    return RedirectResponse(url="/admin/stations", status_code=303)
@router.post("/admin/salles/{salle_id}/reset-sessions")
def reset_salle_sessions(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    station_ids = [r[0] for r in db.query(Station.id).filter(Station.salle_id == salle_id).all()]
    if not station_ids:
        return RedirectResponse(url=f"/admin/salles/{salle_id}/stations", status_code=303)

    session_ids_rows = (
        db.query(GameSession.id)
        .filter(
            GameSession.station_id.in_(station_ids),
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .all()
    )
    session_ids = [r[0] for r in session_ids_rows]

    if session_ids:
        db.query(EventLog).filter(EventLog.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(SessionExtension).filter(SessionExtension.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(GameSession).filter(GameSession.id.in_(session_ids)).delete(synchronize_session=False)
        db.commit()

    return RedirectResponse(url=f"/admin/salles/{salle_id}/stations", status_code=303)
@router.post("/admin/salles/{salle_id}/users")
def admin_salle_users_post(
    salle_id: int,
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    make_manager: str = Form("0"),
    make_responsable: str = Form("0"),
    make_salle_admin: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin and salle_id not in get_scoped_salle_ids(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    roles_to_assign: list[str] = []
    if make_manager == "1":
        roles_to_assign.append("manager")
    if make_responsable == "1":
        if not super_admin and not is_effective_salle_admin_for_salle(db, user_id, salle_id):
            raise HTTPException(
                status_code=403,
                detail="Seul l’admin de salle ou le super-admin peut nommer un responsable.",
            )
        roles_to_assign.append("responsable")
    if super_admin and make_salle_admin == "1":
        roles_to_assign.append("salle_admin")

    if not roles_to_assign:
        raise HTTPException(status_code=400, detail="Choisissez au moins un rôle")

    role_ids = get_role_ids(db, roles_to_assign)
    missing = [rk for rk in roles_to_assign if rk not in role_ids]
    if missing:
        raise HTTPException(status_code=500, detail=f"Rôles manquants: {missing}")

    user = _find_or_create_user(
        db=db,
        name=name,
        email=email or None,
        phone=phone or None,
        password=password,
        is_active=is_active == "1",
        created_by_user_id=user_id,
    )

    if not super_admin and not _salle_admin_may_use_existing_user_for_assignment(db, user_id, user):
        raise HTTPException(
            status_code=400,
            detail="Ce compte existe déjà et n’a pas été créé par vous. Créez un nouveau compte dans « Mes utilisateurs » "
            "ou utilisez un compte créé par le super administrateur.",
        )

    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    if make_manager == "1" and mgr_role:
        existing_other = (
            db.query(SalleUser)
            .filter(SalleUser.user_id == user.id, SalleUser.role_id == mgr_role.id)
            .filter(SalleUser.salle_id != salle_id)
            .first()
        )
        if existing_other:
            raise HTTPException(
                status_code=400,
                detail="Ce compte est déjà gérant d'une autre salle ; un gérant n'est lié qu'à une seule salle.",
            )

    for rk in roles_to_assign:
        rid = role_ids[rk]
        exists = (
            db.query(SalleUser)
            .filter(SalleUser.salle_id == salle_id)
            .filter(SalleUser.user_id == user.id)
            .filter(SalleUser.role_id == rid)
            .first()
        )
        if not exists:
            db.add(SalleUser(salle_id=salle_id, user_id=user.id, role_id=rid))

    db.commit()
    return RedirectResponse(url=f"/admin/salles/{salle_id}/users", status_code=303)
@router.post("/admin/salles/{salle_id}/delete")
def delete_salle(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        if not is_effective_salle_admin_for_salle(db, user_id, salle_id):
            raise HTTPException(status_code=403, detail="Accès refusé")
    used = db.query(Station).filter(Station.salle_id == salle_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="Salle utilisée par des stations : suppression refusée")

    db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id).delete()
    db.query(SalleUser).filter(SalleUser.salle_id == salle_id).delete(synchronize_session=False)
    db.delete(salle)
    db.commit()
    return RedirectResponse(url="/admin/salles", status_code=303)
@router.post("/admin/manual-session")
def admin_manual_session_post(
    station_offer: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    user_id = int(_)
    parts = station_offer.split(":", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise HTTPException(status_code=400, detail="Choix station/offre invalide")
    station_id, offer_id = int(parts[0]), int(parts[1])

    if not session_station_allowed_for_user(db, user_id, station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    station = db.query(Station).filter(Station.id == station_id).first()
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

    station_busy = (
        db.query(GameSession)
        .filter(
            GameSession.station_id == station.id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .first()
    )
    if station_busy:
        raise HTTPException(status_code=409, detail="Station déjà occupée")

    phone_v = phone.strip() or None
    email_v = email.strip() or None
    if phone_v:
        joueur = get_or_create_user_by_phone(db, phone_v, email_v)
    else:
        joueur = get_default_user(db)

    chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
    reference = make_payment_reference(chosen_sim_provider)
    session = GameSession(
        station_id=station.id,
        offer_id=offer.id,
        user_id=joueur.id,
        payment_provider=chosen_sim_provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_email=email_v,
        customer_phone=phone_v,
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Station déjà occupée")
    db.refresh(session)
    log_event(
        db,
        f"Démarrage manuel session {reference} station={station.code}",
        station_id=station.id,
        session_id=session.id,
    )
    if not activate_paid_session(db, session, source="admin_manual", trusted=True):
        raise HTTPException(status_code=400, detail="Impossible d'activer la session")
    return RedirectResponse(url="/admin/sessions", status_code=303)
@router.post("/admin/sessions/{session_id}/extend")
def admin_extend_session(
    session_id: int,
    minutes: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status not in ("active", "paused"):
        raise HTTPException(
            status_code=400,
            detail="Session non modifiable (active ou en pause uniquement).",
        )

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    base_end = session.end_at if session.end_at and session.end_at > now else now
    new_end = base_end + timedelta(minutes=minutes)
    if new_end < now + timedelta(minutes=1):
        raise HTTPException(
            status_code=400,
            detail="Il doit rester au moins 1 minute avant la fin de session.",
        )

    if session.status == "active":
        extend_session_end_at(db, session, minutes, source="admin")
    else:
        # En pause : pas de tâche Celery en cours ; on met seulement à jour end_at.
        session.end_at = new_end
        db.add(session)
        db.commit()
        log_event(
            db,
            f"Ajustement fin session {session.id} (en pause): {minutes:+d} min (source=admin).",
            level="info",
            station_id=session.station_id,
            session_id=session.id,
        )
    return RedirectResponse(url="/admin/sessions", status_code=303)
@router.post("/admin/sessions/{session_id}/pause")
def admin_pause_session(
    session_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status != "active":
        raise HTTPException(status_code=400, detail="Seule une session active peut être mise en pause.")

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    session.status = "paused"
    db.add(session)
    db.commit()
    log_event(
        db,
        f"Session {session.id} mise en pause (admin).",
        level="info",
        station_id=session.station_id,
        session_id=session.id,
    )
    return RedirectResponse(url="/admin/sessions", status_code=303)
@router.post("/admin/sessions/{session_id}/resume")
def admin_resume_session(
    session_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status != "paused":
        raise HTTPException(status_code=400, detail="Seule une session en pause peut être reprise.")

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    session.status = "active"
    db.add(session)
    db.commit()
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    if session.end_at and session.end_at > now:
        remaining_s = max(0, int((session.end_at - now).total_seconds()))
        deactivate_session.apply_async(args=[session.id], countdown=remaining_s)
    else:
        deactivate_session.apply_async(args=[session.id], countdown=0)
    log_event(
        db,
        f"Session {session.id} reprise (admin), décompte relancé.",
        level="info",
        station_id=session.station_id,
        session_id=session.id,
    )
    return RedirectResponse(url="/admin/sessions", status_code=303)

# LEFTOVERS ASYNC
@router.post("/admin/users")
def create_user(
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    is_admin: str = Form("0"),
    global_salle_admin: str = Form("0"),
    assign_salle_id: str = Form(""),
    assign_salle_role: str = Form(""),
    redirect_after: str = Form("/admin/users"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    email_v = email.strip() or None
    phone_v = phone.strip() or None

    if not email_v and not phone_v:
        raise HTTPException(status_code=400, detail="Email ou phone requis")
    if not password or not password.strip():
        raise HTTPException(status_code=400, detail="Mot de passe requis")

    assign_sid_raw = (assign_salle_id or "").strip()
    assign_rk = (assign_salle_role or "").strip()
    if (assign_sid_raw and not assign_rk) or (assign_rk and not assign_sid_raw):
        raise HTTPException(
            status_code=400,
            detail="Pour un rôle sur salle, choisissez à la fois la salle et le rôle (ou laissez les deux vides).",
        )
    assign_sid: int | None = None
    if assign_sid_raw:
        if not assign_sid_raw.isdigit():
            raise HTTPException(status_code=400, detail="Identifiant de salle invalide.")
        assign_sid = int(assign_sid_raw)

    user = User(
        name=name.strip(),
        email=email_v,
        phone=phone_v,
        avatar=None,
        password_hash=hash_password(password.strip()),
        is_active=is_active == "1",
    )
    try:
        db.add(user)
        db.flush()

        if is_admin == "1":
            super_role = db.query(Role).filter(Role.key == "super_admin").first()
            if not super_role:
                raise HTTPException(status_code=500, detail="Role super_admin manquant")
            db.add(UserRole(user_id=user.id, role_id=super_role.id))

        if global_salle_admin == "1":
            sar = db.query(Role).filter(Role.key == "salle_admin").first()
            if not sar:
                raise HTTPException(status_code=500, detail="Role salle_admin manquant")
            exists_sa = (
                db.query(UserRole)
                .filter(UserRole.user_id == user.id, UserRole.role_id == sar.id)
                .first()
            )
            if not exists_sa:
                db.add(UserRole(user_id=user.id, role_id=sar.id))

        if assign_sid is not None and assign_rk:
            err = _apply_salle_role_for_user(db, user.id, assign_sid, assign_rk)
            if err:
                db.rollback()
                raise HTTPException(status_code=400, detail=err)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return RedirectResponse(
        url=safe_internal_redirect(redirect_after, "/admin/users"),
        status_code=303,
    )
@router.post("/admin/mes-utilisateurs")
def admin_mes_utilisateurs_post(
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    viewer_id = int(_)
    if not can_use_mes_utilisateurs_page(db, viewer_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    email_v = email.strip() or None
    phone_v = phone.strip() or None
    if not email_v and not phone_v:
        raise HTTPException(status_code=400, detail="Email ou téléphone requis")
    if not password.strip():
        raise HTTPException(status_code=400, detail="Mot de passe requis")
    user = User(
        name=name.strip(),
        email=email_v,
        phone=phone_v,
        avatar=None,
        password_hash=hash_password(password.strip()),
        is_active=is_active == "1",
        created_by_user_id=viewer_id,
    )
    try:
        db.add(user)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Email ou téléphone déjà utilisé : {e}")
    return RedirectResponse(url="/admin/mes-utilisateurs", status_code=303)
@router.post("/admin/mes-utilisateurs/{child_user_id}/update")
def admin_mes_utilisateurs_update(
    child_user_id: int,
    name: str = Form(...),
    password: str = Form(""),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    viewer_id = int(_)
    if not can_use_mes_utilisateurs_page(db, viewer_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    child = db.query(User).filter(User.id == child_user_id).first()
    if not child or child.created_by_user_id != viewer_id:
        raise HTTPException(status_code=403, detail="Compte introuvable ou non créé par vous.")
    child.name = name.strip()
    child.is_active = is_active == "1"
    pwd = password.strip()
    if pwd:
        child.password_hash = hash_password(pwd)
    db.add(child)
    db.commit()
    return RedirectResponse(url="/admin/mes-utilisateurs", status_code=303)
@router.post("/admin/providers")
def update_providers(
    paystack_enabled: str = Form("0"),
    cinetpay_enabled: str = Form("0"),
    redirect_after: str = Form("/admin/providers"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    cfg = db.query(PaymentProviderConfig).order_by(PaymentProviderConfig.id.asc()).first()
    if not cfg:
        cfg = PaymentProviderConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    cfg.paystack_enabled = paystack_enabled == "1"
    cfg.cinetpay_enabled = cinetpay_enabled == "1"
    db.commit()
    return RedirectResponse(
        url=safe_internal_redirect(redirect_after, "/admin/providers"),
        status_code=303,
    )
@router.get("/super-admin/users/{target_user_id}/roles")
def super_admin_edit_user_roles_get(
    target_user_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    uid = int(_)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not is_global_super_admin(db, uid):
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            raise HTTPException(status_code=403, detail="Profil réservé au super administrateur")
    return _html_super_admin_user_roles_editor(
        db, u, viewer_is_super=is_global_super_admin(db, uid)
    )
@router.post("/super-admin/users/{target_user_id}/roles/super-admin")
def super_admin_edit_user_roles_super_admin(
    target_user_id: int,
    grant: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if grant not in ("0", "1"):
        return _html_super_admin_user_roles_editor(db, u, error="Paramètre grant invalide.")

    super_role = db.query(Role).filter(Role.key == "super_admin").first()
    if not super_role:
        return _html_super_admin_user_roles_editor(db, u, error="Rôle super_admin introuvable en base.")

    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == super_role.id)
        .first()
    )

    if grant == "1":
        if not existing:
            db.add(UserRole(user_id=target_user_id, role_id=super_role.id))
            db.commit()
    else:
        if existing:
            if _count_global_super_admins(db) <= 1:
                return _html_super_admin_user_roles_editor(
                    db,
                    u,
                    error="Impossible de retirer le dernier super administrateur de la plateforme.",
                )
            db.delete(existing)
            db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/super-admin/users/{target_user_id}/roles/global-salle-admin")
def super_admin_edit_user_roles_global_salle_admin(
    target_user_id: int,
    grant: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if grant not in ("0", "1"):
        return _html_super_admin_user_roles_editor(db, u, error="Paramètre grant invalide.")

    salle_adm_role = db.query(Role).filter(Role.key == "salle_admin").first()
    if not salle_adm_role:
        return _html_super_admin_user_roles_editor(db, u, error="Rôle salle_admin introuvable en base.")

    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == salle_adm_role.id)
        .first()
    )

    if grant == "1":
        if not existing:
            db.add(UserRole(user_id=target_user_id, role_id=salle_adm_role.id))
            db.commit()
    else:
        if existing:
            db.delete(existing)
            db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/super-admin/users/{target_user_id}/roles/global-remove")
def super_admin_edit_user_roles_global_remove(
    target_user_id: int,
    role_key: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    rk = (role_key or "").strip()
    if rk not in _SUPER_ADMIN_REMOVABLE_GLOBAL_ROLE_KEYS:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Ce rôle global ne peut pas être retiré depuis cette action.",
        )
    role = db.query(Role).filter(Role.key == rk).first()
    if not role:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error=f"Rôle « {rk} » introuvable en base.",
        )
    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user_id, UserRole.role_id == role.id)
        .first()
    )
    if not existing:
        return RedirectResponse(
            url=f"/super-admin/users/{target_user_id}/roles",
            status_code=303,
        )
    if rk == "super_admin" and _count_global_super_admins(db) <= 1:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Impossible de retirer le dernier super administrateur de la plateforme.",
        )
    db.delete(existing)
    db.commit()
    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/super-admin/users/{target_user_id}/roles/salle-set")
def super_admin_edit_user_roles_salle_set(
    target_user_id: int,
    salle_id: int = Form(...),
    role_key: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    viewer_uid = int(_)
    v_super = is_global_super_admin(db, viewer_uid)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not v_super:
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            return _html_super_admin_user_roles_editor(
                db,
                u,
                error="Profil réservé au super administrateur.",
                viewer_is_super=False,
            )

    allowed_keys = {rk for rk, _ in _SUPER_ADMIN_EDITABLE_SALLE_ROLES}
    if role_key not in allowed_keys:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Rôle de salle non autorisé.",
            viewer_is_super=v_super,
        )

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        return _html_super_admin_user_roles_editor(
            db, u, error="Salle introuvable.", viewer_is_super=v_super
        )

    role = db.query(Role).filter(Role.key == role_key).first()
    if not role:
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error=f"Rôle « {role_key} » introuvable en base.",
            viewer_is_super=v_super,
        )

    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    if role_key == "manager" and mgr_role:
        existing_other = (
            db.query(SalleUser)
            .filter(
                SalleUser.user_id == target_user_id,
                SalleUser.role_id == mgr_role.id,
                SalleUser.salle_id != salle_id,
            )
            .first()
        )
        if existing_other:
            return _html_super_admin_user_roles_editor(
                db,
                u,
                error="Ce compte est déjà gérant d’une autre salle ; un gérant n’est lié qu’à une seule salle.",
                viewer_is_super=v_super,
            )

    su = (
        db.query(SalleUser)
        .filter(SalleUser.user_id == target_user_id, SalleUser.salle_id == salle_id)
        .first()
    )
    if su:
        su.role_id = role.id
    else:
        db.add(SalleUser(salle_id=salle_id, user_id=target_user_id, role_id=role.id))
    # Assignation par le super admin : rendre le compte visible pour les admins de salle (règle created_by).
    tu = db.query(User).filter(User.id == target_user_id).first()
    if tu and tu.created_by_user_id is not None and not is_global_super_admin(
        db, tu.created_by_user_id
    ):
        tu.created_by_user_id = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _html_super_admin_user_roles_editor(
            db,
            u,
            error="Impossible d’enregistrer (contrainte base de données).",
            viewer_is_super=v_super,
        )

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/super-admin/users/{target_user_id}/roles/salle-remove")
def super_admin_edit_user_roles_salle_remove(
    target_user_id: int,
    salle_id: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_staff_users_or_super),
):
    viewer_uid = int(_)
    u = db.query(User).filter(User.id == target_user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not is_global_super_admin(db, viewer_uid):
        gmap, _ = _batch_user_roles_maps(db, [target_user_id])
        if "super_admin" in gmap.get(target_user_id, []):
            raise HTTPException(status_code=403, detail="Profil réservé au super administrateur")

    su = (
        db.query(SalleUser)
        .filter(SalleUser.user_id == target_user_id, SalleUser.salle_id == salle_id)
        .first()
    )
    if su:
        db.delete(su)
        db.commit()

    return RedirectResponse(
        url=f"/super-admin/users/{target_user_id}/roles",
        status_code=303,
    )
@router.post("/admin/offers")
def create_offer(
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    offer = Offer(
        name=name,
        duration_minutes=duration_minutes,
        price_xof=price_xof,
        provider="paystack",
        station_id=None,
        is_active=True,
    )
    db.add(offer)
    db.commit()
    return RedirectResponse(url="/admin/offers", status_code=303)
@router.post("/admin/offers/{offer_id}/update")
def update_offer(
    offer_id: int,
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price_xof: int = Form(...),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    offer.name = name
    offer.duration_minutes = duration_minutes
    offer.price_xof = price_xof
    offer.provider = "paystack"
    offer.station_id = None
    offer.is_active = is_active == "1"
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")
    return RedirectResponse(url="/admin/offers", status_code=303)
@router.post("/admin/offers/{offer_id}/delete")
def delete_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        if offer_id not in allowed_offer_ids:
            raise HTTPException(status_code=403, detail="Accès refusé")
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    # Comportement souhaité:
    # - l'offre disparaît immédiatement des stations (liaisons supprimées)
    # - on évite de casser les FK vers game_sessions/session_extensions en faisant
    #   un soft delete (is_active=false) au lieu de supprimer physiquement la ligne.
    db.query(StationOffer).filter(StationOffer.offer_id == offer_id).delete()
    db.query(SalleOffer).filter(SalleOffer.offer_id == offer_id).delete()
    offer.is_active = False
    db.commit()
    return RedirectResponse(url="/admin/offers", status_code=303)
@router.post("/admin/offers/clone-global-to-all")
def clone_global_offers_to_all(
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")
    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    target_stations = db.query(Station).filter(Station.is_active.is_(True)).all()
    if not target_stations:
        return admin_page_response(
            "<h1>Aucune station active</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0
    for st in target_stations:
        for go in global_offers:
            existing = (
                db.query(StationOffer)
                .filter(
                    and_(
                        StationOffer.station_id == st.id,
                        StationOffer.offer_id == go.id,
                    )
                )
                .first()
            )
            if not existing:
                db.add(StationOffer(station_id=st.id, offer_id=go.id, is_active=True))
                created += 1
            elif override and not existing.is_active:
                existing.is_active = True
                updated += 1

    db.commit()
    return admin_page_response(
        "<h1>Dupliquer terminé</h1>"
        f"<p>Rattachements créés (station_offers): {created}</p>"
        f"<p>Rattachements réactivés: {updated}</p>"
        "<p><a href='/admin/offers'>Retour</a></p>",
        title="Offres",
    )
@router.post("/admin/offers/clone-global-to-station/{station_id}")
def clone_global_offers_to_station(
    station_id: int,
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0

    for go in global_offers:
        existing = (
            db.query(StationOffer)
            .filter(and_(StationOffer.station_id == station_id, StationOffer.offer_id == go.id))
            .first()
        )
        if not existing:
            db.add(StationOffer(station_id=station_id, offer_id=go.id, is_active=True))
            created += 1
        elif override and not existing.is_active:
            existing.is_active = True
            updated += 1

    db.commit()
    return RedirectResponse(url=f"/admin/stations/{station_id}/offers", status_code=303)
@router.post("/admin/offers/clone-global-to-salle")
def clone_global_offers_to_salle(
    salle_code: str = Form(...),
    override_existing: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    salle = db.query(Salle).filter(Salle.code == salle_code).first()
    if not salle:
        return admin_page_response(
            "<h1>Salle introuvable</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle.id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    global_offers = (
        db.query(Offer)
        .filter(and_(Offer.station_id.is_(None), Offer.provider == "paystack", Offer.is_active.is_(True)))
        .all()
    )
    if not global_offers:
        return admin_page_response(
            "<h1>Aucune offre globale à dupliquer</h1><p><a href='/admin/offers'>Retour</a></p>",
            title="Offres",
        )

    override = override_existing == "1"
    created = 0
    updated = 0

    # "Global -> salle" = rattacher les templates à la salle via salle_offers.
    # Les stations de cette salle recevront automatiquement les offres (car station_page regarde salle_offers).
    for go in global_offers:
        existing = (
            db.query(SalleOffer)
            .filter(
                and_(
                    SalleOffer.salle_id == salle.id,
                    SalleOffer.offer_id == go.id,
                )
            )
            .first()
        )
        if not existing:
            db.add(SalleOffer(salle_id=salle.id, offer_id=go.id, is_active=True))
            created += 1
        elif override and not existing.is_active:
            existing.is_active = True
            updated += 1

    db.commit()
    return admin_page_response(
        "<h1>Dupliquer terminé</h1>"
        f"<p>Salle: {html_lib.escape(salle_code)}</p>"
        f"<p>Rattachements créés (salle_offers): {created}</p>"
        f"<p>Rattachements réactivés: {updated}</p>"
        "<p><a href='/admin/offers'>Retour</a></p>",
        title="Offres",
    )
@router.post("/admin/stations")
def create_station(
    code: str = Form(...),
    name: str = Form(...),
    broadlink_ip: str = Form(...),
    ir_code_hdmi1: str = Form(...),
    ir_code_hdmi2: str = Form(...),
    salle_code: str = Form(""),
    is_active: str = Form("1"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    existing = db.query(Station).filter(Station.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Code station deja utilise")
    salle_id = None
    if salle_code:
        salle = db.query(Salle).filter(Salle.code == salle_code).first()
        if not salle:
            raise HTTPException(status_code=404, detail="Salle introuvable")
        if not super_admin:
            allowed_salles = get_scoped_salle_ids(db, user_id)
            if not allowed_salles or salle.id not in allowed_salles:
                raise HTTPException(status_code=403, detail="Accès refusé")
        salle_id = salle.id
    else:
        if not super_admin:
            raise HTTPException(status_code=403, detail="Salle requise pour un admin scopé")
    station = Station(
        code=code,
        name=name,
        broadlink_ip=broadlink_ip,
        ir_code_hdmi1=ir_code_hdmi1,
        ir_code_hdmi2=ir_code_hdmi2,
        salle_id=salle_id,
        is_active=is_active == "1",
    )
    db.add(station)
    db.commit()
    return RedirectResponse(url="/admin/stations", status_code=303)
@router.post("/admin/stations/{station_id}/update")
def update_station(
    station_id: int,
    code: str = Form(...),
    name: str = Form(...),
    broadlink_ip: str = Form(...),
    ir_code_hdmi1: str = Form(...),
    ir_code_hdmi2: str = Form(...),
    salle_code: str = Form(""),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    allowed_salles = None
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        if not salle_code:
            raise HTTPException(status_code=403, detail="Salle requise")

    station.salle_id = None
    if salle_code:
        salle = db.query(Salle).filter(Salle.code == salle_code).first()
        if not salle:
            raise HTTPException(status_code=404, detail="Salle introuvable")
        if not super_admin and salle.id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        station.salle_id = salle.id

    station.code = code
    station.name = name
    station.broadlink_ip = broadlink_ip
    station.ir_code_hdmi1 = ir_code_hdmi1
    station.ir_code_hdmi2 = ir_code_hdmi2
    station.is_active = is_active == "1"

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")

    return RedirectResponse(url="/admin/stations", status_code=303)
@router.post("/admin/stations/{station_id}/reset-sessions")
def reset_station_sessions(
    station_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    active_ids_rows = (
        db.query(GameSession.id)
        .filter(
            GameSession.station_id == station_id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .all()
    )
    active_session_ids = [r[0] for r in active_ids_rows]
    if active_session_ids:
        db.query(EventLog).filter(EventLog.session_id.in_(active_session_ids)).delete(synchronize_session=False)
        db.query(SessionExtension).filter(SessionExtension.session_id.in_(active_session_ids)).delete(synchronize_session=False)
        db.query(GameSession).filter(GameSession.id.in_(active_session_ids)).delete(synchronize_session=False)
        db.commit()

    return RedirectResponse(url="/admin/stations", status_code=303)
@router.post("/admin/stations/{station_id}/delete")
def delete_station(station_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id is None or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    used = db.query(GameSession).filter(GameSession.station_id == station_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="Station utilisée par des sessions : suppression refusée")

    db.query(StationOffer).filter(StationOffer.station_id == station_id).delete()
    db.delete(station)
    db.commit()
    return RedirectResponse(url="/admin/stations", status_code=303)
@router.post("/admin/stations/{station_id}/offers")
async def admin_station_offers_post(station_id: int, request: Request, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        if station.salle_id is None:
            raise HTTPException(status_code=403, detail="Accès refusé")
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if not allowed_salles or station.salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    form = await request.form()
    raw_ids = form.getlist("offer_ids")
    offer_ids = [int(x) for x in raw_ids if str(x).isdigit()]

    if not super_admin:
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        offer_ids = [oid for oid in offer_ids if oid in allowed_offer_ids]

    # Vérifie que les offres existent et sont actives (sinon on ignore).
    active_ids = {
        o.id
        for o in db.query(Offer).filter(Offer.id.in_(offer_ids), Offer.is_active.is_(True)).all()
    }

    db.query(StationOffer).filter(StationOffer.station_id == station_id).delete()
    for oid in active_ids:
        db.add(StationOffer(station_id=station_id, offer_id=oid, is_active=True))
    db.commit()
    return RedirectResponse(url=f"/admin/stations/{station_id}/offers", status_code=303)
@router.post("/admin/salles/{salle_id}/reset-sessions")
def reset_salle_sessions(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    station_ids = [r[0] for r in db.query(Station.id).filter(Station.salle_id == salle_id).all()]
    if not station_ids:
        return RedirectResponse(url=f"/admin/salles/{salle_id}/stations", status_code=303)

    session_ids_rows = (
        db.query(GameSession.id)
        .filter(
            GameSession.station_id.in_(station_ids),
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .all()
    )
    session_ids = [r[0] for r in session_ids_rows]

    if session_ids:
        db.query(EventLog).filter(EventLog.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(SessionExtension).filter(SessionExtension.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(GameSession).filter(GameSession.id.in_(session_ids)).delete(synchronize_session=False)
        db.commit()

    return RedirectResponse(url=f"/admin/salles/{salle_id}/stations", status_code=303)
@router.post("/admin/salles/{salle_id}/users")
def admin_salle_users_post(
    salle_id: int,
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(...),
    is_active: str = Form("0"),
    make_manager: str = Form("0"),
    make_responsable: str = Form("0"),
    make_salle_admin: str = Form("0"),
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin and salle_id not in get_scoped_salle_ids(db, user_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    roles_to_assign: list[str] = []
    if make_manager == "1":
        roles_to_assign.append("manager")
    if make_responsable == "1":
        if not super_admin and not is_effective_salle_admin_for_salle(db, user_id, salle_id):
            raise HTTPException(
                status_code=403,
                detail="Seul l’admin de salle ou le super-admin peut nommer un responsable.",
            )
        roles_to_assign.append("responsable")
    if super_admin and make_salle_admin == "1":
        roles_to_assign.append("salle_admin")

    if not roles_to_assign:
        raise HTTPException(status_code=400, detail="Choisissez au moins un rôle")

    role_ids = get_role_ids(db, roles_to_assign)
    missing = [rk for rk in roles_to_assign if rk not in role_ids]
    if missing:
        raise HTTPException(status_code=500, detail=f"Rôles manquants: {missing}")

    user = _find_or_create_user(
        db=db,
        name=name,
        email=email or None,
        phone=phone or None,
        password=password,
        is_active=is_active == "1",
        created_by_user_id=user_id,
    )

    if not super_admin and not _salle_admin_may_use_existing_user_for_assignment(db, user_id, user):
        raise HTTPException(
            status_code=400,
            detail="Ce compte existe déjà et n’a pas été créé par vous. Créez un nouveau compte dans « Mes utilisateurs » "
            "ou utilisez un compte créé par le super administrateur.",
        )

    mgr_role = db.query(Role).filter(Role.key == "manager").first()
    if make_manager == "1" and mgr_role:
        existing_other = (
            db.query(SalleUser)
            .filter(SalleUser.user_id == user.id, SalleUser.role_id == mgr_role.id)
            .filter(SalleUser.salle_id != salle_id)
            .first()
        )
        if existing_other:
            raise HTTPException(
                status_code=400,
                detail="Ce compte est déjà gérant d'une autre salle ; un gérant n'est lié qu'à une seule salle.",
            )

    for rk in roles_to_assign:
        rid = role_ids[rk]
        exists = (
            db.query(SalleUser)
            .filter(SalleUser.salle_id == salle_id)
            .filter(SalleUser.user_id == user.id)
            .filter(SalleUser.role_id == rid)
            .first()
        )
        if not exists:
            db.add(SalleUser(salle_id=salle_id, user_id=user.id, role_id=rid))

    db.commit()
    return RedirectResponse(url=f"/admin/salles/{salle_id}/users", status_code=303)
@router.post("/admin/salles")
async def create_salle(
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    form = await request.form()
    code = (form.get("code") or "").strip()
    name = (form.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")

    latitude_raw = (form.get("latitude") or "").strip()
    longitude_raw = (form.get("longitude") or "").strip()
    lat_v = float(latitude_raw) if latitude_raw else None
    lon_v = float(longitude_raw) if longitude_raw else None

    raw_manager_ids = form.getlist("manager_user_ids")
    raw_responsable_ids = form.getlist("responsable_user_ids")
    manager_ids = [int(x) for x in raw_manager_ids if str(x).isdigit()]
    responsable_ids = [int(x) for x in raw_responsable_ids if str(x).isdigit()]

    # Admin de salle : rôle global (user_roles) ou déjà admin d’au moins une salle ;
    # gérants/responsables = uniquement des comptes créés par lui (pool filtré).
    if not super_admin:
        has_cap = is_global_salle_admin(db, user_id) or (
            db.query(SalleUser)
            .join(Role, Role.id == SalleUser.role_id)
            .filter(SalleUser.user_id == user_id)
            .filter(Role.key == "salle_admin")
            .first()
            is not None
        )
        if not has_cap:
            raise HTTPException(status_code=403, detail="Accès refusé")
        pool = _user_ids_created_by_salle_admin(db, user_id)
        manager_ids = [uid for uid in manager_ids if uid in pool]
        responsable_ids = [uid for uid in responsable_ids if uid in pool]

    exists = db.query(Salle).filter(Salle.code == code).first()
    if exists:
        raise HTTPException(status_code=400, detail="Code salle deja utilise")

    manager_role = db.query(Role).filter(Role.key == "manager").first()
    responsable_role = db.query(Role).filter(Role.key == "responsable").first()
    if not manager_role or not responsable_role:
        raise HTTPException(status_code=500, detail="Roles manager/responsable manquants")

    # On filtre au passage pour éviter les clés étrangères invalides.
    valid_user_ids = {
        r[0]
        for r in db.query(User.id)
        .filter(User.id.in_(manager_ids + responsable_ids))
        .all()
    }
    manager_ids = [uid for uid in manager_ids if uid in valid_user_ids]
    responsable_ids = [uid for uid in responsable_ids if uid in valid_user_ids]

    salle = Salle(
        code=code,
        name=name,
        latitude=lat_v,
        longitude=lon_v,
    )
    db.add(salle)
    try:
        db.flush()
        salle_admin_role = db.query(Role).filter(Role.key == "salle_admin").first()
        # Le créateur non-super doit devenir `salle_admin` sur la salle créée.
        if salle_admin_role and not super_admin:
            db.add(SalleUser(salle_id=salle.id, user_id=user_id, role_id=salle_admin_role.id))
        for uid in manager_ids:
            db.add(SalleUser(salle_id=salle.id, user_id=uid, role_id=manager_role.id))
        for uid in responsable_ids:
            db.add(
                SalleUser(salle_id=salle.id, user_id=uid, role_id=responsable_role.id)
            )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")
    return RedirectResponse(url="/admin/salles", status_code=303)
@router.post("/admin/salles/{salle_id}/update")
async def update_salle(
    salle_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_config_admin),
):
    form = await request.form()
    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    code = (form.get("code") or "").strip()
    name = (form.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Code et nom requis")

    latitude_raw = (form.get("latitude") or "").strip()
    longitude_raw = (form.get("longitude") or "").strip()
    lat_v = float(latitude_raw) if latitude_raw else None
    lon_v = float(longitude_raw) if longitude_raw else None

    raw_manager_ids = form.getlist("manager_user_ids")
    raw_responsable_ids = form.getlist("responsable_user_ids")
    manager_ids = [int(x) for x in raw_manager_ids if str(x).isdigit()]
    responsable_ids = [int(x) for x in raw_responsable_ids if str(x).isdigit()]

    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    if not super_admin:
        if not is_effective_salle_admin_for_salle(db, user_id, salle_id):
            raise HTTPException(status_code=403, detail="Accès refusé")
        manager_ids, responsable_ids = _filter_manager_responsable_ids(
            db, user_id, salle_id, manager_ids, responsable_ids, super_admin=False
        )

    salle.code = code
    salle.name = name

    salle.latitude = lat_v
    salle.longitude = lon_v

    manager_role = db.query(Role).filter(Role.key == "manager").first()
    responsable_role = db.query(Role).filter(Role.key == "responsable").first()
    if not manager_role or not responsable_role:
        raise HTTPException(status_code=500, detail="Roles manager/responsable manquants")

    valid_user_ids = {
        r[0]
        for r in db.query(User.id)
        .filter(User.id.in_(manager_ids + responsable_ids))
        .all()
    }
    manager_ids = [uid for uid in manager_ids if uid in valid_user_ids]
    responsable_ids = [uid for uid in responsable_ids if uid in valid_user_ids]

    try:
        role_ids = [manager_role.id, responsable_role.id]
        db.query(SalleUser).filter(SalleUser.salle_id == salle_id, SalleUser.role_id.in_(role_ids)).delete(
            synchronize_session=False
        )
        for uid in manager_ids:
            db.add(SalleUser(salle_id=salle_id, user_id=uid, role_id=manager_role.id))
        for uid in responsable_ids:
            db.add(SalleUser(salle_id=salle_id, user_id=uid, role_id=responsable_role.id))
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erreur intégrité: {e}")
    return RedirectResponse(url="/admin/salles", status_code=303)
@router.post("/admin/salles/{salle_id}/delete")
def delete_salle(salle_id: int, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    if not is_global_super_admin(db, user_id):
        if not is_effective_salle_admin_for_salle(db, user_id, salle_id):
            raise HTTPException(status_code=403, detail="Accès refusé")
    used = db.query(Station).filter(Station.salle_id == salle_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="Salle utilisée par des stations : suppression refusée")

    db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id).delete()
    db.query(SalleUser).filter(SalleUser.salle_id == salle_id).delete(synchronize_session=False)
    db.delete(salle)
    db.commit()
    return RedirectResponse(url="/admin/salles", status_code=303)
@router.post("/admin/salles/{salle_id}/offers")
async def admin_salle_offers_post(salle_id: int, request: Request, db: Session = Depends(get_db), _: str = Depends(require_config_admin)):
    salle = db.query(Salle).filter(Salle.id == salle_id).first()
    if not salle:
        raise HTTPException(status_code=404, detail="Salle introuvable")

    user_id = int(_)
    super_admin = is_global_super_admin(db, user_id)
    if not super_admin:
        allowed_salles = get_scoped_salle_ids(db, user_id)
        if salle_id not in allowed_salles:
            raise HTTPException(status_code=403, detail="Accès refusé")

    form = await request.form()
    raw_ids = form.getlist("offer_ids")
    offer_ids = [int(x) for x in raw_ids if str(x).isdigit()]

    if not super_admin:
        allowed_offer_ids = get_allowed_offer_ids_for_user(db, user_id)
        offer_ids = [oid for oid in offer_ids if oid in allowed_offer_ids]

    active_ids = {
        o.id
        for o in db.query(Offer).filter(Offer.id.in_(offer_ids), Offer.is_active.is_(True)).all()
    }

    db.query(SalleOffer).filter(SalleOffer.salle_id == salle_id).delete()
    for oid in active_ids:
        db.add(SalleOffer(salle_id=salle_id, offer_id=oid, is_active=True))
    db.commit()
    return RedirectResponse(url=f"/admin/salles/{salle_id}/offers", status_code=303)
@router.post("/admin/manual-session")
def admin_manual_session_post(
    station_offer: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    user_id = int(_)
    parts = station_offer.split(":", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise HTTPException(status_code=400, detail="Choix station/offre invalide")
    station_id, offer_id = int(parts[0]), int(parts[1])

    if not session_station_allowed_for_user(db, user_id, station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    station = db.query(Station).filter(Station.id == station_id).first()
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

    station_busy = (
        db.query(GameSession)
        .filter(
            GameSession.station_id == station.id,
            GameSession.status.in_(("pending", "active", "paused")),
        )
        .first()
    )
    if station_busy:
        raise HTTPException(status_code=409, detail="Station déjà occupée")

    phone_v = phone.strip() or None
    email_v = email.strip() or None
    if phone_v:
        joueur = get_or_create_user_by_phone(db, phone_v, email_v)
    else:
        joueur = get_default_user(db)

    chosen_sim_provider = "paystack" if paystack_enabled() else "cinetpay"
    reference = make_payment_reference(chosen_sim_provider)
    session = GameSession(
        station_id=station.id,
        offer_id=offer.id,
        user_id=joueur.id,
        payment_provider=chosen_sim_provider,
        payment_reference=reference,
        payment_status="pending",
        status="pending",
        customer_email=email_v,
        customer_phone=phone_v,
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Station déjà occupée")
    db.refresh(session)
    log_event(
        db,
        f"Démarrage manuel session {reference} station={station.code}",
        station_id=station.id,
        session_id=session.id,
    )
    if not activate_paid_session(db, session, source="admin_manual", trusted=True):
        raise HTTPException(status_code=400, detail="Impossible d'activer la session")
    return RedirectResponse(url="/admin/sessions", status_code=303)
@router.post("/admin/sessions/{session_id}/extend")
def admin_extend_session(
    session_id: int,
    minutes: int = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status not in ("active", "paused"):
        raise HTTPException(
            status_code=400,
            detail="Session non modifiable (active ou en pause uniquement).",
        )

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    base_end = session.end_at if session.end_at and session.end_at > now else now
    new_end = base_end + timedelta(minutes=minutes)
    if new_end < now + timedelta(minutes=1):
        raise HTTPException(
            status_code=400,
            detail="Il doit rester au moins 1 minute avant la fin de session.",
        )

    if session.status == "active":
        extend_session_end_at(db, session, minutes, source="admin")
    else:
        # En pause : pas de tâche Celery en cours ; on met seulement à jour end_at.
        session.end_at = new_end
        db.add(session)
        db.commit()
        log_event(
            db,
            f"Ajustement fin session {session.id} (en pause): {minutes:+d} min (source=admin).",
            level="info",
            station_id=session.station_id,
            session_id=session.id,
        )
    return RedirectResponse(url="/admin/sessions", status_code=303)
@router.post("/admin/sessions/{session_id}/pause")
def admin_pause_session(
    session_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status != "active":
        raise HTTPException(status_code=400, detail="Seule une session active peut être mise en pause.")

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    session.status = "paused"
    db.add(session)
    db.commit()
    log_event(
        db,
        f"Session {session.id} mise en pause (admin).",
        level="info",
        station_id=session.station_id,
        session_id=session.id,
    )
    return RedirectResponse(url="/admin/sessions", status_code=303)
@router.post("/admin/sessions/{session_id}/resume")
def admin_resume_session(
    session_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    session = db.query(GameSession).filter(GameSession.id == session_id).first()
    if not session or session.status != "paused":
        raise HTTPException(status_code=400, detail="Seule une session en pause peut être reprise.")

    user_id = int(_)
    if not session_station_allowed_for_user(db, user_id, session.station_id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    session.status = "active"
    db.add(session)
    db.commit()
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    if session.end_at and session.end_at > now:
        remaining_s = max(0, int((session.end_at - now).total_seconds()))
        deactivate_session.apply_async(args=[session.id], countdown=remaining_s)
    else:
        deactivate_session.apply_async(args=[session.id], countdown=0)
    log_event(
        db,
        f"Session {session.id} reprise (admin), décompte relancé.",
        level="info",
        station_id=session.station_id,
        session_id=session.id,
    )
    return RedirectResponse(url="/admin/sessions", status_code=303)
