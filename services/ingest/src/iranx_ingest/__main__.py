import asyncio
import os
import time

import httpx
import psycopg

from .db import health_error, health_success, insert_alerts, insert_rates
from .signals import detect_official_market_spread, detect_return_spike
from .sources.bonbast import BROWSER_HEADERS as BONBAST_HEADERS, fetch_bonbast
from .sources.cbi import fetch_cbi_official


async def ingest_once(database_url: str, *, bonbast_url: str, cbi_url: str) -> None:
    rates = []
    alerts = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        # Market
        try:
            b_client = httpx.AsyncClient(headers=BONBAST_HEADERS, timeout=30, follow_redirects=True)
            async with b_client as bc:
                b_rates = await fetch_bonbast(bc, bonbast_url)
            rates.extend(b_rates)
        except Exception as e:
            with psycopg.connect(database_url) as conn:
                health_error(conn, source="bonbast", tier="market", message=f"{type(e).__name__}: {e}")
        else:
            with psycopg.connect(database_url) as conn:
                health_success(conn, source="bonbast", tier="market", message=f"points={len(b_rates)}")

        # Official
        try:
            c_rates = await fetch_cbi_official(client, cbi_url)
            rates.extend(c_rates)
        except Exception as e:
            with psycopg.connect(database_url) as conn:
                health_error(conn, source="cbi", tier="official", message=f"{type(e).__name__}: {e}")
        else:
            with psycopg.connect(database_url) as conn:
                health_success(conn, source="cbi", tier="official", message=f"points={len(c_rates)}")

    with psycopg.connect(database_url) as conn:
        inserted = insert_rates(conn, rates)

        # Signals for a few key pairs
        for quote in {"USD", "EUR", "GBP"}:
            a = detect_return_spike(conn, tier="market", source="bonbast", base_ccy="IRR", quote_ccy=quote)
            if a:
                alerts.append(a)
            a = detect_return_spike(conn, tier="official", source="cbi", base_ccy="IRR", quote_ccy=quote)
            if a:
                alerts.append(a)
            s = detect_official_market_spread(conn, base_ccy="IRR", quote_ccy=quote)
            if s:
                alerts.append(s)

        inserted_alerts = insert_alerts(conn, alerts)

    print(f"rates_inserted={inserted} alerts_inserted={inserted_alerts}")


def main() -> int:
    database_url = os.environ["DATABASE_URL"]
    enable_loop = os.environ.get("ENABLE_LOOP", "true").lower() in {"1", "true", "yes"}
    poll_seconds = int(os.environ.get("POLL_SECONDS", "60"))
    bonbast_url = os.environ.get("BONBAST_URL", "https://www.bonbast.com/")
    cbi_url = os.environ.get("CBI_URL", "https://www.cbi.ir/ExRates/rates_en.aspx")

    if not enable_loop:
        asyncio.run(ingest_once(database_url, bonbast_url=bonbast_url, cbi_url=cbi_url))
        return 0

    while True:
        try:
            asyncio.run(ingest_once(database_url, bonbast_url=bonbast_url, cbi_url=cbi_url))
        except Exception as e:
            print(f"fatal={type(e).__name__} msg={e}")
        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

