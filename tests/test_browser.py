"""Browser smoke test: every page renders without script errors, and a research question runs end to end
(with the offline stand-in for the model). Skipped when no Chromium is available.

Set TICKERTUTOR_CHROMIUM to a Chromium executable if Playwright's bundled browser isn't installed
(`uv run playwright install chromium` installs it)."""

from __future__ import annotations

import os
import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(fake_llm):
    import uvicorn

    import app as app_module
    app_module._hits.clear()
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app_module.app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(timeout=5)


@pytest.fixture
def page():
    with playwright.sync_playwright() as p:
        try:
            exe = os.environ.get("TICKERTUTOR_CHROMIUM")
            browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"no Chromium for Playwright: {str(exc).splitlines()[0]}")
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        # Everything, fonts included, is served by the app itself, so any console error is ours.
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        outside = []
        pg.on("request", lambda r: outside.append(r.url) if not r.url.startswith(("http://127.0.0.1", "http://localhost", "data:")) else None)
        pg.outside = outside
        pg.errors = errors
        yield pg
        browser.close()


@pytest.mark.parametrize("hash_, expect", [
    ("#/", "Learn to read the stock market"),
    ("#/guide", "Find a company or index"),
    ("#/overview", "How it works"),
    ("#/index/SPY", "Its largest companies"),
    ("#/index/IWM", "Analyze the Russell 2000"),
    ("#/screener", "Screener"),
    ("#/screener?view=sector", "Screener"),
    ("#/stock/KO", "Analyze KO"),
    ("#/analyze?t=KO&a=rsi&p=1y", "About RSI"),
    ("#/analyze?t=KO&a=returns_distribution&p=5y", "About Return distribution"),
    ("#/analyze?t=KO&a=beta&p=3y", "About Beta & correlation"),
    ("#/signals", "Pick a stock or a market index to start"),
    ("#/analyze?a=rsi", "Opens with"),
    ("#/news", "In the news"),
    ("#/research", "Research desk"),
    ("#/learn", "Taxes and the one-year mark"),
    ("#/learn?term=pe", "P/E ratio"),
    ("#/analyze?t=QQQ&a=relative&p=1y", "Performance vs the other indexes"),
])
def test_pages_render(server, page, hash_, expect):
    page.goto(f"{server}/{hash_}")
    page.wait_for_selector(f"text={expect}", timeout=15000)
    page.wait_for_timeout(300)
    assert not page.query_selector("text=Something went wrong")
    assert page.errors == []
    assert page.outside == []   # no fonts, scripts, or anything else loaded from another site


def test_home_page(server, page):
    page.goto(f"{server}/#/")
    page.wait_for_selector(".marked .note")
    assert page.locator(".marked .note").count() >= 2            # the tutor's notes on the chart
    assert page.locator(".nav a[aria-current='page']").count() == 0   # home has no tab; the brand links to it
    page.fill(".home-search .stock-input", "nasdaq")
    page.keyboard.press("Enter")
    page.wait_for_selector("text=Analyze the Nasdaq-100")
    assert page.evaluate("location.hash") == "#/index/QQQ"
    assert page.get_attribute(".nav a[aria-current='page']", "data-id") == "screener"
    page.click(".brand")
    page.wait_for_selector(".home-search")
    page.fill(".home-search .stock-input", "coca")
    page.click(".home-search .btn")
    page.wait_for_selector("text=Analyze KO")
    assert page.evaluate("location.hash") == "#/stock/KO"
    # Finances sits right under the chart.
    heads = page.eval_on_selector_all(".stock-layout > div > .card h2", "els => els.map(e => e.textContent)")
    assert heads[0].startswith("Finances") and heads[1] == "Returns"
    assert page.errors == []


def test_analyze_controls(server, page):
    page.goto(f"{server}/#/analyze")
    page.click(".stock-input")
    page.fill(".stock-input", "coca")
    page.keyboard.press("Enter")
    page.click(".analysis-list button[data-id='volatility']")
    page.click(".period-seg button:has-text('3Y')")
    page.wait_for_selector("text=About Volatility")
    page.wait_for_load_state("networkidle")
    page.fill(".an-params input[data-id='window']", "63")
    page.dispatch_event(".an-params input[data-id='window']", "change")
    page.wait_for_function("location.hash.includes('window=63')")
    assert "t=KO" in page.evaluate("location.hash") and "a=volatility" in page.evaluate("location.hash")
    page.wait_for_selector("text=Rolling 63-day volatility")
    assert page.locator(".an-stats .stat").count() >= 4
    assert page.errors == []


def test_screener_indexes_and_learn_links(server, page):
    page.goto(f"{server}/#/screener")
    page.wait_for_selector(".index-card")
    assert page.locator(".index-card").count() == 4
    assert page.get_attribute(".seg button[aria-pressed='true']", "data-v") == "sector"   # by sector comes first
    assert page.get_attribute("input[type='search']", "placeholder") == "Search ticker"
    page.click(".index-card:has-text('Russell 2000')")           # an index opens its own page, under the Screener
    page.wait_for_selector("text=Analyze the Russell 2000")
    assert page.evaluate("location.hash") == "#/index/IWM"
    page.click("a.back")
    page.wait_for_selector(".index-card")
    # A "?" next to a stock's P/E opens its card on the Learn tab, highlighted.
    page.goto(f"{server}/#/stock/KO")
    page.wait_for_selector(".fact")
    page.click(".fact:has-text('P/E') a.qmark >> nth=0")
    page.wait_for_selector("#term-pe.flash")
    assert "term=pe" in page.evaluate("location.hash")
    assert page.errors == []


def test_stock_chart_starts_simple_and_has_short_ranges(server, page):
    page.goto(f"{server}/#/stock/KO")
    page.wait_for_selector(".price-chart svg.chart path")
    assert page.inner_text(".price-chart .seg button[aria-pressed='true']") == "YTD"
    assert page.eval_on_selector_all(".price-chart .seg button", "els => els.map(e => e.textContent)") == \
        ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "Max", "Custom"]
    # Just the price to start: the averages and the S&P 500 are off, and each has a "?".
    assert page.eval_on_selector_all(".price-chart .keys input", "els => els.map(e => e.checked)") == [False, False, False]
    assert page.locator(".price-chart svg.chart path").count() == 1
    assert page.locator(".price-chart .keys a.qmark").count() == 3
    assert "opens a plain explanation" not in page.inner_text(".page")
    page.click(".price-chart .keys label:has-text('200-day') input")
    page.wait_for_function("document.querySelectorAll('.price-chart svg.chart path').length === 2")
    page.click(".price-chart .seg button[data-k='1m']")
    page.wait_for_function("document.querySelector('.chart-summary').textContent.includes('dividends included')")
    page.click(".price-chart .seg button[data-k='custom']")
    page.fill(".price-chart .custom-dates input >> nth=0", "2025-03-03")
    page.fill(".price-chart .custom-dates input >> nth=1", "2025-06-30")
    page.click(".price-chart .custom-dates .btn")
    page.wait_for_function("document.querySelector('.chart-summary').textContent.includes('Jun 30, 2025')")
    page.click(".price-chart .keys label:has-text('50-day') a.qmark")     # the "?" goes to its own Learn card
    page.wait_for_selector("#term-moving-average.flash")
    assert page.errors == []


def test_tabs_remember_and_analyze_starts_empty(server, page):
    tab = lambda name: page.click(f".nav a[data-id='{name}']")   # noqa: E731
    page.goto(f"{server}/#/stock/KO")
    page.wait_for_selector("text=Analyze KO")
    tab("analyze")
    page.wait_for_selector(".an-start")
    assert page.evaluate("location.hash") == "#/analyze"
    assert not page.query_selector(".an-main")                     # nothing is analyzed until something is picked
    for heading in ("Market indexes", "Biggest moves this week", "Largest companies"):
        assert page.locator(f".sug-group h2:has-text('{heading}')").count() == 1
    tab("screener")                                               # back to the stock that was open
    page.wait_for_selector("text=Analyze KO")
    assert page.evaluate("location.hash") == "#/stock/KO"
    tab("analyze")
    page.click(".sug-group:has-text('Market indexes') .sug >> nth=1")
    page.wait_for_selector(".an-main .an-stats .stat")
    assert page.evaluate("location.hash").startswith("#/analyze?t=QQQ")
    page.click(".analysis-list button[data-id='drawdown']")
    page.wait_for_function("location.hash.includes('a=drawdown')")
    assert page.locator(".an-stats a.qmark").count() >= 1
    tab("learn")
    page.wait_for_selector(".term-find")
    tab("analyze")                                                # same index, same analysis
    page.wait_for_selector("text=About Drawdowns")
    assert "t=QQQ" in page.evaluate("location.hash") and "a=drawdown" in page.evaluate("location.hash")
    page.click("a.back")                                          # and a way back to the start screen
    page.wait_for_selector(".an-start")
    assert page.evaluate("location.hash") == "#/analyze"
    assert page.locator(".sug-group:has-text('Pick up where you left off') .sug").count() == 1
    tab("screener")
    tab("screener")                                               # clicking the tab you're on goes to its start
    page.wait_for_selector(".index-card")
    assert page.evaluate("location.hash") == "#/screener"
    assert page.errors == []


def test_news_moves_open_analyze_and_every_question_mark_has_a_card(server, page):
    page.goto(f"{server}/#/news")
    page.wait_for_selector(".move.link")
    ticker = page.inner_text(".move.link >> nth=0 >> .tick")
    assert page.locator(".page-news a.qmark").count() >= 10
    page.wait_for_function("!document.querySelector('.head-stamp span').textContent.includes('Checking')")
    page.click(".move.link >> nth=0", position={"x": 200, "y": 10})
    page.wait_for_selector(".an-main .an-stats .stat")
    assert page.evaluate("location.hash").startswith(f"#/analyze?t={ticker}&a=moving_averages")
    # Collect every "?" and term link on the busiest pages. Each must point at a card that exists on Learn.
    hrefs = set()
    for h in ("#/news", "#/stock/KO", "#/index/QQQ", "#/guide", "#/analyze", "#/analyze?t=KO&a=returns_distribution&p=1y",
              "#/analyze?t=KO&a=beta&p=1y", "#/analyze?t=KO&a=rolling_returns&p=3y", "#/screener?view=list"):
        page.goto(f"{server}/{h}")
        page.wait_for_selector("a.qmark, a.term-link")
        page.wait_for_load_state("networkidle")
        hrefs |= set(page.eval_on_selector_all("a.qmark, a.term-link", "els => els.map(e => e.getAttribute('href'))"))
        assert page.locator("span.qmark").count() == 0             # no "?" that isn't a link
    page.goto(f"{server}/#/learn")
    page.wait_for_selector(".term-find")
    cards = set(page.eval_on_selector_all("[id^='term-']", "els => els.map(e => e.id)"))
    assert len(hrefs) >= 40
    assert all(h.startswith("#/learn?term=") and f"term-{h.split('=')[1]}" in cards for h in hrefs), sorted(hrefs)
    page.fill(".term-find", "priced in")
    assert page.is_visible("#term-priced-in") and not page.is_visible("#term-pe")
    assert page.errors == []


def test_research_desk_end_to_end(server, page):
    page.goto(f"{server}/#/research")
    page.fill("textarea", "What do KO's moving averages and volatility show?")
    page.click("form.ask button[type=submit]")
    page.wait_for_selector(".report .made", timeout=60000)
    assert page.locator(".agent-card.researcher").count() >= 2       # parallel researchers showed up live
    assert page.locator(".report .sources li").count() >= 1
    page.click(".report a.cite >> nth=0")
    assert page.evaluate("location.hash") == "#/research"            # citations don't navigate away
    assert page.errors == []
