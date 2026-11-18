"""Shared fixtures: one synthetic demo database per test session, and the fake model."""

from __future__ import annotations

import pytest

from tests.fakes import FakeLLM


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory):
    from tickertutor import data
    from tickertutor.build import compute, demo

    path = tmp_path_factory.mktemp("db") / "demo.duckdb"
    compute.write_db(compute.compute(demo.generate(), progress=lambda m: None), path)
    data.set_db(path)
    yield path
    data.set_db(None)


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    from tickertutor import agents, config
    from tickertutor.sources import news

    monkeypatch.setattr(config, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    news.clear_cache()
    # No network in tests: live news falls back to the database snapshot.
    from tickertutor.sources import SourceError

    def no_net(*a, **k):
        raise SourceError("network disabled in tests")
    monkeypatch.setattr(news, "gdelt", no_net)
    monkeypatch.setattr(news, "market_news", no_net)
    agents.sessions.__init__()


@pytest.fixture
def fake_llm(monkeypatch, demo_db):
    return FakeLLM().install(monkeypatch)
