"""Clients for the external data Ticker Tutor uses.

  wikipedia.py  S&P 500 members, sectors, and the history of index changes
  prices.py     daily prices (Alpaca, Tiingo, or Stooq)
  sec.py        SEC EDGAR: XBRL fundamentals, filing lists, 10-K text
  news.py       company and market news (Finnhub, or GDELT without a key)
  fred.py       optional market context (FRED)

Every function returns plain Python data and raises SourceError with a message
that says what went wrong and what to try.
"""

from __future__ import annotations

import logging
import random
import time

import httpx

from .. import config

log = logging.getLogger("tickertutor.sources")


class SourceError(Exception):
    pass


_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True,
                               headers={"User-Agent": config.USER_AGENT})
    return _client


def set_client(c: httpx.Client | None) -> None:
    """Swap the HTTP client (tests)."""
    global _client
    _client = c


def host(url: str) -> str:
    return url.split("/")[2] if "://" in url else url


def _snippet(text: str) -> str:
    import re
    t = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(t.split())[:160]


def _refusal_hint(url: str) -> str:
    h = host(url)
    if "wikipedia.org" in h:
        return ("Wikipedia blocks requests whose User-Agent has no contact email. Put your email in "
                "SEC_USER_AGENT in .env (it's used for Wikipedia too). If it still fails, save the page from your "
                "browser and pass --wiki-html (see README).")
    if "sec.gov" in h:
        return "The SEC requires a User-Agent with your name and email: set SEC_USER_AGENT in .env."
    if "gdeltproject" in h:
        return "GDELT may be rate-limiting; try again later or set FINNHUB_API_KEY."
    return "Check the API key in .env and that your plan includes this data."


def get(url: str, params: dict | None = None, headers: dict | None = None, retries: int = 4,
        expect: str = "json"):
    """GET with retries on rate limits and server errors. expect: json | text | bytes."""
    delay = 1.5
    last = ""
    for attempt in range(1, retries + 1):
        try:
            r = client().get(url, params=params, headers=headers)
        except httpx.TimeoutException:
            last = f"{host(url)} timed out"
        except httpx.HTTPError as exc:
            last = f"couldn't reach {host(url)} ({exc.__class__.__name__})"
        else:
            if r.status_code == 429 or r.status_code >= 500:
                last = f"{host(url)} returned HTTP {r.status_code}" + (" (rate limit)" if r.status_code == 429 else "")
                wait = float(r.headers.get("Retry-After", "0") or 0) or delay
                if attempt < retries:
                    time.sleep(min(wait, 60) * random.uniform(0.8, 1.2))
                    delay *= 2
                    continue
                raise SourceError(last + "; try again later")
            if r.status_code in (401, 403):
                raise SourceError(f"{host(url)} refused the request (HTTP {r.status_code}). {_refusal_hint(url)}"
                                  + (f" Server said: {_snippet(r.text)}" if _snippet(r.text) else ""))
            if r.status_code == 404:
                raise SourceError(f"{host(url)} has no data at {url.split('?')[0]} (HTTP 404)")
            if r.status_code >= 400:
                raise SourceError(f"{host(url)} returned HTTP {r.status_code}: {r.text[:200]}")
            if expect == "text":
                return r.text
            if expect == "bytes":
                return r.content
            try:
                return r.json()
            except ValueError as exc:
                raise SourceError(f"{host(url)} returned something that isn't JSON") from exc
        if attempt < retries:
            time.sleep(delay * random.uniform(0.8, 1.2))
            delay *= 2
    raise SourceError(last or f"request to {host(url)} failed")
