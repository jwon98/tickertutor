"""How we decide whether a signal "worked": honest statistics for overlapping,
correlated stock returns.

The question for every signal is the same: in the months when it was on for a
stock, did that stock beat the S&P 500 over the following year more often (and by
more) than stocks where it was off?

Two problems make naive statistics overconfident:
  1. Stocks move together. 400 stocks in the same month aren't 400 independent
     data points. So we first summarize each month (the on-minus-off difference
     that month), then do statistics across months.
  2. 1-year returns measured every month overlap: January's next-12-months and
     February's share 11 months. So the margin of error comes from a block
     bootstrap that resamples 12-month blocks, which keeps that overlap intact.

The most recent third of months is held out: a signal only "held up" if its
direction is the same there as over the whole period.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BLOCK = 12          # months per bootstrap block (the forward-return horizon)
B = 2000            # bootstrap resamples
MIN_MONTHS = 24
MIN_EFFECT = 0.01   # under 1 point a year of extra return we call it no meaningful edge


def block_bootstrap_ci(x: np.ndarray, block: int = BLOCK, reps: int = B, alpha: float = 0.05,
                       seed: int = 7) -> tuple[float, float]:
    """Moving-block bootstrap CI for the mean of a time series."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")
    block = max(1, min(block, n // 2 or 1))
    rng = np.random.default_rng(seed)
    starts_max = n - block + 1
    k = int(np.ceil(n / block))
    starts = rng.integers(0, starts_max, size=(reps, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, -1)[:, :n]
    means = x[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def monthly_comparison(df: pd.DataFrame, flag: str, outcome: str = "excess_12m", beat: str = "beat_12m",
                       min_group: int = 5) -> pd.DataFrame:
    """Per month: mean outcome and beat rate for stocks with the flag on vs off."""
    d = df[[ "date", flag, outcome, beat]].dropna()
    if d.empty:
        return pd.DataFrame(columns=["date", "n_on", "n_off", "on_mean", "off_mean", "on_hit", "off_hit"])
    d = d.assign(on=d[flag].astype(bool))
    g = d.groupby(["date", "on"]).agg(n=(outcome, "size"), mean=(outcome, "mean"), hit=(beat, "mean")).unstack("on")
    out = pd.DataFrame({
        "n_on": g[("n", True)] if ("n", True) in g else 0, "n_off": g[("n", False)] if ("n", False) in g else 0,
        "on_mean": g[("mean", True)] if ("mean", True) in g else np.nan,
        "off_mean": g[("mean", False)] if ("mean", False) in g else np.nan,
        "on_hit": g[("hit", True)] if ("hit", True) in g else np.nan,
        "off_hit": g[("hit", False)] if ("hit", False) in g else np.nan,
    }).fillna({"n_on": 0, "n_off": 0}).reset_index()
    return out[(out["n_on"] >= min_group) & (out["n_off"] >= min_group)].sort_values("date").reset_index(drop=True)


def verdict(n_months: int, diff: float, lo: float, hi: float, oos_diff: float | None) -> str:
    if n_months < MIN_MONTHS or np.isnan(diff):
        return "too_little_data"
    significant = not (np.isnan(lo) or np.isnan(hi)) and (lo > 0 or hi < 0)
    if not significant or abs(diff) < MIN_EFFECT:
        return "no_clear_edge"
    same_direction = oos_diff is not None and not np.isnan(oos_diff) and np.sign(oos_diff) == np.sign(diff)
    if not same_direction:
        return "mixed"
    return "held_up" if diff > 0 else "worse"


VERDICT_TEXT = {
    "held_up": "Held up: stocks with this signal beat the others, including in the held-out recent years.",
    "worse": "Worse: stocks with this signal did worse than the others, including recently.",
    "mixed": "Mixed: a difference over the full period, but it didn't hold in the recent held-out years.",
    "no_clear_edge": "No clear edge: the difference is too small or too uncertain to rely on.",
    "too_little_data": "Too little data to say.",
}


def report_card(df: pd.DataFrame, flag: str, holdout_frac: float = 1 / 3, min_group: int = 5) -> dict:
    """Track record of one signal (see module docstring)."""
    m = monthly_comparison(df, flag, min_group=min_group)
    n_months = len(m)
    base = df[["excess_12m", "beat_12m"]].dropna()
    out = {"n_months": n_months, "n_obs": int(df[[flag, "excess_12m"]].dropna().shape[0]),
           "hit_all": float(base["beat_12m"].mean()) if len(base) else float("nan")}
    if n_months == 0:
        out.update({"verdict": "too_little_data", "diff": float("nan")})
        return out
    d = (m["on_mean"] - m["off_mean"]).to_numpy()
    h = (m["on_hit"] - m["off_hit"]).to_numpy()
    lo, hi = block_bootstrap_ci(d)
    hlo, hhi = block_bootstrap_ci(h)
    cut = int(round(n_months * (1 - holdout_frac)))
    is_d = float(np.nanmean(d[:cut])) if cut > 0 else float("nan")
    oos_d = float(np.nanmean(d[cut:])) if cut < n_months else float("nan")
    diff = float(np.nanmean(d))
    out.update({
        "period_start": m["date"].iloc[0], "period_end": m["date"].iloc[-1],
        "on_share": float((m["n_on"] / (m["n_on"] + m["n_off"])).mean()),
        "avg_on": float(m["n_on"].mean()),
        "excess_on": float(m["on_mean"].mean()), "excess_off": float(m["off_mean"].mean()),
        "hit_on": float(m["on_hit"].mean()), "hit_off": float(m["off_hit"].mean()),
        "diff": diff, "diff_lo": lo, "diff_hi": hi,
        "hit_diff": float(np.nanmean(h)), "hit_diff_lo": hlo, "hit_diff_hi": hhi,
        "is_diff": is_d, "oos_diff": oos_d, "oos_start": m["date"].iloc[cut] if cut < n_months else None,
        "verdict": verdict(n_months, diff, lo, hi, oos_d),
    })
    return out


def group_stats(values: np.ndarray, clusters: np.ndarray | None = None, reps: int = B, seed: int = 11) -> dict:
    """Mean and share-positive of event outcomes with a cluster bootstrap CI
    (events in the same month are resampled together)."""
    v = np.asarray(values, dtype=float)
    keep = ~np.isnan(v)
    v = v[keep]
    if len(v) == 0:
        return {"n": 0}
    if clusters is None:
        clusters = np.arange(len(v))
    else:
        clusters = np.asarray(clusters)[keep]
    uniq, inv = np.unique(clusters, return_inverse=True)
    rng = np.random.default_rng(seed)
    sums = np.bincount(inv, weights=v, minlength=len(uniq))
    pos = np.bincount(inv, weights=(v > 0).astype(float), minlength=len(uniq))
    cnt = np.bincount(inv, minlength=len(uniq)).astype(float)
    picks = rng.integers(0, len(uniq), size=(reps, len(uniq)))
    boot_mean = sums[picks].sum(axis=1) / cnt[picks].sum(axis=1)
    boot_pos = pos[picks].sum(axis=1) / cnt[picks].sum(axis=1)
    return {"n": int(len(v)), "clusters": int(len(uniq)), "mean": float(v.mean()), "pct_positive": float((v > 0).mean()),
            "mean_lo": float(np.quantile(boot_mean, 0.025)), "mean_hi": float(np.quantile(boot_mean, 0.975)),
            "pos_lo": float(np.quantile(boot_pos, 0.025)), "pos_hi": float(np.quantile(boot_pos, 0.975))}
