"""Data source clients, against recorded-style responses (no network)."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pandas as pd
import pytest

from tickertutor import config
from tickertutor import sources
from tickertutor.sources import SourceError, fred, news, prices, sec, wikipedia

GDELT = news.gdelt          # the real function, captured before the offline fixture swaps it out
COMPANY_NEWS = news.company_news


@pytest.fixture
def mock_http(monkeypatch):
    """Route every request to a handler: mock_http(handler) → list of requests seen."""
    seen: list[httpx.Request] = []

    def install(handler):
        def wrapped(request):
            seen.append(request)
            return handler(request)
        sources.set_client(httpx.Client(transport=httpx.MockTransport(wrapped)))
        return seen
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    monkeypatch.setattr(sec.time, "sleep", lambda s: None)
    yield install
    sources.set_client(None)


# --- the shared GET helper ---------------------------------------------------------------------------------

def test_get_retries_rate_limits_then_succeeds(mock_http):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429) if calls["n"] < 3 else httpx.Response(200, json={"ok": 1})
    mock_http(handler)
    assert sources.get("https://example.com/x") == {"ok": 1}
    assert calls["n"] == 3


def test_get_explains_auth_failures(mock_http):
    mock_http(lambda req: httpx.Response(401, text="bad key"))
    with pytest.raises(SourceError, match="refused the request.*API key"):
        sources.get("https://data.alpaca.markets/v2/stocks/bars")


# --- Wikipedia: constituents, changes, and point-in-time membership ----------------------------------------

def wiki_html(n=420):
    rows = "".join(
        f"<tr><td>T{i:03d}</td><td>Company {i}</td><td>Industrials</td><td>Machinery</td><td>City</td>"
        f"<td>2001-01-0{1 + i % 9}</td><td>{1000 + i}</td><td>1950</td></tr>" for i in range(n))
    rows += ("<tr><td>KO</td><td>Coca-Cola Company (The)</td><td>Consumer Staples</td><td>Soft Drinks</td><td>Atlanta</td>"
             "<td>1957-03-04</td><td>21344</td><td>1886</td></tr>"
             "<tr><td>NEWCO</td><td>New Co</td><td>Energy</td><td>Oil</td><td>Houston</td><td>2023-06-01</td><td>99</td><td>2000</td></tr>")
    cons = ("<table id='constituents'><thead><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th>"
            "<th>Headquarters Location</th><th>Date added</th><th>CIK</th><th>Founded</th></tr></thead><tbody>" + rows + "</tbody></table>")
    changes = ("<table id='changes'><thead><tr><th rowspan='2'>Effective Date</th><th colspan='2'>Added</th><th colspan='2'>Removed</th>"
               "<th rowspan='2'>Reason</th></tr><tr><th>Ticker</th><th>Security</th><th>Ticker</th><th>Security</th></tr></thead><tbody>"
               "<tr><td>June 1, 2023</td><td>NEWCO</td><td>New Co</td><td>OLDCO</td><td>Old Co</td><td>Market cap change.</td></tr>"
               "<tr><td>March 2, 2015</td><td>OLDCO</td><td>Old Co</td><td>GONE</td><td>Gone Inc</td><td>Acquired.</td></tr>"
               "</tbody></table>")
    return "<html><body>" + cons + changes + "</body></html>"


def test_wikipedia_parse_and_membership():
    constituents, changes = wikipedia.parse(wiki_html())
    assert len(constituents) == 422
    ko = next(c for c in constituents if c["ticker"] == "KO")
    assert ko["sector"] == "Consumer Staples" and ko["cik"] == 21344 and ko["date_added"] == date(1957, 3, 4)
    assert {(c["date"], c["added"], c["removed"]) for c in changes} == {
        (date(2023, 6, 1), "NEWCO", "OLDCO"), (date(2015, 3, 2), "OLDCO", "GONE")}
    m = {(i["ticker"]): i for i in wikipedia.membership(constituents, changes, today=date(2026, 10, 30))}
    assert m["NEWCO"]["start"] == date(2023, 6, 1) and m["NEWCO"]["end"] is None
    assert m["OLDCO"]["start"] == date(2015, 3, 2) and m["OLDCO"]["end"] == date(2023, 6, 1)   # a former member
    assert m["GONE"]["start"] == wikipedia.EARLIEST and m["GONE"]["end"] == date(2015, 3, 2)
    assert m["KO"]["end"] is None


def test_wikipedia_layout_change_is_reported():
    with pytest.raises(SourceError, match="layout"):
        wikipedia.parse("<html><table id='constituents'><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th>"
                        "<th>GICS Sub-Industry</th></tr><tr><td>A</td><td>B</td><td>C</td><td>D</td></tr></table></html>")


# --- prices ---------------------------------------------------------------------------------------------------

def test_alpaca_merges_adjusted_and_raw_with_paging(mock_http, monkeypatch):
    monkeypatch.setattr(config, "ALPACA_API_KEY", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET", "s")

    def handler(req):
        p = dict(req.url.params)
        assert req.headers["APCA-API-KEY-ID"] == "k"
        adj = p["adjustment"] == "all"
        if "page_token" not in p:
            bars = {"AAPL": [{"t": "2024-01-02T05:00:00Z", "c": 184.0 if adj else 185.6, "v": 1e6}]}
            return httpx.Response(200, json={"bars": bars, "next_page_token": "p2"})
        bars = {"AAPL": [{"t": "2024-01-03T05:00:00Z", "c": 182.5 if adj else 184.2, "v": 2e6}],
                "BRK.B": [{"t": "2024-01-03T05:00:00Z", "c": 360.0, "v": 5e5}]}
        return httpx.Response(200, json={"bars": bars, "next_page_token": None})
    mock_http(handler)
    df = prices.alpaca(["AAPL", "BRK.B"], date(2024, 1, 1), date(2024, 1, 5))
    aapl = df[df.ticker == "AAPL"].sort_values("date")
    assert list(aapl["date"]) == [date(2024, 1, 2), date(2024, 1, 3)]   # UTC timestamps → New York trading dates
    assert list(aapl["adj_close"]) == [184.0, 182.5] and list(aapl["close"]) == [185.6, 184.2]
    assert df[df.ticker == "BRK.B"]["close"].iloc[0] == 360.0


def test_alpaca_skips_one_bad_symbol(mock_http, monkeypatch):
    monkeypatch.setattr(config, "ALPACA_API_KEY", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET", "s")

    def handler(req):
        syms = req.url.params["symbols"].split(",")
        if "BADX" in syms:
            return httpx.Response(422, json={"message": "invalid symbol: BADX"})
        return httpx.Response(200, json={"bars": {s: [{"t": "2024-01-02T05:00:00Z", "c": 10.0, "v": 1}] for s in syms}})
    mock_http(handler)
    df = prices.alpaca(["MSFT", "BADX"], date(2024, 1, 1), date(2024, 1, 5))
    assert set(df.ticker) == {"MSFT"}


def test_alpaca_needs_keys(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_API_KEY", "")
    with pytest.raises(SourceError, match="ALPACA_API_KEY"):
        prices.alpaca(["AAPL"], date(2024, 1, 1), date(2024, 1, 5))


def test_tiingo_and_stooq_parsing(mock_http, monkeypatch):
    monkeypatch.setattr(config, "TIINGO_API_KEY", "t")

    def handler(req):
        if "tiingo" in req.url.host:
            assert "BRK-B" in req.url.path
            return httpx.Response(200, json=[{"date": "2024-01-02T00:00:00.000Z", "close": 360.0, "adjClose": 359.0,
                                              "volume": 100}])
        return httpx.Response(200, text="Date,Open,High,Low,Close,Volume\n2024-01-02,1,2,0.5,1.5,1000\n")
    mock_http(handler)
    t = prices.tiingo_one("BRK.B", date(2024, 1, 1), date(2024, 1, 5))
    assert t.iloc[0]["adj_close"] == 359.0 and t.iloc[0]["ticker"] == "BRK.B"
    s = prices.stooq_one("AAPL", date(2024, 1, 1), date(2024, 1, 5))
    assert s.iloc[0]["close"] == 1.5 and s.iloc[0]["date"] == date(2024, 1, 2)


def test_stooq_daily_limit_is_explained(mock_http):
    mock_http(lambda req: httpx.Response(200, text="Exceeded the daily hits limit"))
    with pytest.raises(SourceError, match="daily download limit"):
        prices.stooq_one("AAPL", date(2024, 1, 1), date(2024, 1, 5))


def test_download_caches_per_ticker(mock_http, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    seen = mock_http(lambda req: httpx.Response(200, text="Date,Open,High,Low,Close,Volume\n2024-01-02,1,2,0.5,1.5,1000\n"))
    a = prices.download(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 5), provider="stooq")
    assert len(a) == 2 and len(seen) == 2
    b = prices.download(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 5), provider="stooq")
    assert len(b) == 2 and len(seen) == 2            # served from the cache, no new requests


# --- SEC EDGAR -------------------------------------------------------------------------------------------------

def test_extract_facts_prefers_earlier_concepts_and_filters_units():
    raw = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"start": "2022-01-01", "end": "2022-12-31", "val": 100, "fy": 2022, "fp": "FY", "form": "10-K", "filed": "2023-02-01", "accn": "a1"}]}},
        "Revenues": {"units": {"USD": [
            {"start": "2022-01-01", "end": "2022-12-31", "val": 999, "fy": 2022, "fp": "FY", "form": "10-K", "filed": "2023-02-01", "accn": "a1"},
            {"start": "2021-01-01", "end": "2021-12-31", "val": 90, "fy": 2021, "fp": "FY", "form": "10-K", "filed": "2022-02-01", "accn": "a0"},
            {"start": "2021-01-01", "end": "2021-12-31", "val": 1, "fy": 2021, "fp": "FY", "form": "8-K", "filed": "2022-01-20", "accn": "x"}]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [
            {"start": "2022-01-01", "end": "2022-12-31", "val": 2.5, "fy": 2022, "fp": "FY", "form": "10-K", "filed": "2023-02-01"}],
            "USD": [{"start": "2022-01-01", "end": "2022-12-31", "val": 7, "fy": 2022, "fp": "FY", "form": "10-K", "filed": "2023-02-01"}]}},
    }, "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"end": "2023-01-20", "val": 5e9, "fy": 2022, "fp": "FY", "form": "10-K", "filed": "2023-02-01"}]}}}}}
    rows = pd.DataFrame(sec.extract_facts(raw))
    rev = rows[rows.metric == "revenue"].sort_values("end")
    assert list(rev["value"]) == [90, 100]                # 2022 from the preferred tag; 8-K ignored
    assert list(rows[rows.metric == "eps_diluted"]["value"]) == [2.5]
    assert rows[rows.metric == "shares_outstanding"]["value"].iloc[0] == 5e9


def test_filings_items_urls_and_older_pages(mock_http):
    recent = {"form": ["8-K", "4", "10-K"], "accessionNumber": ["0000320193-24-000001", "x", "0000320193-23-000106"],
              "filingDate": ["2024-02-01", "2024-01-15", "2023-11-03"], "reportDate": ["2024-02-01", "", "2023-09-30"],
              "items": ["2.02,9.01", "", ""], "primaryDocument": ["a8k.htm", "f4.xml", "aapl-20230930.htm"]}
    older = {"form": ["8-K"], "accessionNumber": ["0000320193-15-000002"], "filingDate": ["2015-01-27"],
             "reportDate": ["2015-01-27"], "items": ["2.02"], "primaryDocument": ["old.htm"]}

    def handler(req):
        if req.url.path.endswith("CIK0000320193.json"):
            return httpx.Response(200, json={"cik": "320193", "filings": {"recent": json.loads(json.dumps(recent)),
                                  "files": [{"name": "CIK0000320193-submissions-001.json", "filingTo": "2016-01-01"},
                                            {"name": "CIK0000320193-submissions-000.json", "filingTo": "2009-01-01"}]}})
        assert req.url.path.endswith("-001.json"), "pages older than the start date shouldn't be fetched"
        return httpx.Response(200, json=older)
    seen = mock_http(handler)
    out = sec.filings(sec.submissions_all(320193, "2014-01-01"))
    assert [f["form"] for f in out] == ["8-K", "10-K", "8-K"]
    assert out[0]["item_names"] == ["Earnings results", "Financial exhibits"]
    assert out[1]["url"] == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
    assert out[2]["filed"] == "2015-01-27"
    assert all(r.headers["User-Agent"] == config.SEC_USER_AGENT for r in seen)   # the SEC asks for a contact


def test_risk_factor_section_skips_table_of_contents():
    toc = "Item 1A. Risk Factors 12\nItem 1B. Unresolved Staff Comments 20\n"
    body = ("Item 1A. Risk Factors\nThe Company's business depends on consumer demand, which can change quickly.\n"
            "Competition could reduce our margins and market share over time in key markets.\n"
            "Item 1B. Unresolved Staff Comments\nNone.")
    text = sec.html_to_text("<p>" + toc.replace("\n", "</p><p>") + "</p>" + "<div>" + body.replace("\n", "</div><div>") + "</div>")
    sec_text = sec.section(text, "risk_factors")
    assert "consumer demand" in sec_text and "Unresolved" not in sec_text
    titles = sec.risk_titles(sec_text)
    diff = sec.compare_lists(titles + ["New regulations on sugary drinks could raise our costs significantly."],
                             [t.replace("quickly", "fast") for t in titles])
    assert diff["added"] == ["New regulations on sugary drinks could raise our costs significantly."]
    assert diff["removed"] == []


# --- news & FRED --------------------------------------------------------------------------------------------

def test_finnhub_company_news_dedupes_and_caches(mock_http, monkeypatch):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "f")
    monkeypatch.setattr(news, "company_news", COMPANY_NEWS)
    news.clear_cache()
    item = {"headline": "Apple unveils new chip", "summary": "s", "source": "Reuters", "url": "https://r.com/1",
            "datetime": 1730000000, "related": "AAPL"}
    seen = mock_http(lambda req: httpx.Response(200, json=[item, dict(item, url="https://r.com/2"), {"headline": ""}]))
    out = news.company_news("AAPL", "Apple", 7)
    assert len(out) == 1 and out[0]["provider"] == "Finnhub" and out[0]["published"].startswith("2024-10-27")
    news.company_news("AAPL", "Apple", 7)
    assert len(seen) == 1


def test_gdelt_parsing(mock_http):
    news.clear_cache()
    mock_http(lambda req: httpx.Response(200, json={"articles": [
        {"title": "Stocks rally", "url": "https://n.com/a", "domain": "n.com", "seendate": "20261030T140000Z"}]}))
    out = GDELT('"Apple"', 7)
    assert out[0]["headline"] == "Stocks rally" and out[0]["published"].startswith("2026-10-30T14:00")


def test_fred_skips_missing_values(mock_http, monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "k")
    mock_http(lambda req: httpx.Response(200, json={"observations": [
        {"date": "2026-10-29", "value": "4.05"}, {"date": "2026-10-30", "value": "."}]}))
    assert fred.series("DGS10", date(2026, 10, 1)) == [{"series": "DGS10", "date": "2026-10-29", "value": 4.05}]


def test_user_agent_carries_a_contact_email(monkeypatch):
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)
    monkeypatch.setattr(config, "SEC_USER_AGENT", "Ticker Tutor class project jane.doe@columbia.edu")
    assert config._contact() == "jane.doe@columbia.edu"
    monkeypatch.setenv("CONTACT_EMAIL", "other@example.org")
    assert config._contact() == "other@example.org"


def test_contact_problems_are_explained(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / ".env.txt").write_text("x")
    assert "Rename-Item .env.txt .env" in config.contact_problem()
    (tmp_path / ".env").write_text("x")
    monkeypatch.setattr(config, "CONTACT_EMAIL", "")
    assert "no email" in config.contact_problem()
    monkeypatch.setattr(config, "CONTACT_EMAIL", "your-email@example.com")
    assert "placeholder" in config.contact_problem()
    monkeypatch.setattr(config, "CONTACT_EMAIL", "jane@columbia.edu")
    assert config.contact_problem() == ""


def test_wikipedia_refusal_says_what_to_do(mock_http):
    mock_http(lambda req: httpx.Response(403, text="Please set a user-agent and respect our robot policy https://w.wiki/4wJS"))
    with pytest.raises(SourceError) as err:
        wikipedia.fetch_html()
    msg = str(err.value)
    assert "SEC_USER_AGENT" in msg and "--wiki-html" in msg and "robot policy" in msg and "API key" not in msg


def test_wikipedia_from_a_saved_page(tmp_path):
    saved = tmp_path / "List of S&P 500 companies - Wikipedia.html"
    saved.write_text(wiki_html(), encoding="utf-8")
    out = wikipedia.fetch(str(saved))
    assert len(out["constituents"]) == 422 and out["membership"]


def test_changes_from_the_historical_components_page(mock_http, monkeypatch, tmp_path):
    """The changes table moved to its own article: read it from there, across several tables."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    full = wiki_html()
    list_page = full.split("<table id='changes'>")[0] + "</body></html>"
    changes_table = "<table id='changes'>" + full.split("<table id='changes'>")[1].split("</body>")[0]
    older = changes_table.replace("June 1, 2023", "May 3, 2010").replace("NEWCO", "MIDCO").replace("March 2, 2015", "April 1, 2009")
    pages = {wikipedia.PAGE: list_page,
             wikipedia.CHANGES_PAGE: "<html><body><h2>2010s</h2>" + changes_table + "<h2>2000s</h2>" + older + "</body></html>"}
    seen = []

    def respond(req):
        seen.append(req.url.params["page"])
        return httpx.Response(200, json={"parse": {"text": pages[req.url.params["page"]]}})
    mock_http(respond)
    out = wikipedia.fetch()
    assert seen == [wikipedia.PAGE, wikipedia.CHANGES_PAGE]
    keys = {(c["date"], c["added"], c["removed"]) for c in out["changes"]}
    assert (date(2023, 6, 1), "NEWCO", "OLDCO") in keys and (date(2010, 5, 3), "MIDCO", "OLDCO") in keys
    assert any(m["ticker"] == "GONE" and m["end"] == date(2015, 3, 2) for m in out["membership"])
    assert (tmp_path / "wikipedia_sp500_changes.html").exists()   # kept for troubleshooting


def test_former_components_layout():
    html = ("<table class='wikitable'><thead><tr><th>Symbol</th><th>Security</th><th>Date added</th><th>Date removed</th></tr></thead>"
            "<tbody><tr><td>GONE</td><td>Gone Inc</td><td>June 3, 1999</td><td>March 2, 2015</td></tr>"
            "<tr><td>OLDX</td><td>Old X</td><td>—</td><td>2012-07-01[3]</td></tr></tbody></table>")
    ch = {(c["date"], c["added"], c["removed"]) for c in wikipedia.parse_changes(html)}
    assert ch == {(date(2015, 3, 2), "", "GONE"), (date(1999, 6, 3), "GONE", ""), (date(2012, 7, 1), "", "OLDX")}
    m = {i["ticker"]: i for i in wikipedia.membership([], wikipedia.parse_changes(html), today=date(2026, 1, 1))}
    assert m["GONE"]["start"] == date(1999, 6, 3) and m["GONE"]["end"] == date(2015, 3, 2)
    assert m["OLDX"]["start"] == wikipedia.EARLIEST and m["OLDX"]["end"] == date(2012, 7, 1)


def test_changes_table_without_id_and_footnote_dates():
    html = wiki_html().replace("id='changes'", "class='wikitable'").replace("June 1, 2023", "June 1, 2023[12]")
    constituents, changes = wikipedia.parse(html)
    assert (date(2023, 6, 1), "NEWCO", "OLDCO") in {(c["date"], c["added"], c["removed"]) for c in changes}
