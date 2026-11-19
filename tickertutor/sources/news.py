"""Recent news: Finnhub (free key) for company and market news, or GDELT (no key)
as a fallback. Results are cached for 30 minutes."""

from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

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


def _opens(item: dict) -> bool:
    """Google News RSS links only open through a redirect page that often fails, so skip those."""
    host = urlparse(item.get("url") or "").netloc.lower()
    return bool(host) and host != "news.google.com"


def company_news(ticker: str, name: str = "", days: int = 14) -> list[dict]:
    days = max(1, min(int(days), 60))
    if config.FINNHUB_API_KEY:
        def fetch():
            to = date.today()
            rows = get("https://finnhub.io/api/v1/company-news",
                       {"symbol": ticker, "from": (to - timedelta(days=days)).isoformat(), "to": to.isoformat(),
                        "token": config.FINNHUB_API_KEY})
            items = [_finnhub_item(a) for a in (rows or []) if a.get("headline")]
            return _dedupe([it for it in items if _opens(it)])[:30]
        return _cached(("fh", ticker, days), fetch)
    return gdelt(f'"{name or ticker}"', days)


def market_news(topic: str = "general") -> list[dict]:
    if config.FINNHUB_API_KEY:
        def fetch():
            rows = get("https://finnhub.io/api/v1/news", {"category": topic or "general", "token": config.FINNHUB_API_KEY})
            items = [_finnhub_item(a) for a in (rows or []) if a.get("headline")]
            return _dedupe([it for it in items if _opens(it) and is_market_story(it)])[:40]
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
        return _dedupe([it for it in out if _opens(it)])[:30]
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


# --- is a headline about this company? ------------------------------------------------------------------------
# Feeds tag articles loosely: a market roundup or a story about a rival often comes back for a ticker. A headline
# counts only if its headline (or the start of its summary) names the company or its ticker.

_SUFFIX = re.compile(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.?|plc|PLC|Ltd\.?|Limited|Holdings?|"
                     r"Group|N\.V\.|S\.A\.|SE|AG|L\.P\.|Trust)$", re.I)
# First words too ordinary to stand for a company on their own ("First Solar" is fine, "First" is not).
_GENERIC = {"advanced", "air", "alliant", "allied", "american", "applied", "bank", "best", "capital", "central", "consolidated",
            "digital", "dollar", "eastern", "electronic", "energy", "federal", "fidelity", "first", "general", "global",
            "great", "home", "intercontinental", "international", "national", "new", "northern", "old", "public",
            "realty", "regency", "republic", "royal", "southern", "southwest", "state", "super", "united", "universal",
            "western", "world"}
# Tickers that are also everyday words in capitals: only count them as "$ALL", "(ALL)", or "NYSE: ALL".
_WORD_TICKERS = {"A", "ALL", "ARE", "BALL", "BE", "C", "CAT", "D", "DAY", "DD", "DG", "EL", "F", "FAST", "GD", "GE",
                 "HAS", "HD", "IT", "J", "K", "KEY", "KO", "L", "LOW", "MA", "MAS", "MO", "MS", "NOW", "O", "ON", "PEAK",
                 "PM", "SO", "T", "TT", "V", "WELL", "WAT", "WM", "X"}
# Names people and headlines use that don't start the official name.
_ALSO = {"GOOGL": ["Google"], "GOOG": ["Google"], "META": ["Facebook", "Instagram"], "KO": ["Coke"], "BRK.B": ["Berkshire"],
         "JPM": ["JPMorgan", "Chase"], "XOM": ["Exxon"], "DIS": ["Disney"], "TTWO": ["Take-Two"], "MCD": ["McDonald's"],
         "AMZN": ["AWS"], "NVDA": ["Nvidia"], "CMG": ["Chipotle"], "LLY": ["Eli Lilly", "Lilly"], "BKNG": ["Booking"],
         "UNH": ["UnitedHealth"], "GM": ["GM"], "HPE": ["HPE"], "HPQ": ["HP Inc"], "PYPL": ["PayPal"]}


def name_keys(name: str, ticker: str = "") -> list[str]:
    n = re.sub(r"\s*\(.*?\)\s*$", "", name or "").strip()
    n = re.sub(r"^The\s+", "", n)
    prev = None
    while prev != n:
        prev, n = n, _SUFFIX.sub("", n).strip().rstrip(",")
    keys = {n} if len(n) >= 3 else set()
    words = n.split()
    if len(words) >= 3 and words[1][:1].isupper():
        keys.add(" ".join(words[:2]))
    if len(words) >= 2 and len(words[0]) >= 4 and words[0].lower().strip(".,") not in _GENERIC:
        keys.add(words[0].rstrip(".,"))
    keys.update(_ALSO.get(ticker.upper(), []))
    return sorted(keys, key=len, reverse=True)


def _patterns(name: str, ticker: str) -> list[re.Pattern]:
    pats = [re.compile(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", re.I) for k in name_keys(name, ticker)]
    t = re.escape(ticker.upper())
    if ticker and len(ticker) >= 2 and ticker.upper() not in _WORD_TICKERS:
        pats.append(re.compile(r"(?<![A-Za-z0-9.])\$?" + t + r"(?![A-Za-z0-9])"))
    elif ticker:
        pats.append(re.compile(r"(\$|\(|:\s?)" + t + r"(?![A-Za-z0-9])"))
    return pats


def _names_it(text: str, pats: list[re.Pattern]) -> bool:
    # A name only counts as a proper noun ("Apple shares", not "apple pie"), so the match must start with a capital.
    return any(m and m.group(0).lstrip("$(: ")[:1].isupper() for p in pats for m in [p.search(text or "")])


def mentions(item: dict, name: str, ticker: str, pats: list[re.Pattern] | None = None) -> int:
    """2 if the headline names the company, 1 if only the start of the summary does, 0 if neither."""
    pats = pats or _patterns(name, ticker)
    if _names_it(item.get("headline", ""), pats):
        return 2
    return 1 if _names_it((item.get("summary") or "")[:220], pats) else 0


def about(items: list[dict], name: str, ticker: str) -> list[dict]:
    """Only the articles about this company, the ones that name it in the headline first."""
    pats = _patterns(name, ticker)
    scored = [(mentions(it, name, ticker, pats), i, it) for i, it in enumerate(items)]
    return [it for score, _, it in sorted(scored, key=lambda x: (-x[0], x[1])) if score]


_MARKET_WORDS = re.compile(
    r"\b(stocks?|shares|stock market|markets?|S&P|Dow|Nasdaq|Wall Street|investors?|earnings|profits?|revenue|"
    r"Fed|Federal Reserve|interest rates?|rate cuts?|rate hikes?|inflation|CPI|jobs report|payrolls|economy|GDP|"
    r"recession|Treasury|Treasuries|yields?|bonds?|oil prices|crude|IPO|merger|acquisition|buyback|dividends?|"
    r"tariffs?|analysts?|rally|sell-?off|ETFs?|futures|semiconductors?|chipmakers?)\b", re.I)


def is_market_story(item: dict) -> bool:
    """Keeps business and market stories from a general feed and drops world news that rides along with it."""
    return bool(_MARKET_WORDS.search(item.get("headline", "")))


def clear_cache() -> None:
    with _lock:
        _cache.clear()
