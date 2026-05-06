from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Tier = Literal["official", "market"]


class RatePoint(BaseModel):
    ts: datetime
    source: str
    tier: Tier
    base_ccy: str = Field(pattern=r"^[A-Z]{3,5}$")
    quote_ccy: str = Field(pattern=r"^[A-Z]{3,5}$")
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AlertPoint(BaseModel):
    ts: datetime
    rule_id: str
    severity: str
    tier: Tier
    source: str
    base_ccy: str
    quote_ccy: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)

