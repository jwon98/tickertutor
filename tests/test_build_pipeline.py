"""The real-data build (fetch → compute → database), run against mocked APIs.

Every source is faked at the HTTP level with responses shaped like the real ones (Wikipedia's parse
API, Alpaca bars, SEC company facts and submissions), so this exercises the same code path John runs
with real keys, just with a small universe."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

import httpx
import numpy as np
import pandas as pd
import pytest

from tickertutor import config, data, sources
from tickertutor.build import compute, fetch
from tickertutor.sources import sec

from tests.test_sources import wiki_html

TODAY = date.today()


def bdays(start: date, end: date):
    return pd.bdate_range(start, end)


def bars_for(symbol: str, start: date, end: date, adjusted: bool):
    seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    days = bdays(date(2016, 1, 4), TODAY)
    steps = rng.normal(0.0004 + (seed % 7) * 0.00005, 0.012, len(days))
    price = 50 * np.exp(np.cumsum(steps))
    out = []
    for d, p in zip(days, price):
        if start <= d.date() <= end:
            c = p * (1 if adjusted else 1.02)
            out.append({"t": f"{d.date()}T05:00:00Z", "o": c, "h": c, "l": c, "c": round(float(c), 4), "v": 1_000_000})
    return out


def companyfacts_for(cik: int):
    def entry(fy, val, start=True):
        e = {"end": f"{fy}-12-31", "val": val, "fy": fy, "fp": "FY", "form": "10-K", "filed": f"{fy + 1}-02-15",
             "accn": f"000{cik}-{fy}"}
        if start:
            e["start"] = f"{fy}-01-01"
        return e
    years = range(2014, TODAY.year)
    rev = {fy: 1e9 * (1.06 ** (fy - 2014)) * (1 + cik % 5 / 10) for fy in years}
    usgaap = {
        "Revenues": {"units": {"USD": [entry(fy, rev[fy]) for fy in years]}},
        "NetIncomeLoss": {"units": {"USD": [entry(fy, rev[fy] * 0.12) for fy in years]}},
        "OperatingIncomeLoss": {"units": {"USD": [entry(fy, rev[fy] * 0.18) for fy in years]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [entry(fy, rev[fy] * 0.12 / 1e8) for fy in years]}},
        "StockholdersEquity": {"units": {"USD": [entry(fy, rev[fy] * 0.8, start=False) for fy in years]}},
        "LongTermDebt": {"units": {"USD": [entry(fy, rev[fy] * 0.3, start=False) for fy in years]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [entry(fy, rev[fy] * 0.15) for fy in years]}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [entry(fy, rev[fy] * 0.04) for fy in years]}},
        "CommonStockDividendsPerShareDeclared": {"units": {"USD/shares": [entry(fy, 1.0) for fy in years]}},
    }
    dei = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"end": f"{fy + 1}-01-31", "val": 1e8, "fy": fy, "fp": "FY", "form": "10-K", "filed": f"{fy + 1}-02-15"} for fy in years]}}}
    return {"cik": cik, "entityName": f"Company {cik}", "facts": {"us-gaap": usgaap, "dei": dei}}


def submissions_for(cik: int):
    forms, accns, dates, items, docs = [], [], [], [], []
    d = TODAY - timedelta(days=20)
    while d > date(2016, 6, 1):
        forms.append("8-K"); accns.append(f"0000{cik}-{d:%y%m%d}"); dates.append(d.isoformat())
        items.append("2.02,9.01"); docs.append("pr.htm")
        d -= timedelta(days=91)
    forms.append("10-K"); accns.append(f"0000{cik}-k"); dates.append(f"{TODAY.year}-02-15"); items.append(""); docs.append("k.htm")
    return {"cik": str(cik), "filings": {"recent": {"form": forms, "accessionNumber": accns, "filingDate": dates,
            "reportDate": dates, "items": items, "primaryDocument": docs}, "files": []}}


def handler(request: httpx.Request) -> httpx.Response:
    host, path, params = request.url.host, request.url.path, dict(request.url.params)
    if host == "en.wikipedia.org":
        return httpx.Response(200, json={"parse": {"text": wiki_html()}})
    if host == "data.alpaca.markets":
        start, end = date.fromisoformat(params["start"]), date.fromisoformat(params["end"])
        adjusted = params["adjustment"] == "all"
        return httpx.Response(200, json={"bars": {s: bars_for(s, start, end, adjusted) for s in params["symbols"].split(",")
                                                   if s != "GONE"}})
    if host == "www.sec.gov" and path.endswith("company_tickers.json"):
        return httpx.Response(200, json={"0": {"cik_str": 555, "ticker": "OLDCO", "title": "Old Co"}})
    if host == "data.sec.gov" and "companyfacts" in path:
        return httpx.Response(200, json=companyfacts_for(int(path.split("CIK")[1][:10])))
    if host == "data.sec.gov" and "submissions" in path:
        return httpx.Response(200, json=submissions_for(int(path.split("CIK")[1][:10])))
    return httpx.Response(404)


@pytest.fixture
def mocked_world(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ALPACA_API_KEY", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET", "s")
    monkeypatch.setattr(config, "FRED_API_KEY", "")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(sec.time, "sleep", lambda s: None)
    sources.set_client(httpx.Client(transport=httpx.MockTransport(handler)))
    yield tmp_path
    sources.set_client(None)


def test_real_build_pipeline_end_to_end(mocked_world):
    raw = fetch.fetch_raw(date(2016, 1, 1), provider="alpaca", limit=12)
    comp = raw["companies"]
    assert comp["current"].sum() == 12
    assert "OLDCO" in set(comp.loc[~comp["current"], "ticker"])          # a former member is kept for the backtest
    assert {"SPY", "XLK", "XLU"} <= set(raw["prices"]["ticker"])
    assert not raw["facts"].empty and not raw["filings"].empty

    tables = compute.compute(raw, progress=lambda m: None)
    path = compute.write_db(tables, mocked_world / "real.duckdb")
    previous = data._db.path if data._db is not None else None
    data.set_db(path)
    try:
        db = data.db()
        meta = db.meta()
        assert meta["synthetic"] is False and meta["provider"] == "alpaca"
        assert meta["coverage"]["with_prices"] == 12
        snap = db.rows("SELECT * FROM snapshot")
        assert len(snap) == 12
        assert all(r["pe"] is not None and r["pe"] > 0 for r in snap)
        assert all(r["profitable_years"] == 5 for r in snap)
        f = db.rows("SELECT * FROM fundamentals WHERE ticker = 'T000' ORDER BY fy_end")
        assert len(f) >= 5 and f[-1]["revenue"] > f[0]["revenue"]
        assert db.rows("SELECT count(*) AS n FROM earnings")[0]["n"] > 0     # 8-K 2.02 reactions were measured
        assert db.rows("SELECT count(*) AS n FROM signal_cards")[0]["n"] >= 16
        # Former member: in the panel while a member (2015-03 → 2023-06), not after.
        old = db.rows("SELECT min(date) AS a, max(date) AS b FROM panel WHERE ticker = 'OLDCO'")[0]
        assert old["a"] is not None and str(old["b"]) < "2023-06-30"
    finally:
        data.set_db(previous)


def test_refresh_reuses_members_and_sec_data_but_not_prices(mocked_world, monkeypatch):
    """The daily update downloads prices again and reuses the slow-changing inputs saved by the last full build."""
    first = fetch.fetch_raw(date(2016, 1, 1), provider="alpaca", limit=12)
    assert (config.CACHE_DIR / fetch.INPUTS_FILE).exists()
    monkeypatch.setattr(fetch, "slow_inputs", lambda *a, **k: pytest.fail("should reuse the saved inputs"))
    again = fetch.fetch_raw(date(2016, 1, 1), provider="alpaca", limit=12, refresh=True)
    assert again["companies"].equals(first["companies"]) and again["facts"].equals(first["facts"])
    assert len(again["prices"]) == len(first["prices"])
    assert fetch.load_inputs(date(2016, 1, 1), 99, True) is None                  # other settings: not reused
    assert fetch.load_inputs(date(2016, 1, 1), 12, True, max_age_days=0) is None  # too old: download again

    def blocked(*a, **k):
        raise sources.SourceError("en.wikipedia.org refused the request (HTTP 403).")

    monkeypatch.setattr(fetch, "slow_inputs", blocked)
    monkeypatch.setattr(fetch, "REUSE_DAYS", 0)
    monkeypatch.setattr(fetch.load_inputs, "__defaults__", (0,))
    fallback = fetch.fetch_raw(date(2016, 1, 1), provider="alpaca", limit=12, refresh=True)   # old inputs beat no update
    assert fallback["companies"].equals(first["companies"])
    with pytest.raises(sources.SourceError):
        fetch.fetch_raw(date(2016, 1, 1), provider="alpaca", limit=12)                         # a full build still fails loudly


def test_headlines_are_fetched_for_recent_movers_first():
    days = pd.bdate_range("2026-09-01", periods=40)
    rows = []
    for t, jump in [("SPY", 0.0), ("CALM", 0.0), ("JUMP", 0.09), ("DROP", -0.07)]:
        price = 100.0
        for i, d in enumerate(days):
            price *= 1 + (jump if i == 30 else 0.001)
            rows.append({"ticker": t, "date": d.date(), "adj_close": price})
    assert fetch.recent_movers(pd.DataFrame(rows), ["CALM", "JUMP", "DROP", "MISSING"]) == ["JUMP", "DROP"]
