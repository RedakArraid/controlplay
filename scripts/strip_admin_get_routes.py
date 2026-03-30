#!/usr/bin/env python3
"""Supprime les routes GET /admin/* et /super-admin/* (remplacées par la SPA)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"

text = MAIN.read_text(encoding="utf-8")

# Fonctions GET à retirer (nom de fonction Python)
REMOVE_PREFIXES = (
    "@app.get(\"/admin/users\"",
    "@app.get(\"/admin/mes-utilisateurs\"",
    "@app.get(\"/admin/providers\"",
    "@app.get(\"/admin/dashboard\"",
    "@app.get(\"/admin/offers\"",
    "@app.get(\"/admin/offers/{offer_id}/edit\"",
    "@app.get(\"/admin/stations\"",
    "@app.get(\"/admin/stations/{station_id}/edit\"",
    "@app.get(\"/admin/stations/{station_id}/offers\"",
    "@app.get(\"/admin/salles\"",
    "@app.get(\"/admin/salles/{salle_id}/stations\"",
    "@app.get(\"/admin/salles/{salle_id}/users\"",
    "@app.get(\"/admin/salles/{salle_id}/edit\"",
    "@app.get(\"/admin/salles/{salle_id}/offers\"",
    "@app.get(\"/admin/manual-session\"",
    "@app.get(\"/admin/sessions\"",
    "@app.get(\"/super-admin/users\"",
    "@app.get(\"/super-admin/users/{target_user_id}/roles\"",
    "@app.get(\"/super-admin/providers\"",
)


def find_next_decorator_or_def(s: str, start: int) -> int:
    """Prochain @app. ou def au niveau module (approximatif)."""
    m = re.search(r"\n@app\.|\ndef [a-z_]", s[start + 1 :])
    if not m:
        return len(s)
    return start + 1 + m.start()


def remove_block(text: str, needle: str) -> str | None:
    idx = text.find(needle)
    if idx == -1:
        return None
    end = find_next_decorator_or_def(text, idx)
    return text[:idx] + text[end:]


changed = 0
for needle in REMOVE_PREFIXES:
    new = remove_block(text, needle)
    if new is not None:
        text = new
        changed += 1

# Remplacer admin_home par catch-all SPA
old_admin_home = """@app.get("/admin", response_class=HTMLResponse)
def admin_home(
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    uid = int(_)
    super_a = is_global_super_admin(db, uid)
    u = db.query(User).filter(User.id == uid).first()
    label = html_lib.escape(u.email or u.phone or str(uid))
    parts = [
        "<h1>Administration</h1>",
        f"<p>Connecté : <b>{label}</b> — <a href='/logout'>Déconnexion</a></p>",
    ]
    if super_a:
        parts.append(
            "<p class='cp-card' style='margin-top:1rem'>"
            "<span class='cp-pill'>Super administrateur</span> — "
            "<a href='/super-admin'>Espace super admin (plateforme)</a>"
            "</p>"
        )
    parts.append("<ul>")
    if is_session_gerant_only(db, uid):
        items = [
            ("Sessions (pause, durée)", "/admin/sessions"),
            ("Démarrer une session pour un joueur", "/admin/manual-session"),
        ]
    else:
        items = [
            ("Salles", "/admin/salles"),
            ("Offres", "/admin/offers"),
            ("Stations", "/admin/stations"),
            ("Sessions", "/admin/sessions"),
            ("Dashboard stations", "/admin/dashboard"),
        ]
        if can_use_mes_utilisateurs_page(db, uid):
            items.insert(1, ("Mes utilisateurs (comptes créés)", "/admin/mes-utilisateurs"))
    if super_a:
        if not is_session_gerant_only(db, uid):
            items.insert(
                1,
                ("Utilisateurs globaux & rôles", "/super-admin/users"),
            )
        items.append(("Providers PSP", "/super-admin/providers"))
    for title, href in items:
        parts.append(f"<li><a href='{href}'>{html_lib.escape(title)}</a></li>")
    parts.append("</ul>")
    return admin_page_response("".join(parts), title="Administration")
"""

new_admin_spa = """@app.get("/admin")
@app.get("/admin/{path:path}")
def admin_spa(path: str = "", _: str = Depends(require_admin)):
    from spa import spa_index_response

    return spa_index_response()
"""

if old_admin_home not in text:
    raise SystemExit("Bloc admin_home introuvable — main.py a peut-être changé.")
text = text.replace(old_admin_home, new_admin_spa, 1)

# super-admin hub
old_super_hub = """@app.get("/super-admin", response_class=HTMLResponse)
def super_admin_hub(
    _db: Session = Depends(get_db), _: str = Depends(require_super_admin)
):
    body = (
        super_admin_nav_html()
        + "<h1>Espace super administrateur</h1>"
        + "<p>Gestion globale de la plateforme (hors périmètre d’un admin de salle seul).</p>"
        + "<ul>"
        + "<li><a href='/super-admin/users'>Utilisateurs globaux</a> — création de comptes, affichage des rôles, édition (super_admin + rôles par salle)</li>"
        + "<li><a href='/super-admin/providers'>Providers de paiement</a> — Paystack / CinetPay</li>"
        + "<li><a href='/admin/dashboard'>Dashboard des stations</a></li>"
        + "<li><a href='/admin'>Menu administration (opérations)</a></li>"
        + "</ul>"
    )
    return HTMLResponse(
        html_shell("Espace super administrateur", body, theme=THEME_SUPER_ADMIN)
    )
"""

new_super_spa = """@app.get("/super-admin")
@app.get("/super-admin/{path:path}")
def super_admin_spa(path: str = "", _: str = Depends(require_super_admin)):
    from spa import spa_index_response

    return spa_index_response()
"""

if old_super_hub not in text:
    raise SystemExit("Bloc super_admin_hub introuvable.")
text = text.replace(old_super_hub, new_super_spa, 1)

MAIN.write_text(text, encoding="utf-8")
print(f"strip_admin_get: blocs décorateurs supprimés: {changed}, admin+super hub remplacés.")
