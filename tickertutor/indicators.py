"""The indicators traders look at most, computed from daily prices.

All functions take a pandas Series of prices indexed by date (oldest first) and
return a Series aligned to it. "adj" means prices adjusted for splits and
dividends (so returns include dividends).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def sma(s: pd.Series, n: int) -> pd.Series:
    """Simple moving average over n trading days (needs a full window)."""
    return s.rolling(n, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing). Above 70 is often called
    'overbought', below 30 'oversold'."""
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(avg_loss != 0, 100.0).where(avg_gain.notna())


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, and histogram (line − signal)."""
    line = s.ewm(span=fast, adjust=False).mean() - s.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def ret(s: pd.Series, n: int) -> pd.Series:
    """Return over the past n trading days."""
    return s / s.shift(n) - 1


def momentum_12_1(s: pd.Series) -> pd.Series:
    """Return from 12 months ago to 1 month ago: the classic momentum measure,
    which skips the latest month (very recent winners tend to dip back)."""
    return s.shift(21) / s.shift(TRADING_DAYS) - 1


def high_low_distance(s: pd.Series, n: int = TRADING_DAYS) -> tuple[pd.Series, pd.Series]:
    """How far below the n-day high, and above the n-day low (fractions)."""
    hi = s.rolling(n, min_periods=int(n * 0.8)).max()
    lo = s.rolling(n, min_periods=int(n * 0.8)).min()
    return s / hi - 1, s / lo - 1


def volatility(s: pd.Series, n: int = TRADING_DAYS) -> pd.Series:
    """Annualized standard deviation of daily returns over n days."""
    return s.pct_change().rolling(n, min_periods=int(n * 0.8)).std() * np.sqrt(TRADING_DAYS)


def beta(s: pd.Series, market: pd.Series, n: int = TRADING_DAYS) -> pd.Series:
    """How much the stock tends to move when the market moves 1% (rolling)."""
    r, m = s.pct_change(), market.pct_change()
    cov = r.rolling(n, min_periods=int(n * 0.8)).cov(m)
    var = m.rolling(n, min_periods=int(n * 0.8)).var()
    return cov / var


def drawdowns(s: pd.Series) -> dict:
    """Largest peak-to-trough drop, when it happened, and whether/when it recovered."""
    s = s.dropna()
    if s.empty:
        return {}
    peak = s.cummax()
    dd = s / peak - 1
    trough = dd.idxmin()
    peak_date = s.loc[:trough].idxmax()
    after = s.loc[trough:]
    recovered = after[after >= s.loc[peak_date]]
    rec_date = recovered.index[0] if not recovered.empty else None
    return {
        "max_drawdown": float(dd.min()), "peak_date": peak_date, "trough_date": trough,
        "recovered_date": rec_date,
        "days_to_recover": int(pd.Timedelta(rec_date - trough).days) if rec_date is not None and hasattr(rec_date - trough, "days") else None,
        "current_drawdown": float(dd.iloc[-1]),
    }


def holding_odds(s: pd.Series, n: int = TRADING_DAYS) -> dict:
    """Over every n-day holding period in the history: how often it ended up,
    plus the best, worst, and median outcomes. Descriptive, not a forecast."""
    s = s.dropna()
    if len(s) <= n + 20:
        return {}
    fwd = (s.shift(-n) / s - 1).dropna()
    return {"windows": int(len(fwd)), "pct_positive": float((fwd > 0).mean()), "best": float(fwd.max()),
            "worst": float(fwd.min()), "median": float(fwd.median()), "start": fwd.index[0], "end": fwd.index[-1]}
