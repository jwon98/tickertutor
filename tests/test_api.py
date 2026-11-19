"""HTTP API: pages' data endpoints and the /chat contract the course requires."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(demo_db):
    import app as app_module
    app_module._hits.clear()
    return TestClient(app_module.app)


def test_index_and_health(client):
    r = client.get("/")
    assert r.status_code == 200 and "Ticker Tutor" in r.text
    assert client.get("/healthz").json()["ok"] is True


def test_meta_says_what_the_data_is(client):
    m = client.get("/api/meta").json()
    assert m["synthetic"] is True and m["as_of"] and len(m["sectors"]) == 11
    assert "not financial advice" in m["disclaimer"]


def test_overview_and_screener(client):
    o = client.get("/api/overview").json()
    assert o["n"] == 66 and len(o["sectors"]) == 11 and all(s["about"] for s in o["sectors"])
    assert {e["analysis"] for e in o["examples"]} == {"moving_averages", "volatility", "beta", "drawdown"}
    assert "picks" not in o
    s = client.get("/api/stocks?sector=Energy&sort=ret_1y").json()["stocks"]
    assert s and {x["sector"] for x in s} == {"Energy"}
    rets = [x["ret_1y"] for x in s]
    assert rets == sorted(rets, reverse=True)
    q = client.get("/api/stocks?q=coca").json()["stocks"]
    assert [x["ticker"] for x in q] == ["KO"]
    tk = client.get("/api/tickers").json()["tickers"]
    assert len(tk) == 70 and [t["ticker"] for t in tk[:4]] == ["SPY", "QQQ", "DIA", "IWM"]
    assert {t["kind"] for t in tk[:4]} == {"index"} and {t["kind"] for t in tk[4:]} == {"stock"}
    assert [i["ticker"] for i in o["indexes"]] == ["SPY", "QQQ", "DIA", "IWM"] and all(i["available"] for i in o["indexes"])


def test_market_indexes(client):
    ix = client.get("/api/indexes").json()["indexes"]
    assert [i["id"] for i in ix] == ["sp500", "nasdaq100", "dow", "russell2000"]
    for i in ix:
        assert i["available"] and len(i["spark"]) >= 50
        assert all(isinstance(i[k], float) for k in ("change_1d", "ret_1m", "ret_ytd", "ret_1y", "vol_1y"))
    meta = client.get("/api/meta").json()
    assert [i["ticker"] for i in meta["indexes"]] == ["SPY", "QQQ", "DIA", "IWM"] and all(i["about"] for i in meta["indexes"])
    assert {i["as_of"] for i in ix} == {meta["as_of"]}   # every index describes the same day as the rest of the app


def test_index_pages(client):
    spy = client.get("/api/indexes/SPY").json()
    assert spy["index"]["name"] == "S&P 500" and spy["snapshot"]["beta_1y"] is None
    assert [r["ticker"] for r in spy["returns"]] == ["SPY", "QQQ", "DIA", "IWM"] and spy["returns"][0]["me"]
    assert len(spy["returns"][0]["values"]) == len(spy["periods"]) == 6
    assert len(spy["holdings"]["top"]) == 10 and 0 < spy["holdings"]["top_share"] < 1
    assert spy["snapshot"]["max_drawdown"] < 0 and spy["snapshot"]["dd_peak"] < spy["snapshot"]["dd_trough"]
    qqq = client.get("/api/indexes/qqq").json()
    assert qqq["holdings"] is None and qqq["snapshot"]["beta_1y"] > 0 and qqq["returns"][0]["ticker"] == "QQQ"
    assert [o["ticker"] for o in qqq["others"]] == ["SPY", "DIA", "IWM"]
    assert client.get("/api/indexes/KO").status_code == 404
    assert len(client.get("/api/stocks/QQQ/prices?range=1y").json()["points"]) > 200
    fonts = client.get("/static/fonts/instrument-sans.woff2")
    assert fonts.status_code == 200 and "immutable" in fonts.headers["cache-control"]


def test_analyses_run_on_index_funds(client):
    for t in ["SPY", "qqq", "DIA", "IWM"]:
        for aid in ["moving_averages", "volatility", "drawdown", "relative", "rolling_returns", "returns_distribution"]:
            r = client.get(f"/api/analysis?ticker={t}&a={aid}&period=3y")
            assert r.status_code == 200, (t, aid, r.text)
            assert r.json()["kind"] == "index" and r.json()["evidence"] == []
    rel = client.get("/api/analysis?ticker=QQQ&a=relative&period=1y").json()
    assert rel["analysis"]["name"] == "Performance vs the other indexes"
    assert [s["key"] for s in rel["panels"][0]["series"]] == ["me", "spy", "dia", "iwm"]
    assert "Nasdaq-100" in rel["readout"] and "Russell 2000" in rel["readout"]
    # SPY against itself: the comparison lines are dropped, and beta explains why it can't run.
    vol = client.get("/api/analysis?ticker=SPY&a=volatility&period=1y").json()
    assert [s["key"] for s in vol["panels"][1]["series"]] == ["vol"] and "S&P 500's" not in vol["readout"]
    beta = client.get("/api/analysis?ticker=SPY&a=beta&period=1y")
    assert beta.status_code == 400 and "exactly 1" in beta.json()["error"]
    assert client.get("/api/analysis?ticker=QQQ&a=beta&period=1y").status_code == 200
    # Indexes have no stock page.
    assert client.get("/api/stocks/QQQ").status_code == 404


def test_stock_page_data(client):
    d = client.get("/api/stocks/KO").json()
    assert d["company"]["name"] == "The Coca-Cola Company" and d["company"]["sector_about"]
    assert d["fundamentals"] and {"checklist", "signals_now"}.isdisjoint(d)
    assert [r["period"] for r in d["returns"]][:4] == ["1m", "3m", "ytd", "1y"]
    assert all(r["stock"] is not None and r["spy"] is not None for r in d["returns"])
    p = client.get("/api/stocks/KO/prices?range=1y").json()["points"]
    assert 240 <= len(p) <= 265 and {"sma200", "spy_rebased"} <= set(p[0])
    assert len(client.get("/api/stocks/KO/prices?range=max").json()["points"]) <= 1300


def test_analysis_catalog_and_runs(client):
    cat = client.get("/api/analyses").json()
    ids = [a["id"] for a in cat["analyses"]]
    assert len(ids) == 13 and all(a["explain"]["what"] and a["explain"]["watch"] for a in cat["analyses"])
    for aid in ids:
        r = client.get(f"/api/analysis?ticker=KO&a={aid}&period=3y")
        assert r.status_code == 200, (aid, r.text)
        out = r.json()
        assert out["readout"] and out["summary"] and out["period"]["trading_days"] > 500
        assert out["panels"] or out["extra"]
        for panel in out["panels"]:
            for series in panel["series"]:
                assert len(out["data"][series["key"]]) == len(out["dates"])
    rsi = client.get("/api/analysis?ticker=KO&a=rsi&start=2020-01-01&end=2020-12-31&window=10").json()
    assert rsi["period"]["start"].startswith("2020-01") and rsi["period"]["end"].startswith("2020-12")
    assert next(p for p in rsi["params"] if p["id"] == "window")["value"] == 10
    ma = client.get("/api/analysis?ticker=KO&a=moving_averages&period=5y").json()
    assert {e["signal_id"] for e in ma["evidence"]} == {"above_200d", "golden_cross"}
    assert ma["evidence"][0]["sector_card"]["universe"] == "Consumer Staples"


def test_analysis_errors_are_explained(client):
    bad = client.get("/api/analysis?ticker=KO&a=moving_averages&short=200&long=50")
    assert bad.status_code == 400 and "fewer days" in bad.json()["error"]
    assert client.get("/api/analysis?ticker=KO&a=beta&period=1m").status_code == 400
    assert client.get("/api/analysis?ticker=KO&a=nope").status_code == 400
    assert client.get("/api/analysis?ticker=GME&a=rsi").status_code == 404
    assert client.get("/api/analysis?ticker=KO&a=rsi&start=2030-01-01").status_code == 400


def test_unknown_ticker_is_a_clear_404(client):
    r = client.get("/api/stocks/GME")
    assert r.status_code == 404 and "S&P 500" in r.json()["error"]


def test_price_chart_ranges(client):
    """The chart on stock and index pages: short ranges, year to date by default, and custom dates."""
    as_of = client.get("/api/meta").json()["as_of"]
    d = client.get("/api/stocks/KO/prices").json()
    assert d["range"] == "ytd" and d["end"] == as_of
    assert d["start"] < f"{as_of[:4]}-01-01" <= d["points"][1]["date"]          # starts at last year's final close
    n = {r: len(client.get(f"/api/stocks/KO/prices?range={r}").json()["points"]) for r in ("1m", "3m", "6m", "1y")}
    assert 15 <= n["1m"] < n["3m"] < n["6m"] < n["1y"] <= 265
    c = client.get("/api/stocks/SPY/prices?start=2025-03-03&end=2025-06-30").json()
    assert c["range"] == "custom" and c["start"] >= "2025-03-03" and c["end"] <= "2025-06-30"
    assert c["points"][0]["spy_rebased"] == pytest.approx(c["points"][0]["adj_close"])
    assert client.get("/api/stocks/KO/prices?range=bogus").json()["range"] == "ytd"
    assert client.get("/api/stocks/KO/prices?start=nope").status_code == 400
    assert client.get("/api/stocks/ZZZZ/prices").status_code == 404


def test_analyze_suggestions(client):
    s = client.get("/api/suggestions").json()
    assert [i["ticker"] for i in s["indexes"]] == ["SPY", "QQQ", "DIA", "IWM"]
    up, down = s["movers"]["up"], s["movers"]["down"]
    assert len(up) == 4 and len(down) == 4 and up[0]["ret_1w"] >= up[-1]["ret_1w"] > down[-1]["ret_1w"] >= down[0]["ret_1w"]
    caps = [r["market_cap"] for r in s["largest"]]
    assert len(caps) == 6 and caps == sorted(caps, reverse=True)
    assert len({r["name"].split(" (")[0] for r in s["largest"]}) == 6


def test_news(client):
    n = client.get("/api/news").json()
    assert n["moves"] and n["events"] and n["sectors"] and n["as_of"] and "headlines" not in n
    mv = n["moves"][0]
    assert {"headlines", "times_typical", "ret_1d", "excess_1d", "kind"} <= set(mv) and mv["times_typical"] > 1
    assert len(n["week"]["up"]) == 6 and n["week"]["up"][0]["ret_1w"] > n["week"]["down"][0]["ret_1w"]
    live = client.get("/api/news/live").json()                                    # demo data: the saved headlines
    assert live["live"] is False and live["moves"] == {}


def test_headlines_are_matched_to_the_day_a_stock_moved_and_name_the_company():
    from tickertutor import views

    moves = [{"ticker": "KO", "name": "The Coca-Cola Company", "date": "2026-11-05"},
             {"ticker": "PEP", "name": "PepsiCo", "date": "2026-11-05"}]
    feed = {"KO": [{"headline": "Coca-Cola shares slide on old news", "published": "2026-10-20T12:00:00+00:00"},
                   {"headline": "Coca-Cola (KO) falls after guidance cut", "published": "2026-11-06T13:00:00+00:00"},
                   {"headline": "Coke sales slow in Latin America", "published": "2026-11-04T22:00:00+00:00"},
                   {"headline": "Stock market today: Dow slips as yields climb", "published": "2026-11-05T21:00:00+00:00"},
                   {"headline": "Premarket movers", "summary": "Coca-Cola fell 6% after...", "published": "2026-11-05T12:00:00+00:00"},
                   {"headline": "Coca-Cola a week later", "published": "2026-11-12T09:00:00+00:00"},
                   {"headline": "Coca-Cola no date", "published": ""}]}
    views.attach_headlines(moves, feed, per_move=3)
    # Around the day only, the ones naming the company in the headline first, never the market roundup.
    assert [h["headline"] for h in moves[0]["headlines"]] == \
        ["Coke sales slow in Latin America", "Coca-Cola (KO) falls after guidance cut", "Premarket movers"]
    assert moves[1]["headlines"] == []


def test_news_feeds_drop_world_news_and_links_that_dont_open():
    from tickertutor.sources import news

    general = [{"headline": "Islam forecast to soon exceed Christianity as world's biggest faith - Reuters",
                "url": "https://news.google.com/rss/articles/CBMi?oc=5"},
               {"headline": "Wall St ends lower as hot inflation data heighten rate worries - Reuters",
                "url": "https://news.google.com/rss/articles/abc"},
               {"headline": "Measles is surging in the U.S.", "url": "https://www.cnbc.com/measles"},
               {"headline": "Jim Cramer's top 10 things to watch in the stock market Wednesday", "url": "https://www.cnbc.com/x"}]
    kept = [h for h in general if news._opens(h) and news.is_market_story(h)]
    assert [h["headline"] for h in kept] == ["Jim Cramer's top 10 things to watch in the stock market Wednesday"]
    assert news.mentions({"headline": "Nvidia Vs. AMD: neither is getting choked out"}, "Advanced Micro Devices", "AMD") == 2
    assert news.mentions({"headline": "Why Is Dell Technologies (DELL) Talking Up AI Racks?"}, "Advanced Micro Devices", "AMD") == 0
    assert news.mentions({"headline": "We all want lower rates"}, "The Allstate Corporation", "ALL") == 0
    assert news.mentions({"headline": "Fed's target rate path"}, "Target Corporation", "TGT") == 0
    assert news.name_keys("Alphabet Inc. (Class A)", "GOOGL") == ["Alphabet", "Google"]


def test_chat_contract(client, fake_llm):
    r = client.post("/chat", json={"message": "What do KO's moving averages show?"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"response", "session_id", "tool_calls"}
    assert body["session_id"].startswith("s_")
    assert all("agent" in c and "name" in c for c in body["tool_calls"])
    agents = {c["agent"] for c in body["tool_calls"]}
    assert "lead" in agents and any(a.startswith("researcher:market") for a in agents)
    assert "Sources" in body["response"] and "not financial advice" in body["response"]


def test_chat_follow_up_keeps_the_session(client, fake_llm):
    first = client.post("/chat", json={"message": "What should I buy?"}).json()
    assert first["tool_calls"][0]["result"]["action"] == "clarify"
    second = client.post("/chat", json={"message": "Dividend payers", "session_id": first["session_id"]}).json()
    assert second["session_id"] == first["session_id"]
    assert any(c["name"] == "screen_stocks" for c in second["tool_calls"])
    assert any(c["name"] == "run_analysis" for c in client.post("/chat", json={"message": "How volatile is KO?"}).json()["tool_calls"])


def test_chat_stream_events(client, fake_llm):
    events = []
    with client.stream("POST", "/chat/stream", json={"message": "What do MSFT's moving averages show?"}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "tool_call" and "plan" in kinds and "researcher_start" in kinds
    assert kinds.index("writing") < kinds.index("verified") < kinds.index("done")
    assert kinds[-1] == "done" and events[-1]["sources"]


def test_chat_rejects_empty_and_rate_limits(client, fake_llm, monkeypatch):
    assert client.post("/chat", json={"message": ""}).status_code == 422
    from tickertutor import config
    monkeypatch.setattr(config, "CHAT_RATE_PER_HOUR", 1)
    assert client.post("/chat", json={"message": "What do KO's moving averages show?"}).status_code == 200
    r = client.post("/chat", json={"message": "What do KO's moving averages show?"})
    assert r.status_code == 429 and "this hour" in r.json()["error"]
