from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import RatePoint

TOMAN_TO_IRR = 10.0

BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

ALLOWED_QUOTE_CODES: frozenset[str] = frozenset(
    {
        "usd",
        "eur",
        "gbp",
        "chf",
        "cad",
        "aud",
        "sek",
        "nok",
        "rub",
        "thb",
        "sgd",
        "hkd",
        "aed",
        "try",
        "cny",
        "sar",
        "inr",
    }
)


def _origin(url: str) -> str:
    p = urlparse(url)
    scheme = p.scheme or "https"
    host = (p.netloc or "www.bonbast.com").lower()
    if host == "bonbast.com":
        host = "www.bonbast.com"
    return f"{scheme}://{host}"


def _extract_param(html: str) -> str | None:
    m = re.search(r"\$\.post\('/json',\s*\{param:\s*\"([^\"]+)\"\s*\}", html)
    if m:
        return m.group(1)
    m = re.search(r'\{param:\s*"([^"]+)"\}', html)
    return m.group(1) if m else None


def _num(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    filtered = "".join(ch for ch in s if (ch.isdigit() or ch == "."))
    if not filtered:
        return None
    try:
        return float(filtered)
    except ValueError:
        return None


def _control_payload(data: dict[str, Any]) -> bool:
    if not data:
        return True
    keys = {k.lower() for k in data.keys()}
    return ("reset" in keys) or ("rest" in keys) or keys <= {"reset", "rest"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=6))
async def fetch_bonbast(client: httpx.AsyncClient, url: str) -> list[RatePoint]:
    origin = _origin(url)
    index_url = f"{origin}/"
    json_url = f"{origin}/json"

    idx = await client.get(
        index_url,
        headers={**BROWSER_HEADERS, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"},
        timeout=30,
        follow_redirects=True,
    )
    idx.raise_for_status()
    param = _extract_param(idx.text)
    if not param:
        raise RuntimeError("bonbast_param_missing")

    resp = await client.post(
        json_url,
        headers={
            **BROWSER_HEADERS,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": origin,
            "Referer": index_url,
        },
        data={"param": param},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or _control_payload(data):
        raise RuntimeError("bonbast_control_payload")

    now = datetime.now(timezone.utc)
    out: list[RatePoint] = []
    for code in sorted(ALLOWED_QUOTE_CODES):
        bid_toman = _num(data.get(f"{code}1"))
        ask_toman = _num(data.get(f"{code}2"))
        if bid_toman is None and ask_toman is None:
            continue
        bid = bid_toman * TOMAN_TO_IRR if bid_toman is not None else None
        ask = ask_toman * TOMAN_TO_IRR if ask_toman is not None else None
        mid = (bid + ask) / 2.0 if (bid is not None and ask is not None) else None
        out.append(
            RatePoint(
                ts=now,
                source="bonbast",
                tier="market",
                base_ccy="IRR",
                quote_ccy=code.upper(),
                bid=bid,
                ask=ask,
                mid=mid,
                meta={"url": index_url, "unit": "irr", "original_unit": "toman"},
            )
        )
    return out

