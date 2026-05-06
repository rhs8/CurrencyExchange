from __future__ import annotations

from collections.abc import Iterable

import psycopg
from psycopg.types.json import Json

from .models import AlertPoint, RatePoint


RATE_INSERT_SQL = """
INSERT INTO rates (ts, source, tier, base_ccy, quote_ccy, bid, ask, mid, meta)
VALUES (%(ts)s, %(source)s, %(tier)s, %(base_ccy)s, %(quote_ccy)s, %(bid)s, %(ask)s, %(mid)s, %(meta)s::jsonb)
ON CONFLICT (ts, source, tier, base_ccy, quote_ccy)
DO UPDATE SET
  bid = COALESCE(EXCLUDED.bid, rates.bid),
  ask = COALESCE(EXCLUDED.ask, rates.ask),
  mid = COALESCE(EXCLUDED.mid, rates.mid),
  meta = rates.meta || EXCLUDED.meta,
  ingested_at = now()
"""

ALERT_INSERT_SQL = """
INSERT INTO alerts (ts, rule_id, severity, tier, source, base_ccy, quote_ccy, message, context)
VALUES (%(ts)s, %(rule_id)s, %(severity)s, %(tier)s, %(source)s, %(base_ccy)s, %(quote_ccy)s, %(message)s, %(context)s::jsonb)
ON CONFLICT (ts, rule_id, tier, source, base_ccy, quote_ccy) DO NOTHING
"""


def insert_rates(conn: psycopg.Connection, points: Iterable[RatePoint]) -> int:
    rows = []
    for p in points:
        d = p.model_dump()
        d["meta"] = Json(d["meta"])
        rows.append(d)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(RATE_INSERT_SQL, rows)
    return len(rows)


def insert_alerts(conn: psycopg.Connection, alerts: Iterable[AlertPoint]) -> int:
    rows = []
    for a in alerts:
        d = a.model_dump()
        d["context"] = Json(d["context"])
        rows.append(d)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(ALERT_INSERT_SQL, rows)
        return cur.rowcount if cur.rowcount != -1 else len(rows)


def health_success(conn: psycopg.Connection, *, source: str, tier: str, message: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_health (source, tier, last_success, last_message)
            VALUES (%(source)s, %(tier)s, now(), %(msg)s)
            ON CONFLICT (source) DO UPDATE SET
              tier=EXCLUDED.tier,
              last_success=EXCLUDED.last_success,
              last_message=EXCLUDED.last_message
            """,
            {"source": source, "tier": tier, "msg": message},
        )


def health_error(conn: psycopg.Connection, *, source: str, tier: str, message: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_health (source, tier, last_error, error_count, last_message)
            VALUES (%(source)s, %(tier)s, now(), 1, %(msg)s)
            ON CONFLICT (source) DO UPDATE SET
              tier=EXCLUDED.tier,
              last_error=EXCLUDED.last_error,
              error_count=source_health.error_count + 1,
              last_message=EXCLUDED.last_message
            """,
            {"source": source, "tier": tier, "msg": message},
        )

