"""The database layer: safe SQL for the agents, ticker checks, and the computed tables."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tickertutor import data
from tickertutor.build.compute import SIGNALS, tidy_name
from tickertutor.data import DataError, run_sql, ticker_or_error


@pytest.mark.parametrize("query", [
    "DROP TABLE prices",
    "SELECT 1; DROP TABLE prices",
    "SELECT * FROM read_csv('/etc/passwd')",
    "COPY prices TO 'x.csv'",
    "ATTACH 'other.db'",
    "PRAGMA database_list",
    "WITH x AS (SELECT 1) INSERT INTO prices SELECT * FROM x",
    "SELECT * FROM glob('*')",
    "",
])
def test_sql_blocks_anything_but_reads(demo_db, query):
    with pytest.raises(DataError):
        run_sql(query)


def test_sql_reads_and_caps_rows(demo_db):
    out = run_sql("SELECT ticker, ret_1y FROM snapshot ORDER BY ret_1y DESC")
    assert out["columns"] == ["ticker", "ret_1y"]
    assert 0 < len(out["rows"]) <= 200
    big = run_sql("SELECT * FROM prices")
    assert len(big["rows"]) == 200 and big.get("truncated")


def test_sql_errors_are_actionable(demo_db):
    with pytest.raises(DataError, match="(?i)column|table|binder|catalog"):
        run_sql("SELECT no_such_column FROM snapshot")


def test_ticker_checks(demo_db):
    assert ticker_or_error("brk-b") == "BRK.B"
    with pytest.raises(DataError, match="Did you mean AAPL"):
        ticker_or_error("apple")
    with pytest.raises(DataError, match="only covers current S&P 500"):
        ticker_or_error("GME")
    with pytest.raises(DataError, match="valid ticker"):
        ticker_or_error("not a ticker!")


def test_clean_handles_missing_values():
    assert data.clean({"a": pd.NaT, "b": float("nan"), "c": pd.Timestamp("2026-10-30")}) == {
        "a": None, "b": None, "c": "2026-10-30"}


def test_tidy_names():
    assert tidy_name("Coca-Cola Company (The)") == "The Coca-Cola Company"
    assert tidy_name("Lilly (Eli)") == "Eli Lilly"
    assert tidy_name("Alphabet Inc. (Class A)") == "Alphabet Inc. (Class A)"


# --- the computed database ------------------------------------------------------------------------------------

def test_tables_and_meta(demo_db):
    db = data.db()
    for t in ("meta", "companies", "prices", "snapshot", "panel", "fundamentals", "signal_cards", "sectors", "events",
              "recent_moves", "earnings", "filings", "news", "membership", "index_changes"):
        assert t in db.tables(), t
    m = db.meta()
    assert m["synthetic"] is True and m["as_of"]
    assert "checklist" not in m


def test_every_signal_has_a_report_card(demo_db):
    cards = data.db().rows("SELECT * FROM signal_cards WHERE universe = 'All'")
    ids = {c["signal_id"] for c in cards}
    assert {s[0] for s in SIGNALS} == ids
    for c in cards:
        assert c["verdict"] in {"held_up", "worse", "mixed", "no_clear_edge", "too_little_data"}
        if c["verdict"] != "too_little_data":
            assert c["diff_lo"] <= c["diff"] <= c["diff_hi"]
            assert 0 <= c["hit_on"] <= 1 and 0 <= c["hit_off"] <= 1
            assert c["oos_start"] > c["period_start"]


def test_snapshot_sanity(demo_db):
    rows = data.db().rows("SELECT * FROM snapshot")
    for r in rows:
        if r["pct_up_1y"] is not None:
            assert 0 <= r["pct_up_1y"] <= 1 and r["worst_1y"] <= r["median_1y"] <= r["best_1y"]
        if r["max_drawdown"] is not None:
            assert -1 < r["max_drawdown"] <= 0


def test_backtest_is_point_in_time(demo_db):
    db = data.db()
    # Former members appear in the panel while they were members, and not after they left.
    left = db.rows("SELECT ticker, \"end\" FROM membership WHERE \"end\" IS NOT NULL AND ticker LIKE 'DEMO%'")
    assert left
    for r in left:
        late = db.rows("SELECT count(*) AS n FROM panel WHERE ticker = ? AND date > ?", [r["ticker"], r["end"]])[0]["n"]
        early = db.rows("SELECT count(*) AS n FROM panel WHERE ticker = ? AND date < ?", [r["ticker"], r["end"]])[0]["n"]
        assert late == 0 and early > 0
    # A company added later (TSLA in the demo) isn't in the panel before it joined.
    first = db.rows("SELECT min(date) AS d FROM panel WHERE ticker = 'TSLA'")[0]["d"]
    assert str(first) >= "2020-12-21"
    # Outcomes need a full year after the as-of date: the newest rows have none.
    last = db.rows("SELECT max(date) AS d FROM panel WHERE excess_12m IS NOT NULL")[0]["d"]
    assert str(last) <= str(pd.Timestamp(db.meta()["as_of"]) - pd.Timedelta(days=360))[:10]


def test_no_blue_chip_or_checklist_columns(demo_db):
    cols = {r["column_name"] for r in data.db().rows("SELECT column_name FROM information_schema.columns")}
    assert not {c for c in cols if "blue" in c or "checklist" in c or c.startswith("chk_")}


def test_write_db_handles_empty_and_mixed_tables(tmp_path):
    from datetime import date as d

    import duckdb as ddb

    from tickertutor.build.compute import write_db
    tables = {
        "index_changes": pd.DataFrame(),                         # no rows, no columns
        "news": pd.DataFrame(),
        "mixed": pd.DataFrame({"a": ["x", 1, None, 2.5], "b": [[1, 2], [], None, ["z"]], "c": [d(2020, 1, 1), None, d(2021, 5, 2), None],
                               "e": [None, None, None, None]}),
    }
    path = write_db(tables, tmp_path / "t.duckdb")
    con = ddb.connect(str(path), read_only=True)
    assert [r[0] for r in con.execute("describe index_changes").fetchall()][:3] == ["date", "added", "added_name"]
    assert con.execute("select count(*) from news").fetchone()[0] == 0
    assert con.execute("select a, b from mixed order by rowid").fetchall()[0] == ("x", "[1, 2]")
    con.close()
