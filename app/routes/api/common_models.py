"""Modèles Pydantic partagés par les routes API JSON."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class OfferOut(BaseModel):
    id: int
    name: str
    duration_minutes: int
    price_xof: int
    provider: str
    attached: bool


class SalleOffersOut(BaseModel):
    salle: dict[str, Any]
    offers: list[OfferOut]


class StationOffersOut(BaseModel):
    station: dict[str, Any]
    offers: list[OfferOut]
