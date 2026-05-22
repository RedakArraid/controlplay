"""
API boutique (produits) — périmètre plateforme (super_admin / délégation operations).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import ShopProduct

router = APIRouter(tags=["api"])


def _lazy():
    import main as m

    return m


class ShopProductUpsertBody(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    price_xof: int = Field(..., ge=0)
    provider: str = "paystack"
    sort_order: int = Field(0)
    is_active: bool = True


@router.get("/admin/shop-products")
def api_admin_shop_products(request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(
            status_code=403,
            detail="La boutique est gérée au niveau plateforme.",
        )
    rows = db.query(ShopProduct).order_by(ShopProduct.sort_order.asc(), ShopProduct.id.asc()).all()
    return {
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price_xof": p.price_xof,
                "provider": p.provider,
                "sort_order": p.sort_order,
                "is_active": p.is_active,
            }
            for p in rows
        ]
    }


@router.post("/admin/shop-products")
def api_admin_create_shop_product(
    request: Request, body: ShopProductUpsertBody, db: Session = Depends(get_db)
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(
            status_code=403,
            detail="La boutique est gérée au niveau plateforme.",
        )
    prod = ShopProduct(
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        price_xof=int(body.price_xof),
        provider=(body.provider or "paystack").strip().lower(),
        sort_order=int(body.sort_order),
        is_active=bool(body.is_active),
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return {"ok": True, "id": prod.id}


@router.put("/admin/shop-products/{product_id}")
def api_admin_update_shop_product(
    product_id: int,
    request: Request,
    body: ShopProductUpsertBody,
    db: Session = Depends(get_db),
):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(
            status_code=403,
            detail="La boutique est gérée au niveau plateforme.",
        )
    prod = db.query(ShopProduct).filter(ShopProduct.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    prod.name = body.name.strip()
    prod.description = (body.description or "").strip() or None
    prod.price_xof = int(body.price_xof)
    prod.provider = (body.provider or "paystack").strip().lower()
    prod.sort_order = int(body.sort_order)
    prod.is_active = bool(body.is_active)
    db.commit()
    return {"ok": True}


@router.post("/admin/shop-products/{product_id}/delete")
def api_admin_delete_shop_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    m = _lazy()
    uid = m.get_authenticated_admin_user_id(request, db)
    if m.is_session_gerant_only(db, uid):
        raise HTTPException(status_code=403, detail="Accès refusé")
    if not m.has_platform_operations_scope(db, uid):
        raise HTTPException(
            status_code=403,
            detail="La boutique est gérée au niveau plateforme.",
        )
    prod = db.query(ShopProduct).filter(ShopProduct.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    prod.is_active = False
    db.commit()
    return {"ok": True}
