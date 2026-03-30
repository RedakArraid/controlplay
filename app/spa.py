"""Service de la SPA React (build Vite → static/spa)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

SPA_ROOT = Path(__file__).resolve().parent / "static" / "spa"
SPA_INDEX = SPA_ROOT / "index.html"


def spa_index_response(*, login_next: str | None = None) -> HTMLResponse:
    """
    Sert index.html avec remplacement du placeholder __CP_NEXT__ (tests / login GET).
    """
    if not SPA_INDEX.is_file():
        raise HTTPException(
            status_code=503,
            detail="Interface web non construite. Exécutez : cd frontend && npm install && npm run build",
        )
    text = SPA_INDEX.read_text(encoding="utf-8")
    next_val = (login_next or "/admin").strip() or "/admin"
    text = text.replace("__CP_NEXT__", escape(next_val, quote=True))
    return HTMLResponse(content=text, media_type="text/html; charset=utf-8")
