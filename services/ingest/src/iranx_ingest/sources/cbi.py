from __future__ import annotations

from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import RatePoint


def _num(s: str) -> float | None:
    t = (s or "").strip().replace(",", "")
    if not t:
        return None
    filtered = "".join(ch for ch in t if (ch.isdigit() or ch == "."))
    if not filtered:
        return None
    try:
        return float(filtered)
    except ValueError:
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=6))
async def fetch_cbi_official(client: httpx.AsyncClient, url: str) -> list[RatePoint]:
    """
    Best-effort HTML parse of CBI's published exchange rates page.
    We normalize to IRR per 1 unit of quote currency (if the page provides such figures).
    """
    resp = await client.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    now = datetime.now(timezone.utc)
    out: list[RatePoint] = []

    # Heuristic: find table rows containing 3-letter currency codes and a numeric rate.
    # CBI page structure varies; this is designed to be resilient but may need adjustment.
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        cells = [td.get_text(" ", strip=True) for td in tds]

        code = None
        for c in cells:
            if len(c) == 3 and c.isalpha() and c.isupper():
                code = c
                break
        if not code or code == "IRR":
            continue

        # Look for a plausible numeric cell (rate).
        rate = None
        for c in reversed(cells):
            r = _num(c)
            if r is not None and r > 0:
                rate = r
                break
        if rate is None:
            continue

        out.append(
            RatePoint(
                ts=now,
                source="cbi",
                tier="official",
                base_ccy="IRR",
                quote_ccy=code,
                mid=rate,
                meta={"url": url},
            )
        )

    return out

