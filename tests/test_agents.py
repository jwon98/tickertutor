"""The research team end to end on the demo database, with the fake model."""

from __future__ import annotations

import pytest

from tickertutor import agents


def test_research_run_fans_out_reviews_and_cites(fake_llm):
    events = []
    out = agents.answer("What do KO's moving averages and volatility show?", on_event=events.append)
    assert set(out) == {"response", "session_id", "tool_calls"}
    agents_seen = [c["agent"] for c in out["tool_calls"]]
    assert agents_seen[0] == "lead"
    # Round 1: market + fundamentals in parallel; review finds a gap; round 2: news.
    assert any(a.startswith("researcher:market#") for a in agents_seen)
    assert any(a.startswith("researcher:fundamentals#") for a in agents_seen)
    assert any(a.startswith("researcher:news#") for a in agents_seen)
    assert "review_findings" in [c["name"] for c in out["tool_calls"]]
    assert agents_seen[-2:] == ["writer", "verifier"] or agents_seen[-1] == "verifier"
    assert all({"agent", "name", "args", "result"} <= set(c) for c in out["tool_calls"])
    # Citations: [S#] became numbered links, unknown ids were dropped, sources listed, disclaimer added.
    text = out["response"]
    assert "[S" not in text and "[1]" in text and "**Sources**" in text and "not financial advice" in text
    assert "S999" not in text
    kinds = [e["type"] for e in events]
    assert kinds[0] == "tool_call" and "researcher_start" in kinds and kinds[-1] == "done"
    starts = [e for e in events if e["type"] == "researcher_start"]
    assert len({e["agent"] for e in starts}) == 3


def test_verifier_issue_triggers_one_revision(fake_llm):
    fake_llm.flag_issue_once = True
    out = agents.answer("How risky has KO been?")
    names = [c["name"] for c in out["tool_calls"]]
    assert "revise_report" in names
    assert "every year" not in out["response"]


def test_vague_question_gets_clarified_then_answered(fake_llm):
    first = agents.answer("What should I buy?")
    assert first["response"].startswith("Ticker Tutor doesn't pick stocks")
    assert not any(c["agent"].startswith("researcher") for c in first["tool_calls"])
    second = agents.answer("How the biggest energy stocks have moved this year", first["session_id"])
    assert any(c["name"] == "screen_stocks" and c["args"]["sector"] == "Energy" for c in second["tool_calls"])
    s = agents.sessions.get(first["session_id"])
    assert len(s["turns"]) == 2 and s["pending"] is None


def test_out_of_scope_says_so(fake_llm):
    out = agents.answer("Should I buy bitcoin?")
    assert "doesn't cover crypto" in out["response"]
    assert [c["agent"] for c in out["tool_calls"]] == ["lead"]


def test_unknown_ticker_is_reported_to_the_lead(fake_llm, demo_db):
    found, missing = agents.mentioned_companies("Compare GME and AAPL")
    assert [f["ticker"] for f in found] == ["AAPL"] and "GME" in missing


def test_indexes_are_in_scope_for_the_research_team(demo_db):
    from tickertutor import indexes
    from tickertutor.tools import Sources, run_tool

    found, missing = agents.mentioned_companies("Is QQQ more volatile than SPY and IWM?")
    assert not {"QQQ", "SPY", "IWM"} & set(missing)
    assert [i["ticker"] for i in indexes.find("How did the Dow do vs the Nasdaq and small caps?")] == ["QQQ", "DIA", "IWM"]
    assert indexes.find("the downturn in tech") == []

    class Ctx:
        sources = Sources()
    out = run_tool(Ctx(), "run_analysis", {"ticker": "QQQ", "analysis_id": "volatility", "period": "1y"})
    assert out["ok"] and out["ticker"] == "QQQ" and "Nasdaq-100 fund" in Ctx.sources.items["S1"]["title"]
    hits = run_tool(Ctx(), "find_ticker", {"name": "Nasdaq"})["matches"]
    assert hits[0]["ticker"] == "QQQ"


def test_round_cap_is_reported(fake_llm, monkeypatch):
    from tickertutor import config
    monkeypatch.setattr(config, "MAX_ROUNDS", 1)
    out = agents.answer("What do KO's moving averages and volatility show?")
    stop = [c for c in out["tool_calls"] if c["name"] == "stop_research"]
    assert stop and stop[0]["agent"] == "lead" and "round" in stop[0]["args"]["reason"]
    assert not any(c["agent"].startswith("researcher:news") for c in out["tool_calls"])   # no second round


def test_why_is_it_down_gets_the_news_and_the_numbers(fake_llm):
    """A blunt "why is X down so bad?" is researched, not bounced back, by a news Researcher and a market
    Researcher who measures the move."""
    out = agents.answer("why is coca-cola down so bad?")
    plan = next(c for c in out["tool_calls"] if c["name"] == "plan_research")["result"]
    assert plan["action"] == "research" and {t["role"] for t in plan["tasks"]} == {"news", "market"}
    by_role = {}
    for c in out["tool_calls"]:
        if c["agent"].startswith("researcher"):
            by_role.setdefault(c["agent"].split(":")[1].split("#")[0], set()).add(c["name"])
    assert {"get_price_move", "get_company_news", "get_recent_moves", "get_recent_filings"} <= by_role["news"]
    assert {"get_price_move", "run_analysis"} <= by_role["market"]
    move = next(c for c in out["tool_calls"] if c["name"] == "get_price_move")
    assert move["args"]["ticker"] == "KO" and move["result"]["ok"] is True
    assert "Sources" in out["response"] and "price-move summary for KO" in out["response"]


def test_price_move_tool_measures_how_unusual_a_move_is(demo_db):
    from tickertutor import tools, views

    m = views.price_move("KO", 30)
    assert m["window_days"] == 30 and [r["period"] for r in m["returns"]] == ["1 day", "1 week", "1 month", "3 months", "this year"]
    week = m["returns"][1]
    assert week["vs_sp500"] == pytest.approx(week["stock"] - week["sp500"])
    assert -1 < m["from_52_week_high"]["below_high"] <= 0 and 0.002 < m["typical_daily_move"] < 0.1
    worst = m["biggest_down_days"][0]
    assert worst["return"] < 0 and worst["times_typical_day"] == pytest.approx(abs(worst["return"]) / m["typical_daily_move"])
    assert 1 <= worst["days_this_extreme_in_history"] <= worst["history_days"]
    assert "sp500" not in views.price_move("SPY")["returns"][0]                 # the index isn't compared with itself

    class Ctx:
        sources = tools.Sources()

    out = tools.run_tool(Ctx, "get_price_move", {"ticker": "QQQ", "days": 10})
    assert out["ok"] and out["ref"] == "S1" and out["window"]["trading_days"] == 10
    assert out["returns"][0]["stock"].endswith("%") and out["pages"]["In the news"] == "#/news"
    assert "get_price_move" in tools.ROLE_TOOLS["market"] and "get_price_move" in tools.ROLE_TOOLS["news"]
    assert tools.run_tool(Ctx, "get_price_move", {"ticker": "ZZZZ"})["ok"] is False


def test_writer_is_given_pages_to_point_to(fake_llm):
    run = agents.Run("why is KO down?", agents.sessions.get(None))
    run.run()
    pages = run.pages()
    assert pages["In the news"] == "#/news" and any(v.startswith("#/analyze?t=KO&a=drawdown") for v in pages.values())
