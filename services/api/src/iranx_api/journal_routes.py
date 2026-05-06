from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .deps import current_user_id

router = APIRouter(prefix="/api/journal", tags=["journal"])


def _conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


class ExchangeIn(BaseModel):
    occurred_at: datetime
    from_currency: str = Field(min_length=3, max_length=8)
    to_currency: str = Field(min_length=3, max_length=8)
    amount_from: Decimal
    amount_to: Decimal | None = None
    fx_rate: Decimal | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ExchangePatch(BaseModel):
    occurred_at: datetime | None = None
    from_currency: str | None = Field(default=None, min_length=3, max_length=8)
    to_currency: str | None = Field(default=None, min_length=3, max_length=8)
    amount_from: Decimal | None = None
    amount_to: Decimal | None = None
    fx_rate: Decimal | None = None
    notes: str | None = Field(default=None, max_length=2000)


def _row_to_dict(r: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": int(r[0]),
        "occurred_at": r[1].isoformat(),
        "from_currency": r[2],
        "to_currency": r[3],
        "amount_from": str(r[4]),
        "amount_to": str(r[5]) if r[5] is not None else None,
        "fx_rate": str(r[6]) if r[6] is not None else None,
        "notes": r[7],
        "created_at": r[8].isoformat(),
    }


@router.get("/exchanges")
def list_exchanges(user_id: uuid.UUID = Depends(current_user_id)) -> dict[str, Any]:
    sql = """
    SELECT id, occurred_at, from_currency, to_currency, amount_from, amount_to, fx_rate, notes, created_at
    FROM exchange_journal
    WHERE user_id=%(u)s
    ORDER BY occurred_at DESC, id DESC
    LIMIT 500
    """
    with _conn() as c, c.cursor() as cur:
        cur.execute(sql, {"u": user_id})
        rows = cur.fetchall()
    return {"exchanges": [_row_to_dict(r) for r in rows]}


@router.post("/exchanges")
def create_exchange(body: ExchangeIn, user_id: uuid.UUID = Depends(current_user_id)) -> dict[str, Any]:
    sql = """
    INSERT INTO exchange_journal
      (user_id, occurred_at, from_currency, to_currency, amount_from, amount_to, fx_rate, notes)
    VALUES (%(u)s, %(t)s, %(fc)s, %(tc)s, %(af)s, %(at)s, %(fx)s, %(n)s)
    RETURNING id, occurred_at, from_currency, to_currency, amount_from, amount_to, fx_rate, notes, created_at
    """
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            sql,
            {
                "u": user_id,
                "t": body.occurred_at,
                "fc": body.from_currency.upper(),
                "tc": body.to_currency.upper(),
                "af": body.amount_from,
                "at": body.amount_to,
                "fx": body.fx_rate,
                "n": body.notes,
            },
        )
        r = cur.fetchone()
    return _row_to_dict(r)


@router.patch("/exchanges/{exchange_id}")
def patch_exchange(
    exchange_id: int,
    body: ExchangePatch,
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict[str, Any]:
    fields: list[str] = []
    params: dict[str, Any] = {"id": exchange_id, "u": user_id}

    if body.occurred_at is not None:
        fields.append("occurred_at=%(t)s")
        params["t"] = body.occurred_at
    if body.from_currency is not None:
        fields.append("from_currency=%(fc)s")
        params["fc"] = body.from_currency.upper()
    if body.to_currency is not None:
        fields.append("to_currency=%(tc)s")
        params["tc"] = body.to_currency.upper()
    if body.amount_from is not None:
        fields.append("amount_from=%(af)s")
        params["af"] = body.amount_from
    if body.amount_to is not None:
        fields.append("amount_to=%(at)s")
        params["at"] = body.amount_to
    if body.fx_rate is not None:
        fields.append("fx_rate=%(fx)s")
        params["fx"] = body.fx_rate
    if body.notes is not None:
        fields.append("notes=%(n)s")
        params["n"] = body.notes

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    sql = f"""
    UPDATE exchange_journal
    SET {", ".join(fields)}
    WHERE id=%(id)s AND user_id=%(u)s
    RETURNING id, occurred_at, from_currency, to_currency, amount_from, amount_to, fx_rate, notes, created_at
    """
    with _conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Exchange not found")
    return _row_to_dict(r)


@router.delete("/exchanges/{exchange_id}")
def delete_exchange(exchange_id: int, user_id: uuid.UUID = Depends(current_user_id)) -> dict[str, bool]:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "DELETE FROM exchange_journal WHERE id=%(id)s AND user_id=%(u)s",
            {"id": exchange_id, "u": user_id},
        )
        if cur.rowcount != 1:
            raise HTTPException(status_code=404, detail="Exchange not found")
    return {"ok": True}
