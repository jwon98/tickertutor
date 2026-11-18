"""What each page of the app shows, assembled from the database."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import indexes as idx
from . import indicators
from .data import DataError, clean, db, last_day, ticker_or_error
from .sectors import SECTOR_INFO

SORTS = {
    "market_cap": "c.market_cap DESC NULLS LAST", "ticker": "c.ticker ASC", "change_1d": "s.change_1d DESC NULLS LAST",
    "ret_1m": "s.ret_1m DESC NULLS LAST", "ret_ytd": "s.ret_ytd DESC NULLS LAST", "ret_1y": "s.ret_1y DESC NULLS LAST",
    "pe": "s.pe ASC NULLS LAST", "dividend_yield": "s.dividend_yield DESC NULLS LAST", "vol": "s.vol_1y ASC NULLS LAST",
    "beta": "s.beta_1y ASC NULLS LAST", "dist_52w_high": "s.dist_52w_high DESC NULLS LAST",
}
ROW_COLS = """c.ticker, c.name, c.sector, c.sub_industry, c.market_cap, c.member_since,
  s.price, s.change_1d, s.ret_1m, s.ret_ytd, s.ret_1y, s.ret_5y_ann, s.rsi14, s.dist_52w_high, s.vol_1y, s.beta_1y,
  s.pe, s.dividend_yield, s.revenue_growth, s.op_margin, s.max_drawdown"""


def screener(sector: str = "", sort: str = "market_cap", q: str = "", limit: int = 600) -> list[dict]:
    clauses, params = ["1=1"], []
    if sector:
        clauses.append("c.sector = ?")
        params.append(sector)
    if q:
        clauses.append("(lower(c.ticker) LIKE ? OR lower(c.name) LIKE ?)")
        params += [f"{q.lower()}%", f"%{q.lower()}%"]
    order = SORTS.get(sort, SORTS["market_cap"])
    return db().rows(f"SELECT {ROW_COLS} FROM companies c JOIN snapshot s USING (ticker) WHERE {' AND '.join(clauses)} "
                     f"ORDER BY {order} LIMIT {int(limit)}", params)


def tickers() -> list[dict]:
    """Compact list for the search boxes: the index funds that have prices, then every company by size."""
    have = _index_tickers_with_prices()
    funds = [{"ticker": i["ticker"], "name": i["name"], "sector": "Index fund", "kind": "index"}
             for i in idx.INDEXES if i["ticker"] in have]
    rows = db().rows("SELECT ticker, name, sector FROM companies ORDER BY market_cap DESC NULLS LAST")
    return funds + [{**r, "kind": "stock"} for r in rows]


def _index_tickers_with_prices() -> set[str]:
    marks = ",".join("?" * len(idx.TICKERS))
    return {r["ticker"] for r in db().rows(f"SELECT DISTINCT ticker FROM prices WHERE ticker IN ({marks})", idx.TICKERS)}


def market_indexes() -> list[dict]:
    """The big indexes (through the funds that track them): recent returns, risk, and a one-year sparkline.

    An index without prices in the database (built before index funds were added) comes back with
    available = False, so the page can say to rerun the build instead of failing.
    """
    marks = ",".join("?" * len(idx.TICKERS))
    df = db().df(f"SELECT ticker, date, adj_close FROM prices WHERE ticker IN ({marks}) AND date <= CAST(? AS DATE) "
                 "ORDER BY date", [*idx.TICKERS, last_day()])
    out = []
    for info in idx.INDEXES:
        row = {k: info[k] for k in ("id", "ticker", "name", "label", "short", "fund")}
        s = df[df["ticker"] == info["ticker"]].set_index(pd.to_datetime(df.loc[df["ticker"] == info["ticker"], "date"]))["adj_close"]
        s = s.dropna().astype(float)
        if len(s) < 30:
            out.append({**row, "available": False})
            continue
        end = s.index[-1]

        def ret_since(start):
            base = s.loc[:start]
            return float(s.iloc[-1] / base.iloc[-1] - 1) if len(base) else None

        last_year = s.loc[end - pd.DateOffset(years=1):]
        weekly = last_year.iloc[::5]
        if weekly.index[-1] != end:
            weekly = pd.concat([weekly, s.iloc[-1:]])
        daily = s.pct_change().loc[end - pd.DateOffset(years=1):].dropna()
        out.append({**row, "available": True, "as_of": str(end.date()), "price": float(s.iloc[-1]),
                    "change_1d": float(s.iloc[-1] / s.iloc[-2] - 1),
                    "ret_1m": ret_since(end - pd.DateOffset(months=1)),
                    "ret_ytd": ret_since(pd.Timestamp(end.year, 1, 1) - pd.Timedelta(days=1)),
                    "ret_1y": ret_since(end - pd.DateOffset(years=1)),
                    "vol_1y": float(daily.std() * np.sqrt(252)) if len(daily) > 20 else None,
                    "dist_52w_high": float(s.iloc[-1] / last_year.max() - 1),
                    "spark": [round(float(v), 4) for v in weekly.to_numpy()]})
    return clean(out)


def _sectors() -> list[dict]:
    rows = db().rows("SELECT * FROM sectors ORDER BY market_cap DESC NULLS LAST")
    for r in rows:
        r.update(SECTOR_INFO.get(r["sector"], {}))
    return rows


def overview() -> dict:
    m = db().meta()
    largest = db().rows("SELECT ticker, name, sector FROM companies ORDER BY market_cap DESC NULLS LAST LIMIT 1")
    by_sector = {r["sector"]: r for r in db().rows(
        "SELECT sector, arg_max(ticker, market_cap) AS ticker, arg_max(name, market_cap) AS name FROM companies GROUP BY sector")}
    # A few starting points: the largest company overall and in a few sectors (by size, not a recommendation).
    examples = []
    for analysis_id, label, row in [("moving_averages", "Moving averages", largest[0] if largest else None),
                                    ("volatility", "Volatility", by_sector.get("Consumer Staples")),
                                    ("beta", "Beta & correlation", by_sector.get("Financials")),
                                    ("drawdown", "Drawdowns", by_sector.get("Energy"))]:
        if row:
            examples.append({"analysis": analysis_id, "label": label, "ticker": row["ticker"], "name": row["name"]})
    n = db().rows("SELECT count(*) AS n FROM companies")[0]["n"]
    return {"market": m.get("market", {}), "indexes": market_indexes(), "sectors": _sectors(), "n": n,
            "examples": examples}


def signal_evidence(signal_ids: list[str], sector: str | None = None) -> list[dict]:
    """Backtest report cards for signals tied to an analysis, across all stocks and within one sector."""
    if not signal_ids:
        return []
    marks = ",".join("?" * len(signal_ids))
    universes = ["All"] + ([sector] if sector else [])
    rows = db().rows(f"SELECT * FROM signal_cards WHERE signal_id IN ({marks}) AND universe IN ({','.join('?' * len(universes))})",
                     [*signal_ids, *universes])
    out = []
    for sid in signal_ids:
        card = next((r for r in rows if r["signal_id"] == sid and r["universe"] == "All"), None)
        if card:
            out.append({**card, "sector_card": next((r for r in rows if r["signal_id"] == sid and r["universe"] == sector), None)})
    return out


def signal_cards(universe: str = "All") -> list[dict]:
    return db().rows("SELECT * FROM signal_cards WHERE universe = ? ORDER BY family, signal_id", [universe])


def _period_returns(ticker: str, sector: str) -> list[dict]:
    """Returns over common periods for the stock, the S&P 500, and the sector fund (dividends included)."""
    from .sources.prices import SECTOR_ETFS
    etf = SECTOR_ETFS.get(sector)
    names = [ticker, "SPY"] + ([etf] if etf else [])
    df = db().df(f"SELECT ticker, date, adj_close FROM prices WHERE ticker IN ({','.join('?' * len(names))}) "
                 "AND date <= CAST(? AS DATE) ORDER BY date", [*names, last_day()])
    wide = df.pivot(index="date", columns="ticker", values="adj_close")
    wide.index = pd.to_datetime(wide.index)
    s = wide[ticker].dropna()
    if s.empty:
        return []
    end = s.index[-1]
    wide = wide.loc[:end].ffill()
    rows = []
    for key, label, start, years in [("1m", "1 month", end - pd.DateOffset(months=1), None),
                                     ("3m", "3 months", end - pd.DateOffset(months=3), None),
                                     ("ytd", "Year to date", pd.Timestamp(end.year, 1, 1) - pd.Timedelta(days=1), None),
                                     ("1y", "1 year", end - pd.DateOffset(years=1), None),
                                     ("3y", "3 years, per year", end - pd.DateOffset(years=3), 3),
                                     ("5y", "5 years, per year", end - pd.DateOffset(years=5), 5)]:
        if start < s.index[0]:
            continue
        base = wide.loc[:start].iloc[-1] if len(wide.loc[:start]) else None
        if base is None:
            continue
        def r(col):
            if col not in wide or pd.isna(base.get(col)) or pd.isna(wide[col].iloc[-1]):
                return None
            total = wide[col].iloc[-1] / base[col] - 1
            return float((1 + total) ** (1 / years) - 1) if years else float(total)
        rows.append({"period": key, "label": label, "stock": r(ticker), "spy": r("SPY"), "sector": r(etf) if etf else None})
    return rows


def stock(ticker: str) -> dict:
    t = ticker_or_error(ticker)
    comp = db().rows("SELECT * FROM companies WHERE ticker = ?", [t])[0]
    comp.update({"sector_" + k: v for k, v in SECTOR_INFO.get(comp["sector"], {}).items()})
    snap = db().rows("SELECT * FROM snapshot WHERE ticker = ?", [t])
    if not snap:
        raise DataError(f"No price data for {t}.")
    fundamentals = db().rows("SELECT * FROM fundamentals WHERE ticker = ? ORDER BY fy_end DESC LIMIT 10", [t])
    earnings = db().rows("SELECT * FROM earnings WHERE ticker = ? ORDER BY date DESC LIMIT 8", [t])
    filings = db().rows("SELECT form, filed, items, item_names, url FROM filings WHERE ticker = ? ORDER BY filed DESC "
                        "LIMIT 12", [t])
    moves = db().rows("SELECT * FROM recent_moves WHERE ticker = ? ORDER BY date DESC", [t])
    news = db().rows("SELECT headline, summary, source, url, published, provider FROM news WHERE ticker = ? "
                     "ORDER BY published DESC LIMIT 8", [t])
    peers = db().rows(f"SELECT {ROW_COLS} FROM companies c JOIN snapshot s USING (ticker) WHERE c.sector = ? "
                      "AND c.ticker <> ? ORDER BY c.market_cap DESC NULLS LAST LIMIT 6", [comp["sector"], t])
    sector = db().rows("SELECT * FROM sectors WHERE sector = ?", [comp["sector"]])
    return {"company": comp, "snapshot": snap[0], "returns": _period_returns(t, comp["sector"]),
            "fundamentals": fundamentals, "earnings": earnings, "filings": filings, "recent_moves": moves,
            "news": news, "peers": peers, "sector": sector[0] if sector else None}


def index_page(ticker: str) -> dict:
    """One index, through the fund that tracks it: what it is, returns next to the other indexes, and risk."""
    info = idx.get(ticker)
    if not info:
        raise DataError(f"{ticker} isn't one of the indexes Ticker Tutor follows ({', '.join(idx.TICKERS)}).")
    t = info["ticker"]
    marks = ",".join("?" * len(idx.TICKERS))
    df = db().df(f"SELECT ticker, date, close, adj_close FROM prices WHERE ticker IN ({marks}) AND date <= CAST(? AS DATE) "
                 "ORDER BY date", [*idx.TICKERS, last_day()])
    wide = df.pivot(index="date", columns="ticker", values="adj_close")
    wide.index = pd.to_datetime(wide.index)
    if t not in wide or wide[t].dropna().shape[0] < 30:
        raise DataError(f"No prices for {t} (the {info['name']} fund) yet. Rerun the data build to add the index "
                        "funds: uv run python scripts/build_data.py")
    s = wide[t].dropna().astype(float)
    end = s.index[-1]
    wide = wide.loc[:end].ffill()
    present = [x for x in idx.TICKERS if x in wide and wide[x].notna().sum() >= 30]

    periods = [("1m", "1 month", end - pd.DateOffset(months=1), None), ("3m", "3 months", end - pd.DateOffset(months=3), None),
               ("ytd", "This year", pd.Timestamp(end.year, 1, 1) - pd.Timedelta(days=1), None),
               ("1y", "1 year", end - pd.DateOffset(years=1), None), ("3y", "3 years", end - pd.DateOffset(years=3), 3),
               ("5y", "5 years", end - pd.DateOffset(years=5), 5)]
    periods = [p for p in periods if p[2] >= s.index[0]]

    def ret(col: str, start, years):
        base = wide[col].loc[:start].dropna()
        if base.empty or pd.isna(wide[col].iloc[-1]):
            return None
        total = wide[col].iloc[-1] / base.iloc[-1] - 1
        return float((1 + total) ** (1 / years) - 1) if years else float(total)

    returns = [{"ticker": x, "name": idx.get(x)["name"], "label": idx.get(x)["label"], "me": x == t,
                "values": [ret(x, start, years) for _, _, start, years in periods]} for x in [t] + [x for x in present if x != t]]

    year = s.loc[end - pd.DateOffset(years=1):]
    daily = s.pct_change().dropna()
    daily_1y = daily.loc[end - pd.DateOffset(years=1):]
    dd = indicators.drawdowns(s)
    beta = None
    if t != "SPY" and "SPY" in wide:
        both = pd.concat([daily_1y, wide["SPY"].pct_change().reindex(daily_1y.index)], axis=1).dropna()
        if len(both) > 60 and both.iloc[:, 1].var() > 0:
            beta = float(both.iloc[:, 0].cov(both.iloc[:, 1]) / both.iloc[:, 1].var())
    rsi = indicators.rsi(s).iloc[-1]
    close = df[df["ticker"] == t]["close"].dropna()
    snap = {"as_of": str(end.date()), "history_start": str(s.index[0].date()),
            "price": float(close.iloc[-1]) if len(close) else float(s.iloc[-1]),
            "change_1d": float(s.iloc[-1] / s.iloc[-2] - 1),
            "ret_1y": ret(t, end - pd.DateOffset(years=1), None),
            "ret_5y_ann": ret(t, end - pd.DateOffset(years=5), 5) if end - pd.DateOffset(years=5) >= s.index[0] else None,
            "dist_52w_high": float(s.iloc[-1] / year.max() - 1), "rsi14": None if pd.isna(rsi) else float(rsi),
            "vol_1y": float(daily_1y.std() * np.sqrt(252)) if len(daily_1y) > 20 else None, "beta_1y": beta,
            "max_drawdown": dd["max_drawdown"], "dd_peak": str(dd["peak_date"].date()), "dd_trough": str(dd["trough_date"].date()),
            "dd_recovered": str(dd["recovered_date"].date()) if dd["recovered_date"] is not None else None,
            "dd_days_to_recover": dd["days_to_recover"], "current_drawdown": dd["current_drawdown"]}

    # For the S&P 500 we know the members, so show how much of it the biggest companies make up.
    holdings = None
    if t == "SPY":
        rows = db().rows("SELECT c.ticker, c.name, c.sector, c.market_cap, s.ret_1y FROM companies c LEFT JOIN snapshot s "
                         "USING (ticker) WHERE c.market_cap IS NOT NULL ORDER BY c.market_cap DESC")
        total = sum(r["market_cap"] for r in rows) or 0
        if total:
            top = [{**r, "share": r["market_cap"] / total} for r in rows[:10]]
            holdings = {"top": top, "top_share": sum(r["share"] for r in top), "n": len(rows)}
    return clean({"index": {**info, "available": True}, "snapshot": snap,
                  "periods": [{"period": k, "label": lab, "per_year": bool(y)} for k, lab, _, y in periods],
                  "returns": returns, "holdings": holdings,
                  "others": [m for m in market_indexes() if m["ticker"] != t]})


CHART_RANGES = ("1m", "3m", "6m", "ytd", "1y", "3y", "5y", "max")


def price_series(ticker: str, range_: str = "ytd", start: str | None = None, end: str | None = None) -> dict:
    """Daily prices for the chart on a stock or index page: one of CHART_RANGES, or custom start/end dates."""
    from .analysis import resolve_period

    t = idx.get(ticker)["ticker"] if idx.get(ticker) else ticker_or_error(ticker)
    df = db().df("SELECT date, close, adj_close FROM prices WHERE ticker = ? AND date <= CAST(? AS DATE) ORDER BY date",
                 [t, last_day()])
    if df.empty:
        raise DataError(f"No prices for {t}.")
    df["date"] = pd.to_datetime(df["date"])
    df["sma50"] = df["adj_close"].rolling(50, min_periods=50).mean()
    df["sma200"] = df["adj_close"].rolling(200, min_periods=200).mean()
    spy = db().df("SELECT date, adj_close AS spy FROM prices WHERE ticker = 'SPY' ORDER BY date")
    spy["date"] = pd.to_datetime(spy["date"])
    df = df.merge(spy, on="date", how="left")
    key = (range_ or "ytd").lower()
    if not start and key not in CHART_RANGES:
        key = "ytd"
    days = pd.DatetimeIndex(df["date"])
    s, e, label = resolve_period(days, key, start or None, end or None)
    if not start and key == "ytd":
        # A year-to-date chart starts from the last close of the year before, the way YTD returns are counted.
        before = days[days < s]
        if len(before):
            s = before[-1]
    df = df[(df["date"] >= s) & (df["date"] <= e)].reset_index(drop=True)
    if len(df) > 1300:   # weekly points for long ranges
        keep = list(range(0, len(df), 5))
        if keep[-1] != len(df) - 1:
            keep.append(len(df) - 1)
        df = df.iloc[keep].reset_index(drop=True)
    first = df["spy"].dropna()
    base_spy = first.iloc[0] if len(first) else None
    base = df["adj_close"].iloc[0]
    df["spy_rebased"] = df["spy"] / base_spy * base if base_spy else None
    return {"ticker": t, "range": "custom" if start else key, "label": label,
            "start": str(df["date"].iloc[0].date()), "end": str(df["date"].iloc[-1].date()),
            "points": clean(df[["date", "close", "adj_close", "sma50", "sma200", "spy_rebased"]].to_dict(orient="records"))}


def week_movers(n: int = 5) -> dict:
    """The biggest gains and losses among current members over the last five trading days."""
    rows = db().rows("""
        WITH d AS (SELECT DISTINCT date FROM prices WHERE ticker = 'SPY' AND date <= CAST(? AS DATE)
                   ORDER BY date DESC LIMIT 6),
             b AS (SELECT max(date) AS hi, min(date) AS lo FROM d),
             w AS (SELECT p1.ticker, p1.adj_close / p0.adj_close - 1 AS ret_1w, b.lo AS since
                   FROM prices p1 JOIN prices p0 ON p0.ticker = p1.ticker CROSS JOIN b
                   WHERE p1.date = b.hi AND p0.date = b.lo)
        SELECT c.ticker, c.name, c.sector, c.market_cap, s.price, s.change_1d, s.ret_1m, s.ret_1y, w.ret_1w, w.since
        FROM w JOIN companies c USING (ticker) JOIN snapshot s USING (ticker)
        WHERE w.ret_1w IS NOT NULL ORDER BY w.ret_1w DESC""", [last_day()])
    spy = db().rows("""
        WITH d AS (SELECT date, adj_close FROM prices WHERE ticker = 'SPY' AND date <= CAST(? AS DATE)
                   ORDER BY date DESC LIMIT 6)
        SELECT arg_max(adj_close, date) / arg_min(adj_close, date) - 1 AS r FROM d""", [last_day()])
    return {"up": rows[:n], "down": rows[::-1][:n], "since": rows[0]["since"] if rows else None,
            "spy": spy[0]["r"] if spy else None}


def suggestions() -> dict:
    """Starting points for the Analyze tab: the big indexes, this week's biggest movers, and the largest
    companies. Sorted facts, not picks."""
    largest = db().rows("SELECT c.ticker, c.name, c.sector, c.market_cap, s.ret_1y FROM companies c "
                        "JOIN snapshot s USING (ticker) ORDER BY c.market_cap DESC NULLS LAST LIMIT 10")
    seen, one_each = set(), []   # one row per company (Alphabet has two share classes)
    for r in largest:
        key = r["name"].split(" (")[0]
        if key not in seen:
            seen.add(key)
            one_each.append(r)
    return {"indexes": [i for i in market_indexes() if i.get("available")], "movers": week_movers(4),
            "largest": one_each[:6], "as_of": db().meta().get("as_of")}


def _near(headlines: list[dict], day: str, before: int = 1, after: int = 3) -> list[dict]:
    """Headlines published around a date (a move's news usually lands the evening before or the days after)."""
    d = pd.Timestamp(day)
    lo, hi = d - pd.Timedelta(days=before), d + pd.Timedelta(days=after + 1)
    out = []
    for h in headlines:
        try:
            t = pd.Timestamp(h.get("published")).tz_localize(None)
        except (ValueError, TypeError):
            continue
        if lo <= t < hi:
            out.append({**h, "_gap": abs((t - d).total_seconds())})
    out.sort(key=lambda h: h["_gap"])
    return [{k: v for k, v in h.items() if k != "_gap"} for h in out]


def attach_headlines(moves: list[dict], by_ticker: dict[str, list[dict]], per_move: int = 2) -> None:
    for mv in moves:
        mv["headlines"] = _near(by_ticker.get(mv["ticker"], []), mv["date"])[:per_move]


def news_page() -> dict:
    moves = db().rows("""SELECT r.*, c.name, c.sector, s.ret_1m, s.ret_1y, s.dist_52w_high, s.vol_1y
                         FROM recent_moves r JOIN companies c USING (ticker) JOIN snapshot s USING (ticker)
                         ORDER BY r.date DESC, abs(r.excess_1d) DESC LIMIT 40""")
    for mv in moves:   # how many of the stock's ordinary days this one move was worth
        daily = (mv.get("vol_1y") or 0) / np.sqrt(252)
        mv["times_typical"] = abs(mv["ret_1d"]) / daily if daily and mv.get("ret_1d") is not None else None
    stored = db().rows("SELECT n.ticker, n.headline, n.summary, n.source, n.url, n.published, n.provider, c.name "
                       "FROM news n LEFT JOIN companies c USING (ticker) ORDER BY n.published DESC")
    by_ticker: dict[str, list[dict]] = {}
    for h in stored:
        by_ticker.setdefault(h["ticker"], []).append(h)
    attach_headlines(moves, by_ticker)
    events = db().rows("SELECT * FROM events ORDER BY event, horizon")
    sectors = db().rows("SELECT sector, etf, etf_ret_1w, etf_ret_1m, etf_ret_3m, etf_ret_1y, median_ret_1y, "
                        "pct_above_200d FROM sectors ORDER BY etf_ret_1m DESC NULLS LAST")
    leaders = db().rows(f"SELECT {ROW_COLS} FROM companies c JOIN snapshot s USING (ticker) "
                        "ORDER BY s.ret_1m DESC NULLS LAST LIMIT 6")
    laggards = db().rows(f"SELECT {ROW_COLS} FROM companies c JOIN snapshot s USING (ticker) "
                         "ORDER BY s.ret_1m ASC NULLS LAST LIMIT 6")
    m = db().meta()
    # Market-wide headlines first. If the snapshot has few, fill in with company ones (each headline once).
    seen, headlines = set(), []
    for h in [h for h in stored if h["ticker"] == "_market"] + [h for h in stored if h["ticker"] != "_market"]:
        key = (h.get("headline") or "").lower()[:90]
        if key and key not in seen:
            seen.add(key)
            headlines.append(h)
    return {"moves": moves, "events": events, "sectors": sectors, "leaders": leaders, "laggards": laggards,
            "week": week_movers(6), "headlines": headlines[:24], "market": m.get("market", {}),
            "as_of": m.get("as_of"), "built_at": m.get("built_at")}


def live_headlines(max_tickers: int = 12) -> dict:
    """Fresh headlines for the news page: the market, plus each stock in "Big moves lately" around the day it
    moved. Falls back to the headlines saved with the last data build when the live feed isn't available."""
    from datetime import datetime, timezone

    from . import config
    from .sources import SourceError, news

    page = news_page()
    if db().meta().get("synthetic"):
        return {"live": False, "provider": "demo snapshot", "market": page["headlines"][:18], "moves": {},
                "fetched_at": None}
    market, provider, live = [], "", False
    try:
        market = [{**h, "ticker": "_market"} for h in news.market_news()]
        provider, live = (market[0]["provider"] if market else ""), bool(market)
    except SourceError:
        pass
    moves: dict[str, list[dict]] = {}
    if config.FINNHUB_API_KEY:   # the keyless fallback is too slow to call once per stock
        seen: list[str] = []
        for mv in page["moves"]:
            if mv["ticker"] not in seen:
                seen.append(mv["ticker"])
        by_ticker = {}
        for t in seen[:max_tickers]:
            try:
                by_ticker[t] = news.company_news(t, days=35)
                live = True
            except SourceError:
                continue
        subset = [mv for mv in page["moves"] if mv["ticker"] in by_ticker]
        attach_headlines(subset, by_ticker)
        moves = {f"{mv['ticker']}|{mv['date']}": mv["headlines"] for mv in subset if mv["headlines"]}
    return {"live": live, "provider": provider or ("Finnhub" if live else "snapshot"),
            "market": market[:18] or page["headlines"][:18], "moves": moves,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds") if live else None}


def price_move(ticker: str, window: int = 30) -> dict:
    """The size and shape of a stock's (or index fund's) recent move: returns over several horizons next to the
    S&P 500 and its sector, how far it is below its highs, its biggest days in the window, and how unusual those
    days are for this stock. Fractions, not percents."""
    from .sources.prices import SECTOR_ETFS

    info = idx.get(ticker)
    t = info["ticker"] if info else ticker_or_error(ticker)
    comp = None if info else db().rows("SELECT name, sector FROM companies WHERE ticker = ?", [t])[0]
    etf = None if info else SECTOR_ETFS.get(comp["sector"])
    names = list(dict.fromkeys([t, "SPY"] + ([etf] if etf else [])))
    df = db().df(f"SELECT ticker, date, adj_close, volume FROM prices WHERE ticker IN ({','.join('?' * len(names))}) "
                 "AND date <= CAST(? AS DATE) ORDER BY date", [*names, last_day()])
    df["date"] = pd.to_datetime(df["date"])
    px = df.pivot(index="date", columns="ticker", values="adj_close")
    s = px[t].dropna()
    if len(s) < 40:
        raise DataError(f"Not enough price history for {t} to measure a move.")
    px = px.loc[s.index[0]:s.index[-1]].ffill()
    vol = df[df["ticker"] == t].set_index("date")["volume"].reindex(s.index)
    r = s.pct_change()
    spy_r = px["SPY"].reindex(s.index).pct_change()
    window = int(max(5, min(window or 30, 120)))
    w = s.iloc[-(window + 1):]
    end = s.index[-1]

    def ret(series: pd.Series, n: int | None = None, since: pd.Timestamp | None = None):
        x = series.dropna()
        if since is not None:
            base = x.loc[:since]
            return float(x.iloc[-1] / base.iloc[-1] - 1) if len(base) else None
        return float(x.iloc[-1] / x.iloc[-1 - n] - 1) if len(x) > n else None

    horizons = []
    for label, n, since in [("1 day", 1, None), ("1 week", 5, None), ("1 month", 21, None), ("3 months", 63, None),
                            ("this year", None, pd.Timestamp(end.year, 1, 1) - pd.Timedelta(days=1))]:
        row = {"period": label, "stock": ret(s, n, since)}
        if t != "SPY":
            row["sp500"] = ret(px["SPY"], n, since)
            row["vs_sp500"] = None if row["stock"] is None or row["sp500"] is None else row["stock"] - row["sp500"]
        if etf and etf in px.columns:
            row["sector_fund"] = ret(px[etf], n, since)
        horizons.append(row)

    # The yardstick for "unusual": the stock's ordinary daily move over the year before this window.
    before = r.iloc[:-window].iloc[-252:].dropna()
    typical = float(before.std()) if len(before) > 60 else float(r.dropna().std())
    avg_volume = vol.iloc[:-window].iloc[-63:].mean()
    hist = r.dropna()

    def day_row(d: pd.Timestamp) -> dict:
        x = float(r.at[d])
        worse = int((hist <= x).sum()) if x < 0 else int((hist >= x).sum())
        return {"date": str(d.date()), "return": x, "sp500_same_day": None if t == "SPY" or pd.isna(spy_r.at[d]) else float(spy_r.at[d]),
                "times_typical_day": abs(x) / typical if typical else None,
                "volume_vs_normal": float(vol.at[d] / avg_volume) if avg_volume and not pd.isna(vol.at[d]) else None,
                "days_this_extreme_in_history": worse, "history_days": int(len(hist))}

    rw = r.loc[w.index[1]:]
    worst = [day_row(d) for d in rw.nsmallest(3).index if rw.at[d] < 0]
    best = [day_row(d) for d in rw.nlargest(3).index if rw.at[d] > 0]

    year = s.iloc[-252:]
    high_day = year.idxmax()
    below_high = float(s.iloc[-1] / year.max() - 1)
    roll_high = s.rolling(252, min_periods=60).max()
    depth = (s / roll_high - 1).dropna()
    peak_day = w.idxmax()
    after_peak = w.loc[peak_day:]
    low_day = after_peak.idxmin()
    return clean({
        "ticker": t, "name": info["name"] if info else comp["name"], "kind": "index" if info else "stock",
        "sector": None if info else comp["sector"], "sector_fund": etf, "as_of": str(end.date()), "price": float(s.iloc[-1]),
        "window_days": window, "window_start": str(w.index[0].date()), "window_return": float(w.iloc[-1] / w.iloc[0] - 1),
        "returns": horizons,
        "from_52_week_high": {"below_high": below_high, "high_date": str(high_day.date()), "high_price": float(year.max()),
                              "trading_days_since": int(len(s.loc[high_day:]) - 1),
                              "share_of_history_this_far_below": float((depth <= below_high).mean()) if len(depth) else None},
        "in_window": {"peak_date": str(peak_day.date()), "low_date": str(low_day.date()),
                      "peak_to_low": float(after_peak.min() / w.max() - 1),
                      "peak_to_now": float(w.iloc[-1] / w.max() - 1),
                      "down_days": int((rw < 0).sum()), "up_days": int((rw > 0).sum())},
        "typical_daily_move": typical, "biggest_down_days": worst, "biggest_up_days": best,
        "history_start": str(s.index[0].date()),
    })


def meta_public() -> dict:
    m = db().meta()
    sectors = [r["sector"] for r in db().rows("SELECT DISTINCT sector FROM companies ORDER BY sector")]
    have = _index_tickers_with_prices()
    return {"as_of": m.get("as_of"), "built_at": m.get("built_at"), "provider": m.get("provider"),
            "synthetic": m.get("synthetic", False), "coverage": m.get("coverage", {}), "sectors": sectors,
            "sector_info": SECTOR_INFO, "signals": m.get("signals", []),
            "indexes": [{**i, "available": i["ticker"] in have} for i in idx.INDEXES]}
