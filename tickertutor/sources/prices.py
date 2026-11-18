"""Daily stock prices from one of three providers.

  alpaca   free account (paper trading is enough). Official API, fast: many
           symbols per request. History starts in 2016.
  tiingo   free API key. History back to the 1990s, but the free plan is
           rate-limited, so a full download can take several sessions (the
           cache below makes it resumable).
  stooq    no key. Best effort: fine for a quick start, but its adjustments for
           dividends may be incomplete, so total returns are approximate.

Each provider returns rows of (ticker, date, close, adj_close, volume):
  close      the price as it traded that day (used with reported earnings for P/E)
  adj_close  adjusted for splits and dividends (used for returns: total return)

Downloads are cached per ticker in data/cache/prices, so an interrupted build
picks up where it stopped.
"""

from __future__ import annotations

import io
import logging
import time
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from .. import config
from ..indexes import TICKERS as INDEX_TICKERS
from . import SourceError, get

log = logging.getLogger("tickertutor.prices")

BENCHMARK = "SPY"
# Funds that track the other big indexes (SPY above covers the S&P 500).
INDEX_FUNDS = [t for t in INDEX_TICKERS if t != BENCHMARK]
SECTOR_ETFS = {
    "Communication Services": "XLC", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Energy": "XLE", "Financials": "XLF", "Health Care": "XLV", "Industrials": "XLI",
    "Information Technology": "XLK", "Materials": "XLB", "Real Estate": "XLRE", "Utilities": "XLU",
}
COLUMNS = ["ticker", "date", "close", "adj_close", "volume"]
NEW_YORK = "America/New_York"
SETTLED_HOUR = 18   # US markets close at 4 pm New York time; by 6 pm the day's closing prices are final


def last_finished_day(now: pd.Timestamp | None = None) -> date:
    """The most recent weekday whose closing prices are final. Market holidays aren't known here, so on a
    holiday this names a day with no trading, and the providers simply have nothing newer."""
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz=NEW_YORK)
    day = now.normalize()
    if now.hour < SETTLED_HOUR:
        day -= pd.Timedelta(days=1)
    while day.weekday() >= 5:
        day -= pd.Timedelta(days=1)
    return day.date()


def settled_at(day: date) -> float:
    """When a trading day's prices became final, as a Unix time."""
    return pd.Timestamp(day, tz=NEW_YORK).replace(hour=SETTLED_HOUR).timestamp()


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


# --- Alpaca -------------------------------------------------------------------------------

def _alpaca_bars(symbols: list[str], start: date, end: date, adjustment: str, feed: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {s: [] for s in symbols}
    token = None
    headers = {"APCA-API-KEY-ID": config.ALPACA_API_KEY, "APCA-API-SECRET-KEY": config.ALPACA_API_SECRET}
    while True:
        params = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": start.isoformat(),
                  "end": end.isoformat(), "adjustment": adjustment, "feed": feed, "limit": 10000}
        if token:
            params["page_token"] = token
        data = get("https://data.alpaca.markets/v2/stocks/bars", params, headers=headers)
        for sym, bars in (data.get("bars") or {}).items():
            out.setdefault(sym, []).extend(bars or [])
        token = data.get("next_page_token")
        if not token:
            return out


def alpaca(tickers: list[str], start: date, end: date) -> pd.DataFrame:
    if not (config.ALPACA_API_KEY and config.ALPACA_API_SECRET):
        raise SourceError("Set ALPACA_API_KEY and ALPACA_API_SECRET (free at alpaca.markets → Paper trading → API keys).")
    start = max(start, date(2016, 1, 1))
    frames = []
    feed = "sip"
    def both(chunk):
        return _alpaca_bars(chunk, start, end, "all", feed), _alpaca_bars(chunk, start, end, "raw", feed)

    for i in range(0, len(tickers), 50):
        chunk = tickers[i:i + 50]
        try:
            adj, raw = both(chunk)
        except SourceError as exc:
            if feed == "sip" and "refused" in str(exc):
                feed = "iex"   # some free plans only include the IEX feed
                adj, raw = both(chunk)
            elif "refused" in str(exc) or "rate limit" in str(exc):
                raise
            else:
                # One bad symbol (e.g. an old ticker Alpaca doesn't know) can fail the whole request:
                # retry one by one and skip the ones that fail.
                adj, raw = {}, {}
                for sym in chunk:
                    try:
                        a, r = both([sym])
                        adj.update(a); raw.update(r)
                    except SourceError as one:
                        log.warning("alpaca: no prices for %s (%s)", sym, one)
        for sym in chunk:
            a = pd.DataFrame(adj.get(sym) or [])
            r = pd.DataFrame(raw.get(sym) or [])
            if a.empty:
                continue
            a["date"] = pd.to_datetime(a["t"]).dt.tz_convert("America/New_York").dt.date
            df = pd.DataFrame({"ticker": sym, "date": a["date"], "adj_close": a["c"].astype(float),
                               "volume": a["v"].astype(float)})
            if not r.empty:
                r["date"] = pd.to_datetime(r["t"]).dt.tz_convert("America/New_York").dt.date
                df = df.merge(r[["date", "c"]].rename(columns={"c": "close"}), on="date", how="left")
            else:
                df["close"] = df["adj_close"]
            df["close"] = df["close"].fillna(df["adj_close"])
            frames.append(df[COLUMNS])
        log.info("alpaca: %d/%d tickers", min(i + 50, len(tickers)), len(tickers))
    return pd.concat(frames, ignore_index=True) if frames else _empty()


# --- Tiingo -------------------------------------------------------------------------------

def tiingo_one(ticker: str, start: date, end: date) -> pd.DataFrame:
    if not config.TIINGO_API_KEY:
        raise SourceError("Set TIINGO_API_KEY (free at tiingo.com → Account → API).")
    sym = ticker.replace(".", "-")
    rows = get(f"https://api.tiingo.com/tiingo/daily/{sym}/prices",
               {"startDate": start.isoformat(), "endDate": end.isoformat(), "token": config.TIINGO_API_KEY,
                "format": "json"})
    if not rows:
        return _empty()
    df = pd.DataFrame(rows)
    return pd.DataFrame({"ticker": ticker, "date": pd.to_datetime(df["date"]).dt.date, "close": df["close"].astype(float),
                         "adj_close": df["adjClose"].astype(float), "volume": df["volume"].astype(float)})


# --- Stooq --------------------------------------------------------------------------------

def stooq_one(ticker: str, start: date, end: date) -> pd.DataFrame:
    sym = ticker.replace(".", "-").lower() + ".us"
    text = get("https://stooq.com/q/d/l/", {"s": sym, "i": "d", "d1": start.strftime("%Y%m%d"),
                                            "d2": end.strftime("%Y%m%d")}, expect="text")
    if not text or text.startswith("No data") or "Exceeded" in text[:200]:
        if "Exceeded" in (text or "")[:200]:
            raise SourceError("Stooq's daily download limit was reached; try again tomorrow or use Alpaca/Tiingo.")
        return _empty()
    df = pd.read_csv(io.StringIO(text))
    if "Close" not in df.columns:
        return _empty()
    return pd.DataFrame({"ticker": ticker, "date": pd.to_datetime(df["Date"]).dt.date, "close": df["Close"].astype(float),
                         "adj_close": df["Close"].astype(float), "volume": df.get("Volume", 0)})


# --- Cached download -------------------------------------------------------------------------

def download(tickers: list[str], start: date, end: date, provider: str | None = None,
             on_progress: Callable[[int, int], None] | None = None) -> pd.DataFrame:
    """Prices for every ticker (missing ones are skipped and logged). Cached per ticker."""
    provider = (provider or config.PRICE_PROVIDER).lower()
    cache = config.CACHE_DIR / "prices" / provider
    cache.mkdir(parents=True, exist_ok=True)

    def path(t: str) -> Path:
        return cache / f"{t.replace('.', '_')}.csv"

    # A saved file is good while it was downloaded after the last day it needs became final. (Asked for a day
    # that isn't final yet, fall back to "less than 18 hours old".)
    cutoff = settled_at(end) if settled_at(end) <= time.time() else time.time() - 18 * 3600

    def has_day(p: Path) -> bool:
        try:
            with open(p, "rb") as fh:
                fh.seek(max(0, p.stat().st_size - 200))
                return end.isoformat().encode() in fh.read()
        except OSError:
            return False

    def fresh(t: str) -> bool:
        # ...unless it's missing the last day and wasn't fetched in the past few hours: the provider may have
        # been late with that day, so ask again.
        p = path(t)
        if not p.exists() or p.stat().st_mtime < cutoff:
            return False
        return time.time() - p.stat().st_mtime < 3 * 3600 or has_day(p)

    todo = [t for t in tickers if not fresh(t)]
    if todo:
        if provider == "alpaca":
            df = alpaca(todo, start, end)
            for t in todo:
                part = df[df["ticker"] == t]
                part.to_csv(path(t), index=False)
        else:
            fetch = {"tiingo": tiingo_one, "stooq": stooq_one}.get(provider)
            if fetch is None:
                raise SourceError(f"Unknown PRICE_PROVIDER '{provider}'. Use alpaca, tiingo, or stooq.")
            for n, t in enumerate(todo, 1):
                try:
                    fetch(t, start, end).to_csv(path(t), index=False)
                except SourceError as exc:
                    if "limit" in str(exc).lower() or "rate" in str(exc).lower():
                        raise SourceError(f"{exc} Downloaded {n - 1} of {len(todo)} so far; rerun the build "
                                          "later and it will continue from the cache.") from exc
                    log.warning("no prices for %s: %s", t, exc)
                    _empty().to_csv(path(t), index=False)
                if on_progress:
                    on_progress(n, len(todo))
                if provider == "tiingo":
                    time.sleep(0.4)
    frames = []
    for t in tickers:
        p = path(t)
        if p.exists() and p.stat().st_size > 40:
            frames.append(pd.read_csv(p, parse_dates=["date"]))
    if not frames:
        return _empty()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out = out[out["date"] <= end]   # a cached file can hold a later (even unfinished) day than this run asked for
    return out[COLUMNS]
