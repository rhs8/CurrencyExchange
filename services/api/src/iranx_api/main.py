from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse


def conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


app = FastAPI(title="Iran FX Watch", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Iran FX Watch</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
          body { font-family: ui-sans-serif, system-ui, -apple-system; margin: 24px; color: #111827; }
          .row { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
          .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; min-width: 340px; background: #fff; }
          .muted { color: #6b7280; }
          code { background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }
        </style>
      </head>
      <body>
        <h2>Iran FX Watch</h2>
        <p class="muted">
          Tracks <b>official</b> vs <b>market</b> IRR rates and alerts on spikes/spread.
          API: <code>/rates/latest</code>, <code>/rates/series</code>, <code>/alerts</code>, <code>/health</code>.
        </p>

        <div class="row">
          <div class="card">
            <h3>Latest IRR/USD</h3>
            <pre id="latest">Loading…</pre>
          </div>

          <div class="card" style="flex: 1; min-width: 520px;">
            <h3>IRR/USD: Official vs Market</h3>
            <canvas id="chart"></canvas>
          </div>
        </div>

        <div class="row" style="margin-top: 16px;">
          <div class="card" style="flex: 1; min-width: 520px;">
            <h3>Recent alerts</h3>
            <pre id="alerts">Loading…</pre>
          </div>
        </div>

        <script>
          async function loadLatest() {
            const r = await fetch('/rates/latest?base_ccy=IRR&quote_ccy=USD');
            document.getElementById('latest').textContent = JSON.stringify(await r.json(), null, 2);
          }

          async function loadSeries() {
            const r1 = await fetch('/rates/series?tier=market&source=bonbast&base_ccy=IRR&quote_ccy=USD&limit=200');
            const r2 = await fetch('/rates/series?tier=official&source=cbi&base_ccy=IRR&quote_ccy=USD&limit=200');
            const m = await r1.json();
            const o = await r2.json();

            const labels = m.points.map(p => p.ts);
            const market = m.points.map(p => p.mid ?? p.bid ?? p.ask);
            const official = o.points.map(p => p.mid ?? p.bid ?? p.ask);

            new Chart(document.getElementById('chart'), {
              type: 'line',
              data: {
                labels,
                datasets: [
                  { label: 'market (bonbast)', data: market, borderColor: '#2563eb', pointRadius: 0 },
                  { label: 'official (cbi)', data: official, borderColor: '#111827', pointRadius: 0 }
                ]
              },
              options: { responsive: true, scales: { x: { display: false } } }
            });
          }

          async function loadAlerts() {
            const r = await fetch('/alerts?base_ccy=IRR&quote_ccy=USD&limit=20');
            document.getElementById('alerts').textContent = JSON.stringify(await r.json(), null, 2);
          }

          loadLatest(); loadSeries(); loadAlerts();
          setInterval(loadLatest, 15000);
          setInterval(loadAlerts, 15000);
        </script>
      </body>
    </html>
    """


@app.get("/health")
def health() -> dict[str, Any]:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT source, tier, last_success, last_error, error_count, last_message
            FROM source_health
            ORDER BY source
            """
        )
        rows = cur.fetchall()
    return {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "sources": [
            {
                "source": r[0],
                "tier": r[1],
                "last_success": r[2].isoformat() if r[2] else None,
                "last_error": r[3].isoformat() if r[3] else None,
                "error_count": int(r[4]),
                "last_message": r[5],
            }
            for r in rows
        ],
    }


@app.get("/rates/latest")
def latest_rates(
    base_ccy: str = Query("IRR"),
    quote_ccy: str | None = Query(None),
) -> dict[str, Any]:
    if quote_ccy is None:
        sql = """
        SELECT DISTINCT ON (tier, source, base_ccy, quote_ccy)
          ts, tier, source, base_ccy, quote_ccy, bid, ask, mid
        FROM rates
        WHERE base_ccy=%(base)s
        ORDER BY tier, source, base_ccy, quote_ccy, ts DESC
        """
        params = {"base": base_ccy}
    else:
        sql = """
        SELECT DISTINCT ON (tier, source, base_ccy, quote_ccy)
          ts, tier, source, base_ccy, quote_ccy, bid, ask, mid
        FROM rates
        WHERE base_ccy=%(base)s AND quote_ccy=%(quote)s
        ORDER BY tier, source, base_ccy, quote_ccy, ts DESC
        """
        params = {"base": base_ccy, "quote": quote_ccy}

    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return {
        "base_ccy": base_ccy,
        "quote_ccy": quote_ccy,
        "as_of": datetime.utcnow().isoformat() + "Z",
        "rates": [
            {
                "ts": r[0].isoformat(),
                "tier": r[1],
                "source": r[2],
                "base_ccy": r[3],
                "quote_ccy": r[4],
                "bid": float(r[5]) if r[5] is not None else None,
                "ask": float(r[6]) if r[6] is not None else None,
                "mid": float(r[7]) if r[7] is not None else None,
            }
            for r in rows
        ],
    }


@app.get("/rates/series")
def rate_series(
    tier: str,
    source: str,
    base_ccy: str,
    quote_ccy: str,
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    sql = """
    SELECT ts, bid, ask, mid
    FROM rates
    WHERE tier=%(tier)s AND source=%(source)s AND base_ccy=%(base)s AND quote_ccy=%(quote)s
    ORDER BY ts DESC
    LIMIT %(limit)s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            sql,
            {"tier": tier, "source": source, "base": base_ccy, "quote": quote_ccy, "limit": limit},
        )
        rows = cur.fetchall()

    pts = [
        {
            "ts": r[0].isoformat(),
            "bid": float(r[1]) if r[1] is not None else None,
            "ask": float(r[2]) if r[2] is not None else None,
            "mid": float(r[3]) if r[3] is not None else None,
        }
        for r in reversed(rows)
    ]
    return {"tier": tier, "source": source, "base_ccy": base_ccy, "quote_ccy": quote_ccy, "points": pts}


@app.get("/alerts")
def alerts(
    base_ccy: str = Query("IRR"),
    quote_ccy: str | None = Query(None),
    limit: int = Query(100, ge=1, le=2000),
) -> dict[str, Any]:
    sql = """
    SELECT ts, rule_id, severity, tier, source, base_ccy, quote_ccy, message, context
    FROM alerts
    WHERE base_ccy=%(base)s
      AND (%(quote)s IS NULL OR quote_ccy=%(quote)s)
    ORDER BY ts DESC
    LIMIT %(limit)s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, {"base": base_ccy, "quote": quote_ccy, "limit": limit})
        rows = cur.fetchall()
    return {
        "base_ccy": base_ccy,
        "quote_ccy": quote_ccy,
        "alerts": [
            {
                "ts": r[0].isoformat(),
                "rule_id": r[1],
                "severity": r[2],
                "tier": r[3],
                "source": r[4],
                "base_ccy": r[5],
                "quote_ccy": r[6],
                "message": r[7],
                "context": r[8],
            }
            for r in rows
        ],
    }

