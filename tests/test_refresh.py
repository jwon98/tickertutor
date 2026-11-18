"""Keeping prices current: which day counts as finished, when cached prices are reused, the background
update the app runs for itself, and switching to the refreshed database."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from tickertutor import config, data, refresh
from tickertutor.sources import prices


@pytest.mark.parametrize("now, expected", [
    ("2026-11-14 17:19", "2026-11-13"),   # Saturday: Friday is the last finished day
    ("2026-11-13 17:59", "2026-11-12"),   # Friday before 6 pm New York: Friday isn't final yet
    ("2026-11-13 18:00", "2026-11-13"),
    ("2026-11-16 09:00", "2026-11-13"),   # Monday morning
    ("2026-11-16 19:00", "2026-11-16"),
])
def test_last_finished_day(now, expected):
    assert str(prices.last_finished_day(pd.Timestamp(now, tz=prices.NEW_YORK))) == expected


def test_cached_prices_are_refetched_only_when_they_miss_the_last_day(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    end = date.today() - timedelta(days=10)
    calls = []

    def fake(ticker, start, end_):
        calls.append(ticker)
        return pd.DataFrame([{"ticker": ticker, "date": end_, "close": 10.0, "adj_close": 10.0, "volume": 1.0}])[prices.COLUMNS]

    monkeypatch.setattr(prices, "stooq_one", fake)
    cache = tmp_path / "prices" / "stooq"
    cache.mkdir(parents=True)

    def saved(ticker, last_day, hours_old):
        f = cache / f"{ticker}.csv"
        pd.DataFrame([{"ticker": ticker, "date": last_day, "close": 9.0, "adj_close": 9.0, "volume": 1.0}])[prices.COLUMNS].to_csv(f, index=False)
        t = time.time() - hours_old * 3600
        os.utime(f, (t, t))

    saved("HASDAY", end, 5)                         # complete: keep
    saved("LATE", end - timedelta(days=1), 5)       # fetched hours ago and still missing the day: ask again
    saved("JUSTNOW", end - timedelta(days=1), 1)    # just fetched: don't hammer the provider
    saved("OLD", end, 24 * 30)                      # saved before that day was final: fetch
    out = prices.download(["HASDAY", "LATE", "JUSTNOW", "OLD"], end - timedelta(days=30), end, provider="stooq")
    assert sorted(calls) == ["LATE", "OLD"]
    assert set(out["ticker"]) == {"HASDAY", "LATE", "JUSTNOW", "OLD"}


def _real_copy(src, dest, as_of=None):
    """A copy of the demo database that says it's real data, optionally with a later as-of date."""
    shutil.copy(src, dest)
    con = duckdb.connect(str(dest))
    con.execute("UPDATE meta SET value = 'False' WHERE key = 'synthetic'")
    if as_of:
        con.execute("UPDATE meta SET value = ? WHERE key = 'as_of'", [as_of])
    con.close()
    return dest


@pytest.fixture
def real_db(demo_db, tmp_path, monkeypatch):
    path = _real_copy(demo_db, tmp_path / "tickertutor.duckdb")
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "DATA_GCS_URI", "")
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("AUTO_REFRESH", raising=False)
    monkeypatch.delenv("REFRESH_UPLOAD_URI", raising=False)
    monkeypatch.setattr(refresh, "_last_check", 0.0)
    refresh._state.update(state="idle", message="", started=None, finished=None)
    data.set_db(path)
    yield path
    data.set_db(demo_db)


def _wait():
    for _ in range(200):
        if refresh.status()["state"] != "running":
            return
        time.sleep(0.02)
    raise AssertionError("the update never finished")


def test_app_updates_itself_when_prices_are_behind(real_db, demo_db, monkeypatch):
    before = data.db().meta()["as_of"]
    newer = str(date.fromisoformat(before) + timedelta(days=3))
    monkeypatch.setattr(prices, "last_finished_day", lambda now=None: date.fromisoformat(newer))
    monkeypatch.setattr(refresh, "can_fetch", lambda: "")
    runs = []

    def fake_build(cmd, **kw):
        runs.append(cmd)
        assert "--refresh" in cmd and kw["cwd"] == str(config.ROOT)
        _real_copy(demo_db, cmd[cmd.index("--out") + 1], as_of=newer)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(refresh.subprocess, "run", fake_build)
    assert refresh.status()["behind"] is True
    refresh.tick()
    _wait()
    s = refresh.status()
    assert len(runs) == 1 and s["as_of"] == newer and s["behind"] is False and s["state"] == "idle"
    assert data.db().path == real_db and not data.pending_files()      # the new file replaced the old one
    assert data.db().rows("SELECT count(*) AS n FROM companies")[0]["n"] > 0
    refresh._last_check = 0.0
    refresh.tick()                                                         # now current: nothing more to do
    _wait()
    assert len(runs) == 1


def test_failed_or_empty_updates_are_reported_and_not_repeated(real_db, monkeypatch):
    before = data.db().meta()["as_of"]
    monkeypatch.setattr(prices, "last_finished_day", lambda now=None: date.fromisoformat(before) + timedelta(days=1))
    monkeypatch.setattr(refresh, "can_fetch", lambda: "")
    runs = []

    def no_new_prices(cmd, **kw):       # a market holiday: the build finds nothing newer and writes no file
        runs.append(cmd)
        kw["stdout"].write("Prices are already current.\n")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(refresh.subprocess, "run", no_new_prices)
    refresh.tick()
    _wait()
    s = refresh.status()
    assert s["state"] == "idle" and "No newer prices" in s["message"] and s["as_of"] == before
    refresh._last_check = 0.0
    refresh.tick()                      # same day, minutes later: wait instead of trying again
    _wait()
    assert len(runs) == 1

    def broken(cmd, **kw):
        runs.append(cmd)
        kw["stdout"].write("Build stopped: data.alpaca.markets refused the request (HTTP 403).\n")
        return subprocess.CompletedProcess(cmd, 1)

    (config.CACHE_DIR / "refresh.json").unlink()
    monkeypatch.setattr(refresh.subprocess, "run", broken)
    refresh._last_check = 0.0
    refresh.tick()
    _wait()
    s = refresh.status()
    assert s["state"] == "failed" and "HTTP 403" in s["message"] and data.db().meta()["as_of"] == before


def test_no_update_without_keys_on_demo_data_or_when_turned_off(real_db, demo_db, monkeypatch):
    before = data.db().meta()["as_of"]
    monkeypatch.setattr(prices, "last_finished_day", lambda now=None: date.fromisoformat(before) + timedelta(days=1))
    monkeypatch.setattr(refresh.subprocess, "run", lambda *a, **k: pytest.fail("should not run"))
    monkeypatch.setattr(config, "PRICE_PROVIDER", "alpaca")
    monkeypatch.setattr(config, "ALPACA_API_KEY", "")
    refresh.tick()
    assert refresh.status()["state"] == "idle" and "ALPACA_API_KEY" in refresh.status()["message"]
    monkeypatch.setattr(refresh, "can_fetch", lambda: "")
    monkeypatch.setenv("AUTO_REFRESH", "0")
    refresh._last_check = 0.0
    refresh.tick()
    monkeypatch.delenv("AUTO_REFRESH")
    monkeypatch.setenv("K_SERVICE", "tickertutor")       # on Cloud Run a scheduled job does this instead
    refresh._last_check = 0.0
    refresh.tick()
    assert refresh.enabled() is False
    monkeypatch.delenv("K_SERVICE")
    data.set_db(demo_db)                                  # synthetic demo data never updates
    refresh._last_check = 0.0
    refresh.tick()
    assert refresh.status()["behind"] is False


def test_refreshed_file_left_behind_is_picked_up_at_the_next_start(real_db, demo_db):
    data.set_db(None)
    stale = _real_copy(demo_db, real_db.with_name("tickertutor.new-100.duckdb"), as_of="2020-01-01")
    os.utime(stale, (1, 1))                               # older than the main file: a leftover, not an update
    newer = _real_copy(demo_db, real_db.with_name("tickertutor.new-200.duckdb"), as_of="2099-01-04")
    (real_db.with_name("tickertutor.new-300.tmp.duckdb")).write_bytes(b"half written")
    assert data.pending_files() == [newer] and not stale.exists() and data.newest_file() == newer
    assert data.db().meta()["as_of"] == "2099-01-04"
    assert data.db().path == real_db and not newer.exists()


def test_data_status_endpoint(demo_db):
    from fastapi.testclient import TestClient

    import app as app_module

    s = TestClient(app_module.app).get("/api/data-status").json()
    assert s["as_of"] and s["expected"] and s["behind"] is False and s["state"] == "idle"
