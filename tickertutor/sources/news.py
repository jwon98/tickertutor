"""Recent news: Finnhub (free key) for company and market news, or GDELT (no key)
as a fallback. Results are cached for 30 minutes."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone

from .. import config
from . import SourceError, get

_cache: dict[tuple, tuple[float, list[dict]]] = {}
_lock = threading.Lock()
TTL = 1800


def _cached(key: tuple, fn):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < TTL:
            return hit[1]
    value = fn()
    with _lock:
        _cache[key] = (now, value)
    return value


def _finnhub_item(a: dict) -> dict:
    ts = a.get("datetime") or 0
    return {"headline": (a.get("headline") or "").strip(), "summary": (a.get("summary") or "").strip()[:500],
            "source": a.get("source") or "", "url": a.get("url") or "",
            "published": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else "",
            "related": a.get("related") or "", "provider": "Finnhub"}


def company_news(ticker: str, name: str = "", days: int = 14) -> list[dict]:
    days = max(1, min(int(days), 60))
    if config.FINNHUB_API_KEY:
        def fetch():
            to = date.today()
            rows = get("https://finnhub.io/api/v1/company-news",
                       {"symbol": ticker, "from": (to - timedelta(days=days)).isoformat(), "to": to.isoformat(),
                        "token": config.FINNHUB_API_KEY})
            items = [_finnhub_item(a) for a in (rows or []) if a.get("headline")]
            return _dedupe(items)[:30]
        return _cached(("fh", ticker, days), fetch)
    return gdelt(f'"{name or ticker}"', days)


def market_news(topic: str = "general") -> list[dict]:
    if config.FINNHUB_API_KEY:
        def fetch():
            rows = get("https://finnhub.io/api/v1/news", {"category": topic or "general", "token": config.FINNHUB_API_KEY})
            return _dedupe([_finnhub_item(a) for a in (rows or []) if a.get("headline")])[:40]
        return _cached(("fhm", topic), fetch)
    return gdelt("(stocks OR \"stock market\" OR \"S&P 500\")", 3)


def gdelt(query: str, days: int = 7) -> list[dict]:
    def fetch():
        data = get("https://api.gdeltproject.org/api/v2/doc/doc",
                   {"query": f"{query} sourcelang:english", "mode": "ArtList", "format": "json", "maxrecords": 30,
                    "timespan": f"{max(1, min(days, 90))}d", "sort": "DateDesc"})
        out = []
        for a in (data or {}).get("articles", []):
            seen = a.get("seendate") or ""
            try:
                published = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                published = ""
            out.append({"headline": (a.get("title") or "").strip(), "summary": "", "source": a.get("domain") or "",
                        "url": a.get("url") or "", "published": published, "related": "", "provider": "GDELT"})
        return _dedupe(out)[:30]
    try:
        return _cached(("gd", query, days), fetch)
    except SourceError:
        raise
    except Exception as exc:  # noqa: BLE001  (GDELT sometimes returns HTML on overload)
        raise SourceError(f"GDELT news search failed ({exc.__class__.__name__}); try again shortly.") from exc


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        key = it["headline"].lower()[:90]
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def clear_cache() -> None:
    with _lock:
        _cache.clear()
