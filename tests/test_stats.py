"""Indicators, the backtest statistics, and the one-year date rule."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from tickertutor import indicators as ind
from tickertutor import stats
from tickertutor.data import long_term_date


def series(values, start="2020-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_moving_average_and_returns():
    s = series(range(1, 301))
    assert ind.sma(s, 200).iloc[-1] == pytest.approx(np.mean(range(101, 301)))
    assert np.isnan(ind.sma(s, 200).iloc[198])
    assert ind.ret(s, 1).iloc[-1] == pytest.approx(300 / 299 - 1)


def test_rsi_extremes():
    up = series(np.arange(1, 60, dtype=float))
    down = series(np.arange(60, 1, -1, dtype=float))
    assert ind.rsi(up).iloc[-1] > 95
    assert ind.rsi(down).iloc[-1] < 5


def test_drawdown_and_recovery():
    s = series([100, 110, 120, 90, 60, 80, 121, 125])
    d = ind.drawdowns(s)
    assert d["max_drawdown"] == pytest.approx(60 / 120 - 1)
    assert d["peak_date"] == s.index[2] and d["trough_date"] == s.index[4]
    assert d["recovered_date"] == s.index[6]
    assert d["current_drawdown"] == pytest.approx(0)


def test_drawdown_not_recovered():
    d = ind.drawdowns(series([100, 50, 70]))
    assert d["recovered_date"] is None and d["current_drawdown"] == pytest.approx(-0.3)


def test_holding_odds_counts_every_window():
    s = series(np.linspace(100, 200, 400))   # always rising
    h = ind.holding_odds(s, n=252)
    assert h["windows"] == 400 - 252 and h["pct_positive"] == 1.0 and h["worst"] > 0


def test_block_bootstrap_covers_the_mean():
    rng = np.random.default_rng(0)
    x = 0.05 + rng.normal(0, 0.1, 150)
    lo, hi = stats.block_bootstrap_ci(x)
    assert lo < x.mean() < hi and lo > 0


@pytest.mark.parametrize("args, expected", [
    ((10, 0.05, 0.02, 0.08, 0.04), "too_little_data"),
    ((60, 0.004, 0.001, 0.008, 0.004), "no_clear_edge"),     # significant but under 1 point a year
    ((60, 0.03, -0.01, 0.07, 0.03), "no_clear_edge"),       # range includes zero
    ((60, 0.03, 0.01, 0.05, -0.02), "mixed"),               # faded in the held-out years
    ((60, 0.03, 0.01, 0.05, 0.02), "held_up"),
    ((60, -0.03, -0.05, -0.01, -0.02), "worse"),
])
def test_verdict_rules(args, expected):
    assert stats.verdict(*args) == expected


def panel(effect: float, months=120, per_month=60, seed=1):
    """A fake monthly panel: half the stocks have the flag; flagged ones get `effect` extra return."""
    rng = np.random.default_rng(seed)
    rows = []
    dates = pd.date_range("2012-01-31", periods=months, freq="ME")
    for d in dates:
        common = rng.normal(0, 0.05)    # month-wide noise, so months aren't independent draws
        for i in range(per_month):
            on = i % 2 == 0
            ex = common + rng.normal(0, 0.25) + (effect if on else 0)
            rows.append({"date": d, "flag": on, "excess_12m": ex, "beat_12m": float(ex > 0)})
    return pd.DataFrame(rows)


def test_report_card_finds_a_real_edge():
    card = stats.report_card(panel(0.06), "flag")
    assert card["verdict"] == "held_up"
    assert card["diff_lo"] < 0.06 < card["diff_hi"]
    assert card["hit_on"] > card["hit_off"]


def test_report_card_on_noise_finds_nothing():
    card = stats.report_card(panel(0.0, seed=3), "flag")
    assert card["verdict"] in ("no_clear_edge", "mixed")


def test_report_card_needs_enough_months():
    card = stats.report_card(panel(0.06, months=12), "flag")
    assert card["verdict"] == "too_little_data"


def test_group_stats_cluster_bootstrap():
    v = np.array([0.1, 0.12, 0.08, -0.05, 0.2, 0.15])
    g = stats.group_stats(v, clusters=np.array([1, 1, 2, 3, 3, 4]))
    assert g["n"] == 6 and g["clusters"] == 4
    assert g["mean_lo"] <= g["mean"] <= g["mean_hi"]
    assert g["pct_positive"] == pytest.approx(5 / 6)


@pytest.mark.parametrize("bought, first_long_term_day", [
    (date(2026, 3, 3), date(2027, 3, 4)),
    (date(2025, 12, 31), date(2027, 1, 1)),
    (date(2024, 2, 29), date(2025, 3, 1)),     # leap day: anniversary falls back to Feb 28
])
def test_long_term_date(bought, first_long_term_day):
    assert long_term_date(bought) == first_long_term_day
