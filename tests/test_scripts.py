"""The helper scripts, offline."""

from __future__ import annotations

import sys

from scripts import baseline_compare


def test_baseline_compare_fills_the_readme_block(fake_llm, monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("intro\n<!-- baseline:start -->\nold\n<!-- baseline:end -->\noutro\n", encoding="utf-8")
    monkeypatch.setattr(baseline_compare, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["baseline_compare.py", "--only", "1"])
    baseline_compare.main()
    text = readme.read_text(encoding="utf-8")
    assert text.startswith("intro\n") and text.rstrip().endswith("outro") and "\nold\n" not in text
    assert "Ticker Tutor's answer" in text and "Same model, no tools" in text and "tool calls" in text
    assert (tmp_path / "docs" / "baseline.md").exists()


def test_build_refresh_stops_early_when_prices_are_current(demo_db, monkeypatch, tmp_path, capsys):
    """`build_data.py --refresh` is what the app runs each day. With nothing newer to fetch it leaves the data alone."""
    from scripts import build_data
    from tickertutor import config, data
    from tickertutor.build import demo, fetch

    as_of = data.db().meta()["as_of"]
    monkeypatch.setattr(config, "DB_PATH", demo_db)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    out = tmp_path / "next.duckdb"
    monkeypatch.setattr(sys, "argv", ["build_data.py", "--refresh", "--out", str(out)])
    assert build_data.current_as_of() == as_of

    monkeypatch.setattr(build_data, "newest_price_day", lambda start, provider: as_of)
    monkeypatch.setattr(fetch, "fetch_raw", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not download")))
    build_data.main()
    assert "already current" in capsys.readouterr().out and not out.exists()

    seen = {}

    def fake_fetch(*a, **k):
        seen.update(k)
        return demo.generate()

    monkeypatch.setattr(build_data, "newest_price_day", lambda start, provider: "2099-01-04")
    monkeypatch.setattr(fetch, "fetch_raw", fake_fetch)
    build_data.main()
    assert seen["refresh"] is True and out.exists() and "Updating from" in capsys.readouterr().out
