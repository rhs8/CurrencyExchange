from __future__ import annotations

from dataclasses import dataclass
from math import fabs

import psycopg

from .models import AlertPoint


def _median(xs: list[float]) -> float:
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return ys[mid]
    return (ys[mid - 1] + ys[mid]) / 2.0


def _mad(xs: list[float], med: float) -> float:
    return _median([fabs(x - med) for x in xs])


def detect_return_spike(
    conn: psycopg.Connection,
    *,
    tier: str,
    source: str,
    base_ccy: str,
    quote_ccy: str,
    lookback: int = 120,
    z_threshold: float = 6.0,
) -> AlertPoint | None:
    sql = """
    SELECT ts, COALESCE(mid, bid, ask) AS px
    FROM rates
    WHERE tier=%(tier)s AND source=%(source)s AND base_ccy=%(base)s AND quote_ccy=%(quote)s
      AND (mid IS NOT NULL OR bid IS NOT NULL OR ask IS NOT NULL)
    ORDER BY ts DESC
    LIMIT %(n)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"tier": tier, "source": source, "base": base_ccy, "quote": quote_ccy, "n": lookback})
        rows = cur.fetchall()
    if len(rows) < 10:
        return None

    rows = list(reversed(rows))
    ts_latest = rows[-1][0]
    px = [float(r[1]) for r in rows]

    rets: list[float] = []
    for i in range(1, len(px)):
        if px[i - 1] <= 0:
            continue
        rets.append((px[i] - px[i - 1]) / px[i - 1])
    if len(rets) < 10:
        return None

    med = _median(rets)
    mad = _mad(rets, med)
    if mad == 0:
        return None

    latest = rets[-1]
    z = 0.6745 * (latest - med) / mad
    if fabs(z) < z_threshold:
        return None

    severity = "high" if fabs(z) >= (z_threshold * 1.5) else "medium"
    direction = "up" if latest > 0 else "down"
    msg = f"{tier} {base_ccy}/{quote_ccy} spike {direction}: return={latest:.2%} z={z:.2f}"

    return AlertPoint(
        ts=ts_latest,
        rule_id="mad_return_spike_v1",
        severity=severity,
        tier=tier,  # type: ignore[arg-type]
        source=source,
        base_ccy=base_ccy,
        quote_ccy=quote_ccy,
        message=msg,
        context={"z": z, "return": latest, "median": med, "mad": mad, "lookback": lookback},
    )


def detect_official_market_spread(
    conn: psycopg.Connection,
    *,
    base_ccy: str,
    quote_ccy: str,
    max_age_minutes: int = 180,
) -> AlertPoint | None:
    """
    Alert when market deviates far from official.
    """
    sql = """
    WITH latest AS (
      SELECT DISTINCT ON (tier)
        tier, ts, COALESCE(mid, bid, ask) AS px
      FROM rates
      WHERE base_ccy=%(base)s AND quote_ccy=%(quote)s
        AND tier IN ('official','market')
        AND (mid IS NOT NULL OR bid IS NOT NULL OR ask IS NOT NULL)
      ORDER BY tier, ts DESC
    )
    SELECT
      (SELECT ts FROM latest WHERE tier='market') AS market_ts,
      (SELECT px FROM latest WHERE tier='market') AS market_px,
      (SELECT ts FROM latest WHERE tier='official') AS official_ts,
      (SELECT px FROM latest WHERE tier='official') AS official_px
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"base": base_ccy, "quote": quote_ccy})
        row = cur.fetchone()
    if not row:
        return None
    m_ts, m_px, o_ts, o_px = row
    if m_ts is None or m_px is None or o_ts is None or o_px is None:
        return None

    # Age gate
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (now() - %(t)s::timestamptz))",
            {"t": m_ts.isoformat()},
        )
        m_age = float(cur.fetchone()[0])
        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (now() - %(t)s::timestamptz))",
            {"t": o_ts.isoformat()},
        )
        o_age = float(cur.fetchone()[0])
    if m_age > (max_age_minutes * 60) or o_age > (max_age_minutes * 60):
        return None

    spread = float(m_px) - float(o_px)
    spread_pct = spread / float(o_px) if float(o_px) != 0 else 0.0

    # Simple threshold for v1; tune later.
    if fabs(spread_pct) < 0.15:
        return None

    severity = "high" if fabs(spread_pct) >= 0.30 else "medium"
    direction = "above" if spread > 0 else "below"
    msg = f"market is {direction} official for {base_ccy}/{quote_ccy}: spread={spread_pct:.1%}"

    return AlertPoint(
        ts=m_ts,
        rule_id="official_market_spread_v1",
        severity=severity,
        tier="market",  # alert is about market vs official
        source="derived",
        base_ccy=base_ccy,
        quote_ccy=quote_ccy,
        message=msg,
        context={"spread": spread, "spread_pct": spread_pct, "market": float(m_px), "official": float(o_px)},
    )

