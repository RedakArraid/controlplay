"""
Couches UI HTML : thèmes super admin (bleu clair) et admin/public (orange clair + sarcelle/teal).
"""

from __future__ import annotations

import html as html_lib

from fastapi.responses import HTMLResponse

# Thèmes (classes body dans controlplay.css)
THEME_SUPER_ADMIN = "super-admin"
THEME_ADMIN = "admin"
THEME_PUBLIC = "public"
THEME_LOGIN = "login"


_CLIENT_FONTS = """  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Syne:wght@600;700;800&display=swap" rel="stylesheet"/>
"""


def html_shell(
    title: str,
    inner_html: str,
    *,
    theme: str = THEME_ADMIN,
    body_class_extra: str = "",
) -> str:
    """Document HTML complet avec feuille de style partagée."""
    t_esc = html_lib.escape(title)
    extra = f" {body_class_extra}" if body_class_extra else ""
    fonts = _CLIENT_FONTS if theme == THEME_PUBLIC else ""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{t_esc}</title>
{fonts}  <link rel="stylesheet" href="/static/controlplay.css"/>
</head>
<body class="theme-{theme}{extra}">
  <div class="cp-wrap">
    {inner_html}
  </div>
</body>
</html>"""


def html_shell_login(title: str, inner_html: str) -> str:
    """Page connexion : carte centrée, sans cp-wrap."""
    t_esc = html_lib.escape(title)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{t_esc}</title>
  <link rel="stylesheet" href="/static/controlplay.css"/>
</head>
<body class="theme-{THEME_LOGIN}">
  {inner_html}
</body>
</html>"""


def super_admin_nav_html() -> str:
    return (
        "<nav class='cp-nav' aria-label='Super admin'>"
        "<strong>Super admin</strong>"
        "<span class='sep'>·</span>"
        "<a href='/super-admin'>Accueil</a>"
        "<span class='sep'>·</span>"
        "<a href='/super-admin/users'>Utilisateurs globaux</a>"
        "<span class='sep'>·</span>"
        "<a href='/super-admin/providers'>Providers PSP</a>"
        "<span class='sep'>·</span>"
        "<a href='/admin/dashboard'>Dashboard stations</a>"
        "<span class='sep'>·</span>"
        "<a href='/admin'>Admin opérations</a>"
        "<span class='sep'>·</span>"
        "<a href='/logout'>Déconnexion</a>"
        "</nav>"
    )


def admin_nav_html() -> str:
    return (
        "<nav class='cp-nav' aria-label='Administration'>"
        "<strong>Admin</strong>"
        "<span class='sep'>·</span>"
        "<a href='/admin'>Accueil</a>"
        "<span class='sep'>·</span>"
        "<a href='/admin/salles'>Salles</a>"
        "<span class='sep'>·</span>"
        "<a href='/admin/offers'>Offres</a>"
        "<span class='sep'>·</span>"
        "<a href='/admin/stations'>Stations</a>"
        "<span class='sep'>·</span>"
        "<a href='/admin/sessions'>Sessions</a>"
        "<span class='sep'>·</span>"
        "<a href='/admin/dashboard'>Dashboard</a>"
        "<span class='sep'>·</span>"
        "<a href='/logout'>Déconnexion</a>"
        "</nav>"
    )


def page_response(
    inner_html: str,
    *,
    title: str,
    theme: str,
) -> HTMLResponse:
    return HTMLResponse(html_shell(title, inner_html, theme=theme))


def public_page_html(title: str, body_inner: str) -> str:
    return html_shell(title, body_inner, theme=THEME_PUBLIC)


def admin_page_response(inner_html: str, *, title: str = "ControlPlay") -> HTMLResponse:
    return page_response(admin_nav_html() + inner_html, title=title, theme=THEME_ADMIN)
