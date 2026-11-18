"""Tools the Researcher agents use to get at the data.

Every tool result carries citation ids ("ref": "S4"). The Writer can only cite
those ids, and each one maps to a source: a table and query in the Ticker Tutor
database, an SEC filing, a news article, or a web page. That's how the report's
citations stay accurate.

Errors come back as {"ok": false, "error", "hint"} so the agent can fix its call
or say the data can't answer.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

from . import analysis as analysis_mod
from . import indexes as index_mod
from . import llm, views
from .data import SCHEMA, DataError, clean, db, find_company, run_sql, ticker_or_error
from .sources import SourceError, news, sec

log = logging.getLogger("tickertutor.tools")


class ToolError(Exception):
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


@dataclass
class Sources:
    """Thread-safe registry of everything the agents looked at (the citation list)."""
    items: dict[str, dict] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, kind: str, title: str, url: str = "", detail: str = "") -> str:
        with self._lock:
            for ref, it in self.items.items():   # same source twice → same id
                if it["title"] == title and it["url"] == url and it["detail"] == detail:
                    return ref
            ref = f"S{len(self.items) + 1}"
            self.items[ref] = {"ref": ref, "kind": kind, "title": title, "url": url, "detail": detail}
            return ref

    def get(self, ref: str) -> dict | None:
        return self.items.get(ref)


def _as_of() -> str:
    return db().meta().get("as_of", "")


def _db_ref(src: Sources, table: str, detail: str) -> str:
    synthetic = " (synthetic demo data)" if db().meta().get("synthetic") else ""
    return src.add("data", f"Ticker Tutor database: {table}, as of {_as_of()}{synthetic}", "", detail)


PCT_FIELDS = {"change_1d", "ret_1m", "ret_3m", "ret_6m", "ret_1y", "ret_3y_ann", "ret_5y_ann", "ret_ytd", "spy_ret_1y",
              "dist_52w_high", "vol_1y", "max_drawdown", "current_drawdown", "pct_up_1y", "best_1y", "worst_1y",
              "median_1y", "spy_pct_up_1y", "spy_median_1y", "spy_worst_1y", "dividend_yield", "revenue_growth",
              "op_margin", "net_margin", "roe", "earnings_yield", "mom_12_1", "rel_sector_6m"}


def _pretty(row: dict) -> dict:
    """Round numbers so the model reads them easily (percent fields as %)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, float):
            out[k] = f"{v * 100:.1f}%" if k in PCT_FIELDS else (round(v, 2) if abs(v) < 1e6 else f"{v / 1e9:.1f}B")
        else:
            out[k] = v
    return out


# --- market data -----------------------------------------------------------------------------------------

SORT_CHOICES = list(views.SORTS)


def screen_stocks(ctx, sector: str = "", sort_by: str = "market_cap", limit: int = 10) -> dict:
    if sector:
        sectors = [r["sector"] for r in db().rows("SELECT DISTINCT sector FROM companies")]
        match = next((s for s in sectors if s.lower() == sector.lower() or sector.lower() in s.lower()), None)
        if not match:
            raise ToolError(f"Unknown sector '{sector}'.", "Use one of: " + ", ".join(sorted(sectors)))
        sector = match
    if sort_by not in views.SORTS:
        raise ToolError(f"Unknown sort '{sort_by}'.", "Use one of: " + ", ".join(SORT_CHOICES))
    rows = views.screener(sector, sort_by, "", max(1, min(limit, 25)))
    keep = ["ticker", "name", "sector", "market_cap", "price", "ret_1m", "ret_ytd", "ret_1y", "pe", "dividend_yield",
            "vol_1y", "beta_1y", "dist_52w_high", "rsi14"]
    ref = _db_ref(ctx.sources, "companies + snapshot (list)", f"screen_stocks(sector={sector or 'any'}, sort_by={sort_by})")
    return {"ok": True, "ref": ref, "as_of": _as_of(), "stocks": [_pretty({k: r.get(k) for k in keep}) for r in rows],
            "note": "A sorted list of facts, not a ranking of which stocks are good."}


def get_stock_snapshot(ctx, ticker: str) -> dict:
    t = ticker_or_error(ticker)
    s = views.stock(t)
    snap, comp = s["snapshot"], s["company"]
    keep = ["price", "change_1d", "ret_1m", "ret_ytd", "ret_1y", "ret_3y_ann", "ret_5y_ann", "spy_ret_1y", "above_200d",
            "golden_cross", "sma50", "sma200", "rsi14", "mom_12_1", "dist_52w_high", "vol_1y", "beta_1y",
            "rel_sector_6m", "max_drawdown", "current_drawdown", "pe", "pe_med5", "earnings_yield", "dividend_yield",
            "dividend_years", "revenue_growth", "op_margin", "debt_to_equity", "profitable_years", "market_cap"]
    ref = _db_ref(ctx.sources, "snapshot", f"get_stock_snapshot({t})")
    return {"ok": True, "ref": ref, "as_of": snap["as_of"], "ticker": t, "name": comp["name"], "sector": comp["sector"],
            "member_since": comp.get("member_since"), "snapshot": _pretty({k: snap.get(k) for k in keep}),
            "returns_vs_index": [_pretty(r) | {"label": r["label"]} for r in s["returns"]]}


def run_analysis(ctx, ticker: str, analysis_id: str, period: str = "1y", start: str = "", end: str = "",
                 params: dict | None = None) -> dict:
    idx = index_mod.get(ticker)
    t = idx["ticker"] if idx else ticker_or_error(ticker)
    try:
        out = analysis_mod.run(t, analysis_id, period or "1y", start or None, end or None, params or {})
    except DataError as exc:
        raise ToolError(str(exc), "Analyses: " + ", ".join(analysis_mod.ANALYSES)) from exc
    a, per = out["analysis"], out["period"]
    synthetic = " (synthetic demo data)" if db().meta().get("synthetic") else ""
    settings = ", ".join(f"{p['label']} {p['value']}" for p in out["params"])
    subject = f"{t} ({idx['name']} fund)" if idx else t
    ref = ctx.sources.add("data", f"Ticker Tutor analysis: {a['name']} for {subject}, {per['start']} to {per['end']}{synthetic}", "",
                          f"run_analysis({t}, {analysis_id}, {per['start']}..{per['end']}{', ' + settings if settings else ''}) "
                          "on daily adjusted prices")
    return {"ok": True, "ref": ref, "ticker": t, "analysis": a["name"], "period": per, "settings": settings,
            "summary": [{"label": x["label"], "value": x["text"], **({"note": x["note"]} if x["note"] else {})}
                        for x in out["summary"]],
            "readout": out["readout"], "how_to_read": a["explain"]["read"], "watch_out": a["explain"]["watch"],
            "chart_link": f"#/analyze?t={t}&a={analysis_id}&p={per['key'] or ''}"
                          + (f"&start={per['start']}&end={per['end']}" if not per["key"] else "")}


def _p(v, signed: bool = True) -> str | None:
    return None if v is None else f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"


def get_price_move(ctx, ticker: str, days: int = 30) -> dict:
    """How big a recent move was, and how unusual it is for this stock."""
    try:
        m = views.price_move(ticker, days or 30)
    except DataError as exc:
        raise ToolError(str(exc)) from exc
    t = m["ticker"]
    synthetic = " (synthetic demo data)" if db().meta().get("synthetic") else ""
    ref = ctx.sources.add("data", f"Ticker Tutor price-move summary for {t}, {m['window_start']} to {m['as_of']}{synthetic}", "",
                          f"get_price_move({t}, days={m['window_days']}) on daily adjusted prices")

    def day(d: dict) -> dict:
        return {"date": d["date"], "return": _p(d["return"]), "sp500_same_day": _p(d["sp500_same_day"]),
                "times_its_typical_day": None if d["times_typical_day"] is None else round(d["times_typical_day"], 1),
                "volume_vs_normal": None if d["volume_vs_normal"] is None else f"{d['volume_vs_normal']:.1f}x",
                "how_rare": f"{d['days_this_extreme_in_history']} of {d['history_days']} trading days since "
                            f"{m['history_start']} were this extreme or more"}

    hi, win = m["from_52_week_high"], m["in_window"]
    return {
        "ok": True, "ref": ref, "ticker": t, "name": m["name"], "as_of": m["as_of"], "price": round(m["price"], 2),
        "returns": [{k: (v if k == "period" else _p(v)) for k, v in r.items()} for r in m["returns"]],
        "window": {"trading_days": m["window_days"], "from": m["window_start"], "return": _p(m["window_return"]),
                   "peak_date": win["peak_date"], "low_date": win["low_date"], "peak_to_low": _p(win["peak_to_low"]),
                   "peak_to_now": _p(win["peak_to_now"]), "down_days": win["down_days"], "up_days": win["up_days"]},
        "from_52_week_high": {"below_high": _p(hi["below_high"]), "high_date": hi["high_date"],
                              "trading_days_since_high": hi["trading_days_since"],
                              "share_of_its_history_this_far_below_a_high": _p(hi["share_of_history_this_far_below"], False)},
        "typical_daily_move": _p(m["typical_daily_move"], False),
        "biggest_down_days": [day(d) for d in m["biggest_down_days"]],
        "biggest_up_days": [day(d) for d in m["biggest_up_days"]],
        "how_to_read": "vs_sp500 is the stock's return minus the S&P 500's, so it strips out what the whole market did. "
                       "times_its_typical_day compares one day's move with the stock's ordinary daily move over the year "
                       "before: 1 is a normal day, 3 or more is rare. These numbers measure the move. They don't say why "
                       "it happened (check the news tools for that) or what comes next.",
        "pages": {"In the news": "#/news", f"{t} daily returns (how unusual a day is)": f"#/analyze?t={t}&a=returns_distribution&p=1y",
                  f"{t} drawdowns": f"#/analyze?t={t}&a=drawdown&p=1y",
                  f"{t} vs the S&P 500": f"#/analyze?t={t}&a=relative&p=3m"},
    }


SIGNAL_IDS = ["above_200d", "golden_cross", "momentum_top30", "near_52w_high", "rsi_oversold", "big_dip",
              "strong_vs_sector", "low_volatility", "profitable_5y", "high_margin", "low_debt", "revenue_growth_10",
              "cheap_vs_history", "cheap_vs_market", "dividend_5y"]


def get_signal_track_record(ctx, signal_id: str, sector: str = "") -> dict:
    if signal_id not in SIGNAL_IDS:
        raise ToolError(f"Unknown signal '{signal_id}'.", "Use one of: " + ", ".join(SIGNAL_IDS))
    rows = db().rows("SELECT * FROM signal_cards WHERE signal_id = ? AND (universe = 'All' OR lower(universe) = ?)",
                     [signal_id, sector.lower()])
    if not rows:
        raise ToolError("No track record stored for that signal.")
    ref = _db_ref(ctx.sources, "signal_cards (backtest)", f"get_signal_track_record({signal_id}, sector={sector or 'All'})")
    keep = ["universe", "label", "n_months", "period_start", "period_end", "hit_on", "hit_off", "excess_on", "excess_off",
            "diff", "diff_lo", "diff_hi", "is_diff", "oos_diff", "oos_start", "verdict"]
    out = []
    for r in rows:
        x = {k: r.get(k) for k in keep}
        for k in ("hit_on", "hit_off", "excess_on", "excess_off", "diff", "diff_lo", "diff_hi", "is_diff", "oos_diff"):
            if isinstance(x.get(k), float):
                x[k] = f"{x[k] * 100:.1f}%"
        out.append(x)
    return {"ok": True, "ref": ref, "signal_id": signal_id, "results": out,
            "how_to_read": "hit_on/hit_off = share of stocks that beat the S&P 500 over the next 12 months when the "
                           "signal was on/off; diff = average extra 12-month return of 'on' minus 'off' with a 95% "
                           "interval (diff_lo..diff_hi); oos_diff = the same in the held-out recent period. Verdicts: "
                           "held_up, worse, mixed, no_clear_edge, too_little_data."}


def compare_stocks(ctx, tickers: list[str]) -> dict:
    ts = [ticker_or_error(t) for t in (tickers or [])][:6]
    if len(ts) < 2:
        raise ToolError("Give at least two tickers to compare.")
    ph = ",".join("?" * len(ts))
    rows = db().rows(f"SELECT c.ticker, c.name, c.sector, c.market_cap, s.price, s.ret_1y, s.ret_5y_ann, s.pe, s.pe_med5, "
                     f"s.dividend_yield, s.revenue_growth, s.op_margin, s.debt_to_equity, s.vol_1y, s.beta_1y, "
                     f"s.max_drawdown FROM companies c JOIN snapshot s USING (ticker) WHERE c.ticker IN ({ph})", ts)
    ref = _db_ref(ctx.sources, "companies + snapshot", f"compare_stocks({', '.join(ts)})")
    return {"ok": True, "ref": ref, "stocks": [_pretty(r) for r in rows]}


def query_database(ctx, sql: str) -> dict:
    try:
        res = run_sql(sql)
    except DataError as exc:
        raise ToolError(str(exc), "Check the schema in this tool's description; tables: " + ", ".join(SCHEMA)) from exc
    ref = _db_ref(ctx.sources, "SQL query", sql.strip()[:500])
    return {"ok": True, "ref": ref, **res}


# --- fundamentals ------------------------------------------------------------------------------------------

def get_fundamentals(ctx, ticker: str) -> dict:
    t = ticker_or_error(ticker)
    rows = db().rows("SELECT * FROM fundamentals WHERE ticker = ? ORDER BY fy_end DESC LIMIT 6", [t])
    snap = db().rows("SELECT * FROM snapshot WHERE ticker = ?", [t])[0]
    if not rows and snap.get("revenue_ttm") is None:
        raise ToolError(f"No SEC fundamentals stored for {t}.", "The data can't answer fundamentals questions for it.")
    years = []
    for r in rows:
        rev = r.get("revenue")
        years.append(_pretty({"fiscal_year_end": r["fy_end"], "filed": r["filed"], "revenue": rev,
                              "net_income": r.get("net_income"), "eps_diluted": r.get("eps_diluted"),
                              "operating_margin": (r["operating_income"] / rev) if rev and r.get("operating_income") is not None else None,
                              "long_term_debt": r.get("long_term_debt"), "equity": r.get("equity"),
                              "free_cash_flow": (r["operating_cash_flow"] - r["capex"]) if r.get("operating_cash_flow") is not None and r.get("capex") is not None else None,
                              "dividends_per_share": r.get("dividends_per_share")}))
    ttm_keep = ["revenue_ttm", "revenue_basis", "net_income_ttm", "eps_ttm", "eps_basis", "fcf_ttm", "dividend_ps_ttm",
                "dividend_yield", "pe", "pe_med5", "revenue_growth", "op_margin", "net_margin", "debt_to_equity", "roe",
                "profitable_years", "dividend_years"]
    filing = db().rows("SELECT url, filed FROM filings WHERE ticker = ? AND form = '10-K' ORDER BY filed DESC LIMIT 1", [t])
    ref = ctx.sources.add("filing" if filing and not db().meta().get("synthetic") else "data",
                          f"{t} annual reports (SEC XBRL financial data)" + (" (synthetic demo data)" if db().meta().get("synthetic") else ""),
                          filing[0]["url"] if filing and not db().meta().get("synthetic") else "", f"get_fundamentals({t})")
    return {"ok": True, "ref": ref, "ticker": t, "annual": years, "latest": _pretty({k: snap.get(k) for k in ttm_keep}),
            "note": "Annual values are as first reported. P/E uses trailing-twelve-month EPS."}


def get_annual_report_risks(ctx, ticker: str, compare_previous: bool = True) -> dict:
    t = ticker_or_error(ticker)
    if db().meta().get("synthetic"):
        raise ToolError("Filing text isn't available with the synthetic demo data.",
                        "Say the data can't answer this in demo mode.")
    docs = db().rows("SELECT url, filed FROM filings WHERE ticker = ? AND form = '10-K' ORDER BY filed DESC LIMIT 2", [t])
    if not docs:
        raise ToolError(f"No 10-K filings stored for {t}.")
    try:
        new_text = sec.section(sec.filing_text(docs[0]["url"]), "risk_factors")
    except SourceError as exc:
        raise ToolError(f"Couldn't read the latest 10-K: {exc}") from exc
    if len(new_text) < 500:
        raise ToolError("Couldn't find the Risk Factors section in the latest 10-K.", "The filing layout may be unusual.")
    ref_new = ctx.sources.add("filing", f"{t} 10-K filed {docs[0]['filed']}: Item 1A Risk Factors", docs[0]["url"])
    new_titles = sec.risk_titles(new_text)
    out = {"ok": True, "ticker": t, "latest": {"ref": ref_new, "filed": docs[0]["filed"], "risk_count": len(new_titles),
                                                "first_risks": new_titles[:12]}}
    if compare_previous and len(docs) > 1:
        try:
            old_text = sec.section(sec.filing_text(docs[1]["url"]), "risk_factors")
            ref_old = ctx.sources.add("filing", f"{t} 10-K filed {docs[1]['filed']}: Item 1A Risk Factors", docs[1]["url"])
            diff = sec.compare_lists(new_titles, sec.risk_titles(old_text))
            out["previous"] = {"ref": ref_old, "filed": docs[1]["filed"]}
            out["new_this_year"] = diff["added"][:12]
            out["dropped_this_year"] = diff["removed"][:8]
        except SourceError as exc:
            out["previous_error"] = str(exc)
    return out


# --- news and events -----------------------------------------------------------------------------------------

def get_company_news(ctx, ticker: str, days: int = 14) -> dict:
    t = ticker_or_error(ticker)
    name = db().rows("SELECT name FROM companies WHERE ticker = ?", [t])[0]["name"]
    items, provider = [], ""
    try:
        items = news.company_news(t, name, days)
        provider = items[0]["provider"] if items else ""
    except SourceError as exc:
        log.info("live news failed for %s: %s", t, exc)
    if not items:
        items = db().rows("SELECT headline, summary, source, url, published, provider FROM news WHERE ticker = ? "
                          "ORDER BY published DESC LIMIT 10", [t])
        provider = "snapshot"
    if not items:
        return {"ok": True, "ticker": t, "provider": "", "articles": [],
                "note": f"No news about {t} in the last {days} days from the live feed or the snapshot. Say so; don't guess."}
    out = []
    for it in items[:10]:
        ref = ctx.sources.add("news", f"{it.get('source') or it.get('provider')}: {it['headline'][:140]}", it.get("url", ""),
                              it.get("published", ""))
        out.append({"ref": ref, "headline": it["headline"], "summary": (it.get("summary") or "")[:300],
                    "source": it.get("source"), "published": it.get("published")})
    return {"ok": True, "ticker": t, "provider": provider, "articles": out}


def get_market_news(ctx) -> dict:
    items = []
    try:
        items = news.market_news()
    except SourceError as exc:
        log.info("live market news failed: %s", exc)
    if not items:
        items = db().rows("SELECT headline, summary, source, url, published, provider FROM news WHERE ticker = '_market' "
                          "ORDER BY published DESC LIMIT 15")
    if not items:
        raise ToolError("No market news available right now.")
    out = []
    for it in items[:12]:
        ref = ctx.sources.add("news", f"{it.get('source') or it.get('provider')}: {it['headline'][:140]}", it.get("url", ""),
                              it.get("published", ""))
        out.append({"ref": ref, "headline": it["headline"], "summary": (it.get("summary") or "")[:240],
                    "published": it.get("published")})
    return {"ok": True, "articles": out}


def get_recent_moves(ctx, ticker: str = "") -> dict:
    """Big recent moves, earnings reactions, and what usually followed similar events."""
    params, where = [], ""
    if ticker:
        t = ticker_or_error(ticker)
        where, params = "WHERE ticker = ?", [t]
    moves = db().rows(f"SELECT * FROM recent_moves {where} ORDER BY date DESC LIMIT 15", params)
    events = db().rows("SELECT event, label, horizon, n, mean, mean_lo, mean_hi, pct_positive FROM events")
    earn = db().rows("SELECT date, reaction, excess_next_3m, excess_next_12m, url FROM earnings WHERE ticker = ? "
                     "ORDER BY date DESC LIMIT 6", params) if ticker else []
    sectors = db().rows("SELECT sector, etf_ret_1w, etf_ret_1m, etf_ret_3m FROM sectors ORDER BY etf_ret_1m DESC") if not ticker else []
    ref = _db_ref(ctx.sources, "recent_moves + events + earnings (event study)", f"get_recent_moves({ticker or 'all'})")
    return {"ok": True, "ref": ref, "recent_big_moves": [_pretty(m) for m in moves],
            "base_rates_after_events": [_pretty(e) for e in events], "earnings_reactions": [_pretty(e) for e in earn],
            "sector_trends": [_pretty(s) for s in sectors],
            "note": "excess = return minus the S&P 500. Base rates describe what happened after similar events across "
                    "the index; they are not forecasts."}


def get_recent_filings(ctx, ticker: str) -> dict:
    t = ticker_or_error(ticker)
    rows = db().rows("SELECT form, filed, item_names, url FROM filings WHERE ticker = ? ORDER BY filed DESC LIMIT 10", [t])
    if not rows:
        raise ToolError(f"No filings stored for {t}.")
    synthetic = db().meta().get("synthetic")
    out = []
    for r in rows:
        ref = ctx.sources.add("filing" if not synthetic else "data",
                              f"{t} {r['form']} filed {r['filed']}" + (f" ({r['item_names']})" if r.get("item_names") else "")
                              + (" (synthetic demo data)" if synthetic else ""), r["url"] if not synthetic else "")
        out.append({"ref": ref, **r})
    return {"ok": True, "ticker": t, "filings": out}


def web_search(ctx, query: str) -> dict:
    try:
        text, srcs = llm.grounded_answer(
            f"{query}\n\nAnswer in 3–5 factual sentences with dates. This is for an educational stock research tool; "
            "describe what happened and why, don't recommend buying or selling.")
    except llm.LLMError as exc:
        raise ToolError(f"Web search failed: {exc}") from exc
    refs = [ctx.sources.add("web", s.get("title") or "Web source", s.get("url", "")) for s in srcs]
    return {"ok": True, "answer": text, "refs": refs,
            "note": "Cite these refs for facts from this answer." if refs else "No web sources were returned; treat as unverified."}


def find_ticker(ctx, name: str) -> dict:
    funds = [{"ticker": i["ticker"], "name": f"{i['name']} (index fund)", "sector": "Index fund"}
             for i in index_mod.find(name)]
    found = funds + find_company(name)
    if not found:
        raise ToolError(f"No S&P 500 company or index matches '{name}'.",
                        "Ticker Tutor covers current S&P 500 members and four index funds: SPY, QQQ, DIA, IWM.")
    return {"ok": True, "matches": found[:6]}


# --- registry ---------------------------------------------------------------------------------------------------

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


TICKER = {"type": "string", "description": "Ticker symbol, e.g. AAPL or BRK.B"}
SQL_DESC = ("Run one read-only SQL SELECT (DuckDB dialect) on the Ticker Tutor database; max 200 rows. Tables:\n"
            + "\n".join(f"- {k}: {v}" for k, v in SCHEMA.items()))

TOOLS = {t.name: t for t in [
    Tool("screen_stocks", "List S&P 500 stocks sorted by a fact (company value, returns, P/E, dividend yield, "
         "volatility, beta, distance from 52-week high), optionally within one sector. A sorted list, not a ranking "
         "of quality.",
         _obj({"sector": {"type": "string"}, "sort_by": {"type": "string", "enum": list(views.SORTS)},
               "limit": {"type": "integer"}}), screen_stocks),
    Tool("get_stock_snapshot", "Latest price, returns vs the S&P 500 and sector, trend and momentum readings, "
         "valuation, and risk numbers for one stock.", _obj({"ticker": TICKER}, ["ticker"]), get_stock_snapshot),
    Tool("run_analysis", "Run one of Ticker Tutor's analyses on a stock, or on a big index through the fund that tracks it "
         "(SPY = S&P 500, QQQ = Nasdaq-100, DIA = Dow Jones Industrial Average, IWM = Russell 2000), over a period, "
         "exactly as the Analyze page does. For an index fund, 'relative' compares it with the other three indexes. "
         "Returns summary numbers, a plain-language readout, and how to interpret it. Analyses: "
         + "; ".join(f"{k} ({a['name']})" for k, a in analysis_mod.ANALYSES.items())
         + ". Periods: 1m, 3m, 6m, ytd, 1y, 3y, 5y, max, or start/end dates (YYYY-MM-DD). Optional params, e.g. "
           "{\"window\": 21} for volatility or {\"short\": 20, \"long\": 100} for moving averages.",
         _obj({"ticker": TICKER, "analysis_id": {"type": "string", "enum": list(analysis_mod.ANALYSES)},
               "period": {"type": "string", "enum": list(analysis_mod.PERIODS)},
               "start": {"type": "string"}, "end": {"type": "string"},
               "params": {"type": "object", "description": "Optional settings; defaults are the standard ones."}},
              ["ticker", "analysis_id"]), run_analysis),
    Tool("get_price_move", "Measure a stock's (or index fund's) recent move: returns over 1 day, 1 week, 1 month, "
         "3 months, and this year next to the S&P 500 and its sector fund; how far it is below its 52-week high; its "
         "biggest up and down days in the last N trading days, each with the S&P 500's move that day, how many times "
         "the stock's typical daily move it was, volume vs normal, and how rarely a day that extreme has happened in "
         "its history. Use it whenever the question is about a stock being up or down, or why it moved.",
         _obj({"ticker": TICKER, "days": {"type": "integer", "description": "trading days to look back, 5–120, default 30"}},
              ["ticker"]), get_price_move),
    Tool("get_signal_track_record", "Backtested track record of a signal: did S&P 500 stocks with it beat the index over "
         "the next 12 months more often than stocks without it? Includes a 95% interval and a held-out recent period. "
         "Signals: " + ", ".join(SIGNAL_IDS),
         _obj({"signal_id": {"type": "string", "enum": SIGNAL_IDS}, "sector": {"type": "string"}}, ["signal_id"]),
         get_signal_track_record),
    Tool("compare_stocks", "Side-by-side key numbers for 2–6 stocks.",
         _obj({"tickers": {"type": "array", "items": {"type": "string"}}}, ["tickers"]), compare_stocks),
    Tool("query_database", SQL_DESC, _obj({"sql": {"type": "string"}}, ["sql"]), query_database),
    Tool("get_fundamentals", "Annual revenue, profit, margins, debt, free cash flow, and dividends from SEC filings, plus "
         "trailing-twelve-month figures and P/E vs its own 5-year median.", _obj({"ticker": TICKER}, ["ticker"]),
         get_fundamentals),
    Tool("get_annual_report_risks", "Reads the Risk Factors section of the company's latest 10-K from SEC EDGAR and "
         "lists the risk headings, plus which ones are new or dropped vs the previous year's 10-K.",
         _obj({"ticker": TICKER, "compare_previous": {"type": "boolean"}}, ["ticker"]), get_annual_report_risks),
    Tool("get_company_news", "Recent news headlines for one company (live), with links and publish dates. To explain a "
         "move, match headline dates to the dates of the biggest days from get_price_move.",
         _obj({"ticker": TICKER, "days": {"type": "integer", "description": "1–60, default 14"}}, ["ticker"]),
         get_company_news),
    Tool("get_market_news", "Recent general market news headlines (live), with links.", _obj({}), get_market_news),
    Tool("get_recent_moves", "Big one-day moves in the last ~30 trading days (for one stock or all), earnings-day "
         "reactions, sector fund trends, and base rates for what followed similar events historically.",
         _obj({"ticker": TICKER}), get_recent_moves),
    Tool("get_recent_filings", "Recent SEC filings for a company (10-K, 10-Q, 8-K with what each 8-K was about).",
         _obj({"ticker": TICKER}, ["ticker"]), get_recent_filings),
    Tool("web_search", "Google-grounded web search for recent context (why something moved, what a company announced). "
         "Returns a short answer with source refs.", _obj({"query": {"type": "string"}}, ["query"]), web_search),
    Tool("find_ticker", "Look up the ticker for a company name among S&P 500 members, or the fund for an index "
         "(e.g. 'Nasdaq' → QQQ).",
         _obj({"name": {"type": "string"}}, ["name"]), find_ticker),
]}

ROLE_TOOLS = {
    "market": ["run_analysis", "get_price_move", "get_stock_snapshot", "get_signal_track_record", "compare_stocks", "screen_stocks",
               "query_database", "find_ticker"],
    "fundamentals": ["get_fundamentals", "get_annual_report_risks", "get_stock_snapshot", "query_database", "find_ticker"],
    "news": ["get_company_news", "get_market_news", "get_recent_moves", "get_price_move", "get_recent_filings", "web_search",
             "find_ticker"],
}


def run_tool(ctx, name: str, args: dict) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        return {"ok": False, "error": f"Unknown tool {name}."}
    try:
        return clean(tool.fn(ctx, **(args or {})))
    except ToolError as exc:
        return {"ok": False, "error": str(exc), **({"hint": exc.hint} if exc.hint else {})}
    except DataError as exc:
        return {"ok": False, "error": str(exc), "hint": "If the data doesn't cover this, say so in your findings."}
    except TypeError as exc:
        return {"ok": False, "error": f"Bad arguments for {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        log.exception("tool %s failed", name)
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def preview(result: dict, limit: int = 1500) -> dict:
    """A shortened copy of a tool result for the /chat tool_calls list."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return result
    short = {k: v for k, v in result.items() if not isinstance(v, (list, dict))}
    for k, v in result.items():
        if isinstance(v, list):
            short[k] = v[:3] + ([f"… {len(v) - 3} more"] if len(v) > 3 else [])
        elif isinstance(v, dict):
            short[k] = {kk: vv for i, (kk, vv) in enumerate(v.items()) if i < 12}
    return short
