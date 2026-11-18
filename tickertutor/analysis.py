"""The analyses a beginner can run on any stock, over any period.

Each analysis returns chart panels (for the Analyze page), a few summary numbers, a plain-language
readout of what the numbers say, and an explanation of what the statistic is and how to read it.
The research agents call the same code through the `run_analysis` tool, so the page and the agents
always agree.

Indicators are computed on the full price history and then cut to the chosen dates, so a 200-day
average is already "warmed up" on the first day of the period. Prices are adjusted for splits and
dividends.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import indicators as ind
from . import indexes
from .data import DataError, db, last_day, ticker_or_error
from .sources.prices import BENCHMARK, SECTOR_ETFS

TD = ind.TRADING_DAYS
MAX_POINTS = 1300            # points drawn per line; statistics always use every day
PERIODS = {"1m": ("1 month", 31), "3m": ("3 months", 92), "6m": ("6 months", 183), "ytd": ("Year to date", None),
           "1y": ("1 year", 365), "3y": ("3 years", 365 * 3), "5y": ("5 years", 365 * 5), "max": ("All available", None)}


@dataclass
class Param:
    id: str
    label: str
    default: int | float
    min: float = 1
    max: float = 500
    choices: list[tuple[int, str]] = field(default_factory=list)
    help: str = ""

    def public(self) -> dict:
        out = {"id": self.id, "label": self.label, "default": self.default, "min": self.min, "max": self.max,
               "help": self.help}
        if self.choices:
            out["choices"] = [{"value": v, "label": lbl} for v, lbl in self.choices]
        return out

    def parse(self, raw) -> float | int:
        if raw in (None, ""):
            return self.default
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise DataError(f"{self.label} must be a number.") from None
        if self.choices:
            allowed = [c for c, _ in self.choices]
            if v not in allowed:
                raise DataError(f"{self.label} must be one of: {', '.join(lbl for _, lbl in self.choices)}.")
        elif not (self.min <= v <= self.max):
            raise DataError(f"{self.label} must be between {self.min:g} and {self.max:g}.")
        return int(v) if float(v).is_integer() else v


# --- formatting for readouts -------------------------------------------------------------------------------

def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def pct(v, d: int = 1, sign: bool = False) -> str:
    if not _ok(v):
        return "n/a"
    s = f"{v * 100:.{d}f}"
    if float(s) == 0:
        s = f"{0:.{d}f}"
    return f"{'+' if sign and v > 0 and float(s) != 0 else ''}{s}%"


def num(v, d: int = 2) -> str:
    if not _ok(v):
        return "n/a"
    s = f"{v:,.{d}f}"
    return s[1:] if s.startswith("-") and float(s.replace(",", "")) == 0 else s


def money(v) -> str:
    return f"${v:,.2f}" if _ok(v) else "n/a"


def day(d) -> str:
    if d is None:
        return "n/a"
    d = pd.Timestamp(d)
    return f"{d:%b} {d.day}, {d.year}"


def item(label: str, value, fmt: str, note: str = "") -> dict:
    """A summary number. fmt: pct | pct_signed | num | num0 | money | ratio | date | text | days."""
    v = None if not _ok(value) and fmt not in ("date", "text") else value
    if fmt == "date" and v is not None:
        v = str(pd.Timestamp(v).date())
    text = {"pct": lambda: pct(v), "pct_signed": lambda: pct(v, 1, True), "num": lambda: num(v),
            "num0": lambda: num(v, 0), "money": lambda: money(v), "ratio": lambda: f"{num(v)}×",
            "date": lambda: day(v), "text": lambda: str(v), "days": lambda: f"{int(v):,} days"}[fmt]() if v is not None else "n/a"
    return {"label": label, "value": v, "fmt": fmt, "text": text, "note": note}


# --- the context each analysis works from ---------------------------------------------------------------------

class Ctx:
    def __init__(self, ticker: str, name: str, sector: str, px: pd.Series, volume: pd.Series, spy: pd.Series,
                 sector_px: pd.Series | None, start: pd.Timestamp, end: pd.Timestamp, params: dict,
                 others: dict[str, pd.Series] | None = None):
        self.ticker, self.name, self.sector = ticker, name, sector
        self.px, self.volume, self.spy, self.sector_px = px, volume, spy, sector_px
        self.start, self.end, self.p = start, end, params
        self.mask = (px.index >= start) & (px.index <= end)
        self.idx = px.index[self.mask]
        self.index = indexes.get(ticker)       # set when the subject is an index fund, not a company
        self.others = others or {}             # the other index funds, for comparing one index with the rest
        self.is_spy = ticker == BENCHMARK      # comparing SPY with the S&P 500 would compare it with itself

    def w(self, s: pd.Series) -> pd.Series:
        """Cut a full-history series to the chosen dates."""
        return s.reindex(self.idx)

    @property
    def n(self) -> int:
        return len(self.idx)


def _cross_markers(fast: pd.Series, slow: pd.Series, up: str, down: str, panel: int = 0) -> list[dict]:
    diff = (fast - slow).dropna()
    sign = np.sign(diff)
    flips = sign[(sign != sign.shift(1)) & sign.shift(1).notna() & (sign != 0)]
    return [{"date": str(d.date()), "label": up if v > 0 else down, "kind": "up" if v > 0 else "down", "panel": panel}
            for d, v in flips.items()]


def _price_panel(c: Ctx, extra: list[dict] | None = None, band: dict | None = None, height: int = 250) -> dict:
    title = (f"{c.ticker} price (the fund that tracks the {c.index['name']}, adjusted for dividends)" if c.index
             else f"{c.ticker} price (adjusted for splits and dividends)")
    return {"title": title, "height": height, "y": {"fmt": "money"},
            "series": [{"key": "price", "label": f"{c.ticker} price", "color": "ink"}, *(extra or [])], "band": band}


# --- the analyses ---------------------------------------------------------------------------------------------

def _moving_averages(c: Ctx) -> dict:
    a, b = int(c.p["short"]), int(c.p["long"])
    if a >= b:
        raise DataError("The short average needs fewer days than the long average.")
    sa, sb = ind.sma(c.px, a), ind.sma(c.px, b)
    price, wa, wb = c.w(c.px), c.w(sa), c.w(sb)
    last, la, lb = price.iloc[-1], wa.iloc[-1], wb.iloc[-1]
    markers = [m for m in _cross_markers(sa, sb, "Golden cross", "Death cross") if c.start <= pd.Timestamp(m["date"]) <= c.end]
    all_cross = _cross_markers(sa, sb, "Golden cross", "Death cross")
    last_cross = next((m for m in reversed(all_cross) if pd.Timestamp(m["date"]) <= c.end), None)
    above = (price > wb)[wb.notna()]
    summary = [
        item(f"Price vs {a}-day average", last / la - 1 if _ok(la) else None, "pct_signed"),
        item(f"Price vs {b}-day average", last / lb - 1 if _ok(lb) else None, "pct_signed"),
        item(f"Days above the {b}-day average", above.mean() if len(above) else None, "pct", "share of days in this period"),
        item("Crossovers in this period", len(markers), "num0", "times the two averages crossed"),
        item("Latest crossover", last_cross["date"] if last_cross else None, "date", last_cross["label"] if last_cross else ""),
    ]
    if _ok(la) and _ok(lb):
        rel = "above" if la > lb else "below"
        cross_txt = (f" It has been {rel} since {day(last_cross['date'])} (a {last_cross['label'].lower()})."
                     if last_cross else "")
        readout = (f"On {day(c.end)}, {c.ticker} closed {pct(abs(last / la - 1))} {'above' if last > la else 'below'} its "
                   f"{a}-day average and {pct(abs(last / lb - 1))} {'above' if last > lb else 'below'} its {b}-day average. "
                   f"The {a}-day average is {rel} the {b}-day.{cross_txt} Over this period the price closed above its "
                   f"{b}-day average on {pct(above.mean(), 0)} of trading days, and the two averages crossed "
                   f"{len(markers)} time{'s' if len(markers) != 1 else ''}.")
    else:
        readout = f"There isn't enough price history before this period to compute a {b}-day average yet."
    return {"panels": [_price_panel(c, [{"key": "ma_short", "label": f"{a}-day average", "color": "gold"},
                                        {"key": "ma_long", "label": f"{b}-day average", "color": "grey"}])],
            "data": {"price": price, "ma_short": wa, "ma_long": wb}, "markers": markers,
            "summary": summary, "readout": readout}


def _trendline(c: Ctx) -> dict:
    price = c.w(c.px).dropna()
    if len(price) < 40:
        raise DataError("A trend line needs at least 40 trading days. Pick a longer period.")
    x = np.arange(len(price), dtype=float)
    y = np.log(price.to_numpy())
    slope, intercept = np.polyfit(x, y, 1)
    fit = intercept + slope * x
    resid = y - fit
    sd = resid.std(ddof=2)
    r2 = 1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum()
    growth = math.exp(slope * TD) - 1
    z_now = resid[-1] / sd if sd else float("nan")
    gap = math.exp(resid[-1]) - 1
    outside = float((np.abs(resid) > 2 * sd).mean())
    trend = pd.Series(np.exp(fit), index=price.index)
    lo, hi = pd.Series(np.exp(fit - 2 * sd), index=price.index), pd.Series(np.exp(fit + 2 * sd), index=price.index)
    fit_word = "very closely" if r2 >= 0.9 else "fairly closely" if r2 >= 0.7 else "loosely" if r2 >= 0.4 else "poorly"
    summary = [
        item("Trend growth rate", growth, "pct_signed", "per year, along the fitted line"),
        item("R² (how well a line fits)", r2, "num", "0 = no fit, 1 = perfect"),
        item("Price vs the trend line now", gap, "pct_signed"),
        item("Distance from the line now", z_now, "num", "in standard deviations"),
        item("Days outside the band", outside, "pct", "beyond ±2 standard deviations"),
    ]
    readout = (f"A straight-line trend through {c.ticker}'s price from {day(price.index[0])} to {day(price.index[-1])} "
               f"{'rises' if growth >= 0 else 'falls'} at about {pct(abs(growth), 1)} a year. The line fits {fit_word} "
               f"(R² = {r2:.2f}). Today's price is {pct(abs(gap))} {'above' if gap >= 0 else 'below'} the line, "
               f"{abs(z_now):.1f} standard deviations away. Try other start dates: the slope can change a lot.")
    return {"panels": [_price_panel(c, [{"key": "trend", "label": "Trend line", "color": "blue", "style": "dash"}],
                                    band={"lo": "band_lo", "hi": "band_hi", "label": "±2 standard deviations"})],
            "data": {"price": c.w(c.px), "trend": trend.reindex(c.idx), "band_lo": lo.reindex(c.idx),
                     "band_hi": hi.reindex(c.idx)},
            "summary": summary, "readout": readout}


def _macd(c: Ctx) -> dict:
    f, s, g = int(c.p["fast"]), int(c.p["slow"]), int(c.p["signal"])
    if f >= s:
        raise DataError("The fast average needs fewer days than the slow average.")
    line, sig, hist = ind.macd(c.px, f, s, g)
    wl, ws, wh = c.w(line), c.w(sig), c.w(hist)
    markers = [{**m, "panel": 1} for m in _cross_markers(line, sig, "MACD crossed above signal", "MACD crossed below signal")
               if c.start <= pd.Timestamp(m["date"]) <= c.end]
    last = markers[-1] if markers else None
    summary = [
        item("MACD now", wl.iloc[-1], "num", "dollars"),
        item("Signal line now", ws.iloc[-1], "num"),
        item("Histogram now", wh.iloc[-1], "num", "MACD − signal"),
        item("Days with MACD above zero", (wl > 0).mean(), "pct"),
        item("Signal-line crossovers", len(markers), "num0", "in this period"),
    ]
    readout = (f"MACD is {num(wl.iloc[-1])}, {'above' if wl.iloc[-1] > ws.iloc[-1] else 'below'} its signal line "
               f"({num(ws.iloc[-1])}), and {'above' if wl.iloc[-1] > 0 else 'below'} zero, which means the {f}-day "
               f"average is {'above' if wl.iloc[-1] > 0 else 'below'} the {s}-day. "
               + (f"The latest crossover was on {day(last['date'])} ({last['label'].replace('MACD ', '')}). " if last else "")
               + f"MACD crossed its signal line {len(markers)} times in this period, which gives a sense of how often "
               f"it flips in practice.")
    return {"panels": [_price_panel(c, height=210),
                       {"title": f"MACD ({f}, {s}, {g})", "height": 160, "y": {"fmt": "num", "zero": True},
                        "series": [{"key": "hist", "label": "Histogram", "color": "faint", "style": "bar"},
                                   {"key": "macd", "label": "MACD", "color": "blue"},
                                   {"key": "signal", "label": "Signal", "color": "gold"}],
                        "hlines": [{"y": 0}]}],
            "data": {"price": c.w(c.px), "macd": wl, "signal": ws, "hist": wh}, "markers": markers,
            "summary": summary, "readout": readout}


def _rsi(c: Ctx) -> dict:
    n, hi, lo = int(c.p["window"]), float(c.p["upper"]), float(c.p["lower"])
    if lo >= hi:
        raise DataError("The oversold line needs to be below the overbought line.")
    r = c.w(ind.rsi(c.px, n))
    now = r.iloc[-1]
    zone = "overbought" if now > hi else "oversold" if now < lo else "neutral"
    zone_txt = (f"above the {hi:g} 'overbought' line" if now > hi else f"below the {lo:g} 'oversold' line" if now < lo
                else f"between {lo:g} and {hi:g}, the neutral range")
    below = r[r < lo]
    summary = [
        item(f"RSI ({n}-day) now", now, "num0", zone),
        item(f"Days above {hi:g}", (r > hi).mean(), "pct", "'overbought'"),
        item(f"Days below {lo:g}", (r < lo).mean(), "pct", "'oversold'"),
        item("Average RSI in this period", r.mean(), "num0"),
        item(f"Last day below {lo:g}", below.index[-1] if len(below) else None, "date", "" if len(below) else "not in this period"),
    ]
    readout = (f"{c.ticker}'s {n}-day RSI is {num(now, 0)}, {zone_txt}. Over this period it was above "
               f"{hi:g} on {pct((r > hi).mean(), 0)} of days and below {lo:g} on {pct((r < lo).mean(), 0)}.")
    return {"panels": [_price_panel(c, height=210),
                       {"title": f"RSI ({n}-day)", "height": 150, "y": {"fmt": "num0", "min": 0, "max": 100},
                        "series": [{"key": "rsi", "label": "RSI", "color": "blue"}],
                        "hlines": [{"y": hi, "label": f"{hi:g} overbought"}, {"y": lo, "label": f"{lo:g} oversold"},
                                   {"y": 50, "style": "faint"}]}],
            "data": {"price": c.w(c.px), "rsi": r}, "summary": summary, "readout": readout}


def _momentum(c: Ctx) -> dict:
    n = int(c.p["lookback"])
    roc, spy_roc = c.w(ind.ret(c.px, n)), c.w(ind.ret(c.spy, n))
    now, spy_now = roc.iloc[-1], spy_roc.iloc[-1]
    rank = (roc.dropna() < now).mean() if roc.notna().any() and _ok(now) else None
    summary = [
        item(f"{n}-day change now", now, "pct_signed"),
        *([] if c.is_spy else [
            item(f"S&P 500, same {n} days", spy_now, "pct_signed"),
            item("Gap vs the S&P 500", now - spy_now if _ok(now) and _ok(spy_now) else None, "pct_signed", "percentage points")]),
        item("Days with positive momentum", (roc > 0)[roc.notna()].mean() if roc.notna().any() else None, "pct"),
        item("Higher than", rank, "pct", "of readings in this period"),
    ]
    readout = (f"Over the last {n} trading days {c.ticker} is {'up' if now >= 0 else 'down'} {pct(abs(now))}"
               + ("" if c.is_spy else f", vs {pct(spy_now, 1, True)} for the S&P 500")
               + f". Today's reading is higher than {pct(rank, 0)} of the readings in this period."
               if _ok(now) else f"Not enough history for a {n}-day lookback yet.")
    series = [{"key": "roc", "label": c.ticker, "color": "blue"}]
    data = {"price": c.w(c.px), "roc": roc}
    if not c.is_spy:
        series.append({"key": "spy_roc", "label": "S&P 500 (SPY)", "color": "grey", "style": "dash"})
        data["spy_roc"] = spy_roc
    return {"panels": [_price_panel(c, height=210),
                       {"title": f"Rate of change over {n} trading days", "height": 160, "y": {"fmt": "pct", "zero": True},
                        "series": series, "hlines": [{"y": 0}]}],
            "data": data, "summary": summary, "readout": readout}


def _volatility(c: Ctx) -> dict:
    n = int(c.p["window"])
    v = c.w(c.px.pct_change().rolling(n, min_periods=n).std() * math.sqrt(TD))
    sv = c.w(c.spy.pct_change().rolling(n, min_periods=n).std() * math.sqrt(TD))
    r = c.w(c.px.pct_change()).dropna()
    rs = c.w(c.spy.pct_change()).dropna()
    whole, whole_spy = r.std() * math.sqrt(TD), rs.std() * math.sqrt(TD)
    peak_day = v.idxmax() if v.notna().any() else None
    summary = [
        item("Volatility over the period", whole, "pct", "annualized"),
        *([] if c.is_spy else [
            item("S&P 500, same period", whole_spy, "pct"),
            item("Compared with the S&P 500", whole / whole_spy if whole_spy else None, "ratio")]),
        item("Typical daily move", r.std(), "pct", "one standard deviation"),
        item(f"Highest {n}-day reading", v.max(), "pct", day(peak_day) if peak_day is not None else ""),
    ]
    readout = (f"Over this period {c.ticker}'s daily returns had an annualized volatility of {pct(whole, 0)}"
               + ("" if c.is_spy else f", {num(whole / whole_spy, 1) if whole_spy else 'n/a'}× the S&P 500's {pct(whole_spy, 0)}")
               + f". A typical day moved about ±{pct(r.std())}. Its {n}-day volatility peaked at {pct(v.max(), 0)} around "
               f"{day(peak_day)} and is {pct(v.iloc[-1], 0)} now.")
    series = [{"key": "vol", "label": c.ticker, "color": "blue"}]
    data = {"price": c.w(c.px), "vol": v}
    if not c.is_spy:
        series.append({"key": "spy_vol", "label": "S&P 500 (SPY)", "color": "grey", "style": "dash"})
        data["spy_vol"] = sv
    return {"panels": [_price_panel(c, height=200),
                       {"title": f"Rolling {n}-day volatility (annualized)", "height": 170, "y": {"fmt": "pct", "min": 0},
                        "series": series}],
            "data": data, "summary": summary, "readout": readout}


def _bollinger(c: Ctx) -> dict:
    n, k = int(c.p["window"]), float(c.p["k"])
    mid = c.px.rolling(n, min_periods=n).mean()
    sd = c.px.rolling(n, min_periods=n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    price, wm, wu, wl = c.w(c.px), c.w(mid), c.w(up), c.w(lo)
    pb = (price - wl) / (wu - wl)
    bw = (wu - wl) / wm
    valid = wm.notna()
    above, below = (price > wu)[valid].mean(), (price < wl)[valid].mean()
    summary = [
        item("%B now", pb.iloc[-1], "num", "0 = lower band, 1 = upper band"),
        item("Band width now", bw.iloc[-1], "pct", "of the middle band"),
        item("Typical band width", bw.median(), "pct", "median in this period"),
        item("Days above the upper band", above, "pct"),
        item("Days below the lower band", below, "pct"),
    ]
    squeeze = bw.iloc[-1] < 0.75 * bw.median() if _ok(bw.iloc[-1]) and _ok(bw.median()) else False
    readout = (f"{c.ticker} is at %B {num(pb.iloc[-1])}: "
               + ("above the upper band. " if pb.iloc[-1] > 1 else "below the lower band. " if pb.iloc[-1] < 0
                  else f"{'in the upper half' if pb.iloc[-1] >= 0.5 else 'in the lower half'} of its bands. ")
               + f"The bands are {pct(bw.iloc[-1])} wide vs a typical {pct(bw.median())} in this period"
               + (", narrower than usual (a 'squeeze'). " if squeeze else ". ")
               + f"It closed outside the bands on {pct(above + below, 0)} of days.")
    return {"panels": [_price_panel(c, [{"key": "mid", "label": f"{n}-day average", "color": "gold"}],
                                    band={"lo": "lower", "hi": "upper", "label": f"±{k:g} standard deviations"}, height=280)],
            "data": {"price": price, "mid": wm, "upper": wu, "lower": wl}, "summary": summary, "readout": readout}


def _dd_stats(s: pd.Series) -> dict:
    s = s.dropna()
    peak = s.cummax()
    dd = s / peak - 1
    trough = dd.idxmin()
    peak_date = s.loc[:trough].idxmax()
    rec = s.loc[trough:][s.loc[trough:] >= s.loc[peak_date]]
    episodes, in_ep = 0, False
    for v in dd.to_numpy():
        if not in_ep and v <= -0.10:
            episodes, in_ep = episodes + 1, True
        elif in_ep and v >= 0:
            in_ep = False
    return {"dd": dd, "peak": peak, "max": float(dd.min()), "peak_date": peak_date, "trough": trough,
            "recovered": rec.index[0] if len(rec) else None, "now": float(dd.iloc[-1]), "episodes": episodes}


def _drawdown(c: Ctx) -> dict:
    d = _dd_stats(c.w(c.px))
    sd = _dd_stats(c.w(c.spy))
    if d["max"] == 0:
        rec_txt = "It never fell below a previous high in this period."
    else:
        rec_txt = (f"It got back to that high on {day(d['recovered'])}, {(d['recovered'] - d['trough']).days} days after the low."
                   if d["recovered"] is not None else "It hadn't recovered to that high by the end of the period.")
    summary = [
        item("Biggest drop from a high", d["max"], "pct", f"{day(d['peak_date'])} → {day(d['trough'])}"),
        *([] if c.is_spy else [item("S&P 500's biggest drop, same dates", sd["max"], "pct")]),
        item("Back to the old high", d["recovered"], "date", "" if d["recovered"] is not None else "not yet"),
        item("Below its high now", d["now"], "pct"),
        item("Separate drops of 10%+", d["episodes"], "num0", "in this period"),
    ]
    readout = (f"Measured from the highest price within this period, {c.ticker}'s worst drop was {pct(abs(d['max']), 0)}, "
               f"from {day(d['peak_date'])} to {day(d['trough'])}. "
               + ("" if c.is_spy else f"The S&P 500's worst drop over the same dates was {pct(abs(sd['max']), 0)}. ")
               + f"{rec_txt} It is {pct(abs(d['now']), 0)} below its high now.")
    dd_series = [{"key": "dd", "label": c.ticker, "color": "down", "style": "area"}]
    if not c.is_spy:
        dd_series.append({"key": "spy_dd", "label": "S&P 500 (SPY)", "color": "grey", "style": "dash"})
    return {"panels": [_price_panel(c, [{"key": "peak", "label": "Highest so far", "color": "grey", "style": "dash"}],
                                    height=210),
                       {"title": "Drawdown: % below the highest price so far", "height": 170, "y": {"fmt": "pct", "max": 0},
                        "series": dd_series}],
            "data": {"price": c.w(c.px), "peak": d["peak"].reindex(c.idx), "dd": d["dd"].reindex(c.idx),
                     "spy_dd": sd["dd"].reindex(c.idx)},
            "markers": [{"date": str(d["peak_date"].date()), "label": "Peak", "kind": "down", "panel": 0},
                        {"date": str(d["trough"].date()), "label": "Low", "kind": "up", "panel": 0}] if d["max"] < 0 else [],
            "summary": summary, "readout": readout}


def _beta(c: Ctx) -> dict:
    if c.is_spy:
        raise DataError("Beta measures how something moves with the S&P 500, and SPY is the S&P 500 fund, so its beta is "
                        "exactly 1 by definition. Try beta on QQQ, DIA, or IWM to see how another index moves with it.")
    n = int(c.p["window"])
    r, m = c.px.pct_change(), c.spy.pct_change()
    wr, wm = c.w(r), c.w(m)
    both = pd.concat([wr, wm], axis=1, keys=["r", "m"]).dropna()
    if len(both) < 40:
        raise DataError("Beta needs at least 40 trading days. Pick a longer period.")
    b = both["r"].cov(both["m"]) / both["m"].var()
    corr = both["r"].corr(both["m"])
    alpha_d = both["r"].mean() - b * both["m"].mean()
    down = both[both["m"] <= -0.01]
    upd = both[both["m"] >= 0.01]
    rolling = c.w(ind.beta(c.px, c.spy, n))
    pts = both.sample(n=min(len(both), 1500), random_state=0) if len(both) > 1500 else both
    summary = [
        item("Beta", b, "num", "vs the S&P 500"),
        item("Correlation", corr, "num", "−1 to 1"),
        item("R² (market's share of the moves)", corr ** 2, "pct"),
        item("On days the S&P 500 fell 1%+", down["r"].mean() if len(down) else None, "pct_signed",
             f"{c.ticker}'s average move ({len(down)} days)"),
        item("On days the S&P 500 rose 1%+", upd["r"].mean() if len(upd) else None, "pct_signed",
             f"{c.ticker}'s average move ({len(upd)} days)"),
    ]
    readout = (f"Over this period {c.ticker}'s beta was {num(b)}: when the S&P 500 moved 1%, {c.ticker} moved about "
               f"{num(b)}% in the same direction on average. The correlation is {num(corr)}, so the market lines up with "
               f"about {pct(corr ** 2, 0)} of its daily ups and downs. The rest is the company's own news and noise. "
               + (f"On the {len(down)} days the index fell 1% or more, {c.ticker} moved {pct(down['r'].mean(), 1, True)} on average."
                  if len(down) else ""))
    return {"panels": [{"title": f"Rolling beta ({n} trading days)", "height": 170, "y": {"fmt": "num"},
                        "series": [{"key": "beta", "label": "Beta", "color": "blue"}],
                        "hlines": [{"y": 1, "label": "1 = moves with the market"}, {"y": 0, "style": "faint"}]}],
            "data": {"beta": rolling},
            "extra": {"kind": "scatter", "title": "Each dot is one trading day", "fmt": "pct",
                      "x_label": "S&P 500 (SPY) daily return", "y_label": f"{c.ticker} daily return",
                      "points": [[round(float(x), 5), round(float(y), 5)] for x, y in zip(pts["m"], pts["r"])],
                      "fit": {"slope": float(b), "intercept": float(alpha_d)}},
            "summary": summary, "readout": readout}


def _relative_index(c: Ctx, cum) -> dict:
    """An index fund next to the other big indexes."""
    me = cum(c.px)
    years = (c.idx[-1] - c.idx[0]).days / 365.25
    ann = (lambda x: (1 + x) ** (1 / years) - 1) if years >= 1 else None
    rets = {c.ticker: me.iloc[-1]}
    series = [{"key": "me", "label": f"{c.index['name']} ({c.ticker})", "color": "ink"}]
    data = {"me": me}
    colors = {"SPY": "grey", "QQQ": "blue", "DIA": "gold", "IWM": "violet"}   # same color for an index on every chart
    for t, s in c.others.items():
        info = indexes.get(t)
        k = t.lower()
        data[k] = cum(s)
        rets[t] = data[k].iloc[-1]
        series.append({"key": k, "label": f"{info['name']} ({t})", "color": colors.get(t, "grey"),
                       **({"style": "dash"} if t == BENCHMARK else {})})
    summary = [item(f"{c.index['name']} ({c.ticker})", rets[c.ticker], "pct_signed",
                    f"{pct(ann(rets[c.ticker]), 1, True)} per year" if ann else "dividends included")]
    for t in c.others:
        summary.append(item(f"{indexes.get(t)['name']} ({t})", rets[t], "pct_signed",
                            f"{pct(ann(rets[t]), 1, True)} per year" if ann and _ok(rets[t]) else ""))
    ranked = sorted(((v, t) for t, v in rets.items() if _ok(v)), reverse=True)
    place = [t for _, t in ranked].index(c.ticker) + 1 if ranked else None
    words = {1: "first", 2: "second", 3: "third", 4: "fourth"}
    count = {2: "two", 3: "three", 4: "four"}
    rest = [f"the {indexes.get(t)['name']} {'returned ' if not i else ''}{pct(v, 1, True)}"
            for i, (t, v) in enumerate((t, v) for t, v in rets.items() if t != c.ticker and _ok(v))]
    listed = (", ".join(rest[:-1]) + (", and " if len(rest) > 2 else " and ") + rest[-1]) if len(rest) > 1 else "".join(rest)
    readout = (f"From {day(c.idx[0])} to {day(c.idx[-1])}, the {c.index['name']} fund ({c.ticker}) returned "
               f"{pct(rets[c.ticker], 1, True)} with dividends."
               + (f" Over the same dates, {listed}." if rest else "")
               + (f" That puts it {words.get(place, str(place))} of the {count.get(len(ranked), len(ranked))}." if place and len(ranked) > 1 else "")
               + (" Which index leads changes from period to period, so try a few different dates." if rest
                  else " The other index funds aren't in this database yet. Rerun the data build to compare them."))
    return {"panels": [{"title": "Return since the start of the period", "height": 280, "y": {"fmt": "pct", "zero": True},
                        "series": series, "hlines": [{"y": 0}]}],
            "data": data, "summary": summary, "readout": readout}


def _relative(c: Ctx) -> dict:
    def cum(s):
        s = c.w(s)
        first = s.dropna()
        return s / first.iloc[0] - 1 if len(first) else s * np.nan
    if c.index:
        return _relative_index(c, cum)
    stock, spy = cum(c.px), cum(c.spy)
    sec = cum(c.sector_px) if c.sector_px is not None else None
    etf = SECTOR_ETFS.get(c.sector)
    years = (c.idx[-1] - c.idx[0]).days / 365.25
    t_ret, s_ret = stock.iloc[-1], spy.iloc[-1]
    ann = (lambda x: (1 + x) ** (1 / years) - 1) if years >= 1 else None
    ahead = (stock > spy).mean()
    summary = [
        item(f"{c.ticker} total return", t_ret, "pct_signed", "dividends included"),
        item("S&P 500 total return", s_ret, "pct_signed"),
        item("Difference", t_ret - s_ret, "pct_signed", "percentage points"),
        item(f"Sector fund ({etf})" if etf else "Sector fund", sec.iloc[-1] if sec is not None else None, "pct_signed", c.sector),
        item("Per year" if ann else "Days ahead of the S&P 500", ann(t_ret) if ann else ahead, "pct_signed" if ann else "pct",
             f"S&P 500 {pct(ann(s_ret), 1, True)}" if ann else "share of days with a bigger gain so far"),
    ]
    readout = (f"From {day(c.idx[0])} to {day(c.idx[-1])}, {c.ticker} returned {pct(t_ret, 1, True)} with dividends, vs "
               f"{pct(s_ret, 1, True)} for the S&P 500"
               + (f" and {pct(sec.iloc[-1], 1, True)} for its sector fund ({etf})" if sec is not None else "")
               + f": {'ahead of' if t_ret >= s_ret else 'behind'} the index by {pct(abs(t_ret - s_ret))} points.")
    series = [{"key": "stock", "label": c.ticker, "color": "ink"},
              {"key": "spy", "label": "S&P 500 (SPY)", "color": "grey", "style": "dash"}]
    data = {"stock": stock, "spy": spy}
    if sec is not None:
        series.append({"key": "sector", "label": f"{c.sector} ({etf})", "color": "gold"})
        data["sector"] = sec
    return {"panels": [{"title": "Return since the start of the period", "height": 280, "y": {"fmt": "pct", "zero": True},
                        "series": series, "hlines": [{"y": 0}]}],
            "data": data, "summary": summary, "readout": readout}


def _rolling_returns(c: Ctx) -> dict:
    n = int(c.p["window"])
    rr, srr = c.w(ind.ret(c.px, n)), c.w(ind.ret(c.spy, n))
    ok = rr.notna()
    if ok.sum() < 5:
        raise DataError(f"Not enough history for {n}-day windows in this period. Pick a longer period or a shorter window.")
    beat = (rr > srr)[ok & srr.notna()]
    best_d, worst_d = rr.idxmax(), rr.idxmin()
    label = dict(ROLLING_CHOICES).get(n, f"{n} days")
    sp = not c.is_spy
    summary = [
        item("Windows ending in this period", int(ok.sum()), "num0", f"each {label} long"),
        item("Ended with a gain", (rr[ok] > 0).mean(), "pct", f"S&P 500: {pct((srr.dropna() > 0).mean(), 0)}" if sp else ""),
        *([item("Beat the S&P 500", beat.mean() if len(beat) else None, "pct")] if sp else []),
        item("Typical (median)", rr[ok].median(), "pct_signed", f"S&P 500: {pct(srr.dropna().median(), 1, True)}" if sp else ""),
        item("Best / worst", None, "text", f"{pct(rr.max(), 0, True)} ({day(best_d)}) / {pct(rr.min(), 0, True)} ({day(worst_d)})"),
    ]
    summary[-1]["value"] = summary[-1]["text"] = f"{pct(rr.max(), 0, True)} / {pct(rr.min(), 0, True)}"
    readout = (f"Of the {int(ok.sum()):,} holding periods of {label} ending between {day(c.idx[0])} and {day(c.idx[-1])}, "
               f"{pct((rr[ok] > 0).mean(), 0)} ended with a gain"
               + (f" (S&P 500: {pct((srr.dropna() > 0).mean(), 0)}) and {pct(beat.mean(), 0)} beat the index" if sp else "")
               + f". Results ranged from {pct(rr.min(), 0, True)} to {pct(rr.max(), 0, True)}, "
               f"so timing mattered. Neighboring windows overlap almost completely, so these aren't independent results.")
    series = [{"key": "rr", "label": c.ticker, "color": "blue"}]
    data = {"rr": rr}
    if sp:
        series.append({"key": "spy_rr", "label": "S&P 500 (SPY)", "color": "grey", "style": "dash"})
        data["spy_rr"] = srr
    return {"panels": [{"title": f"Return over the previous {label}, on each day", "height": 280, "y": {"fmt": "pct", "zero": True},
                        "series": series, "hlines": [{"y": 0}]}],
            "data": data, "summary": summary, "readout": readout}


def _returns_distribution(c: Ctx) -> dict:
    h = int(c.p["horizon"])
    s = c.w(c.px).dropna()
    r = (s.iloc[::h].pct_change().dropna()) if h > 1 else s.pct_change().dropna()
    if len(r) < 12:
        raise DataError("Too few returns to draw a distribution. Pick a longer period or a shorter horizon.")
    mu, sd = r.mean(), r.std()
    skew, kurt = float(r.skew()), float(r.kurt())
    beyond = int((np.abs(r - mu) > 3 * sd).sum())
    expected = len(r) * 0.0027
    nb = int(min(40, max(10, round(math.sqrt(len(r)) * 1.5))))
    counts, edges = np.histogram(r, bins=nb)
    width = edges[1] - edges[0]
    xs = np.linspace(edges[0], edges[-1], 80)
    normal = len(r) * width * np.exp(-0.5 * ((xs - mu) / sd) ** 2) / (sd * math.sqrt(2 * math.pi))
    label = dict(HORIZON_CHOICES).get(h, f"{h}-day")
    summary = [
        item(f"{label.capitalize()} returns", len(r), "num0", "non-overlapping" if h > 1 else ""),
        item("Average", mu, "pct_signed"),
        item("Standard deviation", sd, "pct"),
        item("Skewness", skew, "num", "0 for a bell curve"),
        item("Excess kurtosis", kurt, "num", "0 for a bell curve, higher = fatter tails"),
        item("Moves beyond 3 standard deviations", beyond, "num0", f"a bell curve would expect about {expected:.1f}"),
    ]
    readout = (f"{len(r):,} {label} returns: average {pct(mu, 2, True)}, standard deviation {pct(sd, 2)}, "
               f"{pct((r > 0).mean(), 0)} positive. Best {pct(r.max(), 1, True)}, worst {pct(r.min(), 1, True)}. "
               f"There were {beyond} moves beyond 3 standard deviations where a bell curve expects about {expected:.1f}"
               + (", so extreme days were more common than the normal model predicts (fatter tails)." if beyond > expected * 2 and beyond >= 2 else ".")
               + f" Skewness {skew:.2f}{' (the big moves have leaned down)' if skew < -0.3 else ' (the big moves have leaned up)' if skew > 0.3 else ''}.")
    return {"panels": [],
            "data": {},
            "extra": {"kind": "histogram", "title": f"How often each {label} return happened", "fmt": "pct",
                      "bins": [[float(edges[i]), float(edges[i + 1]), int(counts[i])] for i in range(nb)],
                      "normal": [[float(x), float(y)] for x, y in zip(xs, normal)], "mean": float(mu), "sd": float(sd)},
            "summary": summary, "readout": readout}


def _volume(c: Ctx) -> dict:
    n = int(c.p["window"])
    v = c.volume.reindex(c.px.index)
    avg = v.rolling(n, min_periods=max(5, n // 2)).mean()
    wv, wa = c.w(v), c.w(avg)
    if wv.dropna().sum() == 0:
        raise DataError(f"No trading volume data for {c.ticker}.")
    ret1 = c.w(c.px.pct_change())
    top = wv.nlargest(3)
    recent = wv.tail(5).mean()
    summary = [
        item("Average daily volume", wv.mean(), "num0", "shares, this period"),
        item("Last 5 days vs average", recent / wa.iloc[-1] if _ok(wa.iloc[-1]) and wa.iloc[-1] else None, "ratio",
             f"vs the {n}-day average"),
        *[item(f"Heavy day #{i + 1}", d, "date", f"{wv[d] / wa[d]:.1f}× average, price {pct(ret1[d], 1, True)}"
               if _ok(wa[d]) and wa[d] else "") for i, d in enumerate(top.index)],
    ]
    readout = (f"{c.ticker} traded {num(wv.mean(), 0)} shares a day on average in this period. The last five days ran "
               f"{num(recent / wa.iloc[-1], 1) if _ok(wa.iloc[-1]) and wa.iloc[-1] else 'n/a'}× its {n}-day average. "
               f"The heaviest day was {day(top.index[0])}, when the price moved {pct(ret1[top.index[0]], 1, True)}.")
    return {"panels": [_price_panel(c, height=210),
                       {"title": "Shares traded per day", "height": 160, "y": {"fmt": "big", "min": 0},
                        "series": [{"key": "volume", "label": "Volume", "color": "faint", "style": "bar"},
                                   {"key": "avg", "label": f"{n}-day average", "color": "gold"}]}],
            "data": {"price": c.w(c.px), "volume": wv, "avg": wa}, "summary": summary, "readout": readout}


ROLLING_CHOICES = [(21, "1 month"), (63, "3 months"), (126, "6 months"), (252, "1 year"), (756, "3 years")]
HORIZON_CHOICES = [(1, "daily"), (5, "weekly"), (21, "monthly")]

GROUPS = ["Trend", "Momentum", "Volatility & risk", "Returns", "Trading activity"]

ANALYSES: dict[str, dict] = {
    "moving_averages": {
        "name": "Moving averages", "group": "Trend", "fn": _moving_averages, "signals": ["above_200d", "golden_cross"],
        "short": "The average price over the last N days, and where today's price sits against it.",
        "params": [Param("short", "Short average (days)", 50, 5, 250), Param("long", "Long average (days)", 200, 20, 400)],
        "explain": {
            "what": "A moving average is the average closing price over the last N trading days, recalculated every day. "
                    "It smooths out daily noise so the overall direction is easier to see. The 50-day and 200-day averages "
                    "are the most watched: the 50-day reflects roughly the last two to three months, the 200-day roughly the "
                    "last ten months (a year has about 252 trading days).",
            "how": "For each day, add up the last N closing prices and divide by N. The line starts only once there are N "
                   "days of history. Ticker Tutor uses prices adjusted for splits and dividends.",
            "read": "Price above a rising 200-day average is the most common definition of an uptrend, and price below a "
                    "falling one a downtrend. When the shorter average crosses above the longer one it's called a golden "
                    "cross, and crossing below is a death cross. How far the price is from an average shows how stretched it is "
                    "from its recent norm.",
            "watch": "Moving averages lag: they confirm a move only after it has happened, so crossovers often come late. "
                     "In sideways, choppy markets the lines cross back and forth (whipsaws). They describe the past and "
                     "don't predict the next move."}},
    "trendline": {
        "name": "Trend line (regression)", "group": "Trend", "fn": _trendline, "signals": [],
        "short": "A best-fit straight line through the period: its growth rate and how well it fits.",
        "params": [],
        "explain": {
            "what": "A straight line fitted through the price over the period you pick, on a percentage scale. It "
                    "summarizes the overall direction and pace in one number: the growth rate per year along the line.",
            "how": "An ordinary least-squares regression of the natural log of price on time. Using logs means the line "
                   "measures percentage growth, so a move from $10 to $20 counts the same as $100 to $200. The shaded "
                   "band is the line ± 2 standard deviations of the gaps between the price and the line. R² is the share "
                   "of the variation in log price that the line accounts for.",
            "read": "The growth rate is the period's average pace. R² near 1 means the price followed a steady path, and "
                    "near 0 means a straight line explains little. Price well above the band means the stock has run ahead "
                    "of its own trend for this period. Well below means it has fallen behind.",
            "watch": "The line depends heavily on the start and end dates, so try a few. Daily prices aren't independent of "
                     "each other, so R² can look impressive even for a random path, and the usual regression p-values "
                     "would be misleading here. A trend line describes a past period. Prices don't have to return to it."}},
    "macd": {
        "name": "MACD", "group": "Trend", "fn": _macd, "signals": [],
        "short": "The gap between a fast and a slow average, to see if a trend is speeding up or fading.",
        "params": [Param("fast", "Fast average (days)", 12, 2, 100), Param("slow", "Slow average (days)", 26, 5, 200),
                   Param("signal", "Signal line (days)", 9, 2, 50)],
        "explain": {
            "what": "Moving Average Convergence Divergence tracks the gap between a fast and a slow moving average to "
                    "show momentum: whether a trend is gaining or losing strength.",
            "how": "MACD line = 12-day exponential moving average (EMA) − 26-day EMA. The signal line is a 9-day EMA of the "
                   "MACD line, and the histogram is MACD − signal. An EMA gives recent days more weight than older ones.",
            "read": "MACD above zero means the faster average is above the slower one (upward momentum), and below zero "
                    "the opposite. MACD crossing above its signal line is a commonly cited 'bullish' sign, and crossing below "
                    "a 'bearish' one. A shrinking histogram means the move is losing steam.",
            "watch": "It's built from moving averages, so it lags too, and it crosses often when prices go sideways. "
                     "MACD is measured in dollars, so you can't compare its level across stocks with different prices. "
                     "It was designed for short-term trading."}},
    "rsi": {
        "name": "RSI", "group": "Momentum", "fn": _rsi, "signals": ["rsi_oversold"],
        "short": "Recent gains vs recent losses on a 0–100 scale. The classic overbought/oversold gauge.",
        "params": [Param("window", "Look-back (days)", 14, 2, 100), Param("upper", "Overbought line", 70, 50, 95),
                   Param("lower", "Oversold line", 30, 5, 50)],
        "explain": {
            "what": "The Relative Strength Index measures how strong recent gains have been compared with recent losses, "
                    "on a scale from 0 to 100.",
            "how": "Over the look-back (14 days by default), compare the average size of up days with the average size of "
                   "down days: RSI = 100 − 100 ÷ (1 + average gain ÷ average loss), using Wilder's smoothing. Only gains "
                   "gives 100, and only losses gives 0.",
            "read": "Above 70 is traditionally called overbought (risen a lot, quickly) and below 30 oversold (fallen a "
                    "lot, quickly). 50 is neutral. In strong uptrends RSI can stay above 70 for weeks, which reflects "
                    "strength rather than a guaranteed pullback.",
            "watch": "Overbought doesn't mean the price must fall, and oversold doesn't mean it must rise. RSI was "
                     "designed for short-term trading, and the 70/30 lines are conventions, not laws."}},
    "momentum": {
        "name": "Momentum (rate of change)", "group": "Momentum", "fn": _momentum, "signals": ["momentum_top30"],
        "short": "How much the price changed over a look-back, compared with the S&P 500.",
        "params": [Param("lookback", "Look-back (trading days)", 126, 5, 504, help="21 ≈ 1 month, 126 ≈ 6 months, 252 ≈ 1 year")],
        "explain": {
            "what": "Rate of change is the percentage the price moved over a fixed look-back, recalculated every day. "
                    "It's the simplest measure of momentum.",
            "how": "Rate of change = today's price ÷ the price N trading days ago − 1. The same is shown for the S&P 500 "
                   "(SPY), so you can separate the stock's own momentum from the market's.",
            "read": "Above zero means the price is higher than N days ago, and the further from zero, the stronger the move. "
                    "Studies across thousands of stocks have found that stocks with strong 6–12 month returns have, on "
                    "average, kept doing a little better for some months afterwards (the 'momentum effect'), usually "
                    "measured skipping the most recent month.",
            "watch": "Momentum can reverse sharply, especially when the market turns. The research effect is an average "
                     "over many stocks. For one stock it's a noisy signal. Results change a lot with the look-back."}},
    "volatility": {
        "name": "Volatility", "group": "Volatility & risk", "fn": _volatility, "signals": ["low_volatility"],
        "short": "How much the price swings day to day, the most common measure of risk.",
        "params": [Param("window", "Rolling window (days)", 21, 5, 252, help="21 ≈ 1 month")],
        "explain": {
            "what": "Volatility measures how much the price swings from day to day. It's the most widely used measure of "
                    "risk.",
            "how": "Take the daily percentage changes, compute their standard deviation, and multiply by √252 to express "
                   "it per year. The line uses a rolling window (21 trading days ≈ one month by default). The same is "
                   "shown for the S&P 500.",
            "read": "20% annual volatility means a typical day moves about 1.3% (20% ÷ √252). The S&P 500's long-run "
                    "volatility has been roughly 15–20%, and many individual stocks run higher. Volatility clusters: calm and "
                    "stormy stretches each tend to last a while, and spikes usually come with falling markets.",
            "watch": "Volatility counts up and down moves the same, so it isn't the same as the chance of losing money. "
                     "It's backward-looking and can jump in a crisis. Short windows react fast but are noisy."}},
    "bollinger": {
        "name": "Bollinger Bands", "group": "Volatility & risk", "fn": _bollinger, "signals": [],
        "short": "An envelope around a moving average that widens when prices are volatile.",
        "params": [Param("window", "Average (days)", 20, 5, 200), Param("k", "Width (standard deviations)", 2, 1, 4)],
        "explain": {
            "what": "Bollinger Bands draw an envelope around a moving average that widens when the price is volatile and "
                    "narrows when it's calm.",
            "how": "Middle band = 20-day simple moving average. Upper and lower bands = middle ± 2 × the standard "
                   "deviation of the last 20 closing prices. %B shows where the price sits: 0 at the lower band, 1 at "
                   "the upper band.",
            "read": "Near the upper band, the price is high relative to its recent range, and near the lower band, low. A "
                    "'squeeze' (bands unusually narrow) marks a quiet stretch, which is often followed by a bigger move, "
                    "in either direction.",
            "watch": "Touching a band isn't a buy or sell signal by itself: in strong trends prices can ride along a band "
                     "for weeks. Stock prices have fatter tails than a bell curve, so closes outside the bands happen "
                     "more often than the textbook 5%."}},
    "drawdown": {
        "name": "Drawdowns", "group": "Volatility & risk", "fn": _drawdown, "signals": ["big_dip", "near_52w_high"],
        "short": "How far the price fell from its highs, and how long recovery took.",
        "params": [],
        "explain": {
            "what": "A drawdown is how far the price is below its highest point so far. The maximum drawdown is the worst "
                    "peak-to-low drop: the biggest loss someone who bought at the top would have sat through.",
            "how": "For each day: price ÷ the highest price so far in the period − 1. The lower chart (an 'underwater' "
                   "chart) shows this every day, and 0% means a new high. Recovery is the first day the price got back to "
                   "the old peak.",
            "read": "Maximum drawdown and recovery time show what the bad stretches felt like. Compare with the S&P 500 "
                    "over the same dates: a stock that fell 50% while the index fell 25% was about twice as painful.",
            "watch": "It's measured from the highest price within your dates, so a period that starts after a peak can "
                     "hide an earlier drop. Past drawdowns aren't a floor. The next one can be bigger."}},
    "beta": {
        "name": "Beta & correlation", "group": "Volatility & risk", "fn": _beta, "signals": [],
        "short": "How much the stock has tended to move when the whole market moves.",
        "params": [Param("window", "Rolling window", 126, choices=[(63, "3 months"), (126, "6 months"), (252, "1 year")])],
        "explain": {
            "what": "Beta measures how much a stock has tended to move when the overall market moves. Correlation "
                    "measures how consistently it moves with the market.",
            "how": "Each dot is one trading day: the S&P 500's daily return (using SPY) across, the stock's down. Beta is "
                   "the slope of the best-fit line (covariance ÷ the market's variance). Correlation runs from −1 to 1. "
                   "R² (correlation squared) is the share of the stock's daily moves that line up with the market's.",
            "read": "Beta 1: moved with the market one-for-one on average. 1.5: about 50% more, in both directions. 0.5: "
                    "about half as much. A low R² means most of the stock's movement is its own (company news) rather "
                    "than the market's, so beta tells less of the story.",
            "watch": "Beta shifts over time (see the rolling line) and depends on the period. It captures only the "
                     "average, straight-line relationship, so a low-beta stock can still fall hard on its own news."}},
    "relative": {
        "name": "Performance vs the S&P 500", "group": "Returns", "fn": _relative, "signals": ["strong_vs_sector"],
        "short": "Total return over your dates next to the S&P 500 and the stock's sector.",
        "params": [],
        "explain": {
            "what": "Shows how much the stock gained or lost over your dates compared with the S&P 500 and with its "
                    "sector, all starting from 0% on the first day.",
            "how": "Return on each day = price that day ÷ price on the first day − 1, using prices adjusted for dividends "
                   "and splits, so dividends count. The S&P 500 is represented by SPY and the sector by its SPDR sector "
                   "fund (for example XLK for technology).",
            "read": "The gap at the end is how far the stock beat or lagged the index. Comparing with the sector helps "
                    "separate what was specific to the company from what happened to its whole industry.",
            "watch": "The answer depends a lot on the start date, so try a few. Per-year figures are shown only for "
                     "periods of a year or more. Beating the index in the past doesn't mean it will keep doing so."}},
    "rolling_returns": {
        "name": "Rolling returns", "group": "Returns", "fn": _rolling_returns, "signals": [],
        "short": "Every holding period of a chosen length: how often it gained and the range of outcomes.",
        "params": [Param("window", "Holding period", 252, choices=ROLLING_CHOICES)],
        "explain": {
            "what": "Instead of one return from one start date, rolling returns look at every holding period of a given "
                    "length: how often holding that long ended in a gain, and the range from best to worst.",
            "how": "For each day in your dates, the return over the previous N trading days (252 ≈ 1 year). The same is "
                   "computed for the S&P 500.",
            "read": "The share of windows with a gain and the spread between best and worst show how much results "
                    "depended on timing. For broad indexes, longer holding periods have historically had fewer losing "
                    "stretches. Single stocks can stay down for years.",
            "watch": "Neighboring windows overlap almost entirely, so the counts look like more evidence than they are. "
                     "This describes the stock's past only."}},
    "returns_distribution": {
        "name": "Return distribution", "group": "Returns", "fn": _returns_distribution, "signals": [],
        "short": "A histogram of daily, weekly, or monthly returns against the bell curve.",
        "params": [Param("horizon", "Return length", 1, choices=HORIZON_CHOICES)],
        "explain": {
            "what": "A histogram of the stock's returns over your dates (daily, weekly, or monthly), compared with the "
                    "bell curve (normal distribution) that many textbook models assume.",
            "how": "Weekly and monthly returns use back-to-back, non-overlapping blocks of 5 or 21 trading days. The curve "
                   "is a normal distribution with the same average and standard deviation. Skewness measures "
                   "lopsidedness, and excess kurtosis measures fat tails (both are 0 for a bell curve).",
            "read": "Most returns cluster near zero. More moves beyond 3 standard deviations than the bell curve expects "
                    "(and positive excess kurtosis) means big surprises happen more often than a normal model suggests. "
                    "Negative skew means the extreme moves have leaned toward drops.",
            "watch": "With few observations (say, monthly returns over one year) the shape is mostly noise. The past "
                     "distribution doesn't set future odds."}},
    "volume": {
        "name": "Trading volume", "group": "Trading activity", "fn": _volume, "signals": [],
        "short": "Shares traded each day, and the days with unusually heavy trading.",
        "params": [Param("window", "Average (days)", 50, 5, 200)],
        "explain": {
            "what": "Volume is the number of shares traded each day. It shows how much activity is behind a price move.",
            "how": "Bars are daily shares traded, and the line is the rolling average. Spikes are unusually heavy days, often "
                   "around earnings reports, big news, or index changes.",
            "read": "A big price move on heavy volume is often treated as more meaningful than one on light volume. "
                    "Comparing recent volume with its average shows whether activity is picking up.",
            "watch": "Volume levels depend on the data source (some free feeds count only part of the market's trades) "
                     "and on the share price, so compare a stock with its own history rather than with other stocks."}},
}


# When the subject is an index fund, "relative" compares it with the other big indexes instead of with the
# S&P 500 and a sector, so it gets its own name and explanation.
INDEX_RELATIVE = {
    "name": "Performance vs the other indexes",
    "short": "Total return over your dates next to the other big US indexes.",
    "explain": {
        "what": "Shows how much this index gained or lost over your dates next to the other three big US indexes, all "
                "starting from 0% on the first day.",
        "how": "Return on each day = the fund's price that day ÷ its price on the first day − 1, using prices adjusted "
               "for dividends. Each index is represented by a large fund that tracks it: SPY for the S&P 500, QQQ for "
               "the Nasdaq-100, DIA for the Dow, and IWM for the Russell 2000.",
        "read": "The gaps show which slice of the market did better over these dates: large US companies (S&P 500), "
                "the biggest Nasdaq companies, which lean toward technology (Nasdaq-100), 30 well-known companies "
                "(Dow), or smaller companies (Russell 2000).",
        "watch": "Leadership rotates. Smaller companies and technology have each led for years at a time and then "
                 "lagged for years. The answer depends a lot on the start date, so try a few."},
}


def catalog() -> list[dict]:
    """What the Analyze page lists: every analysis with its parameters and explanation."""
    return [{"id": k, "name": a["name"], "group": a["group"], "short": a["short"],
             "params": [p.public() for p in a["params"]], "explain": a["explain"], "signals": a["signals"]}
            for k, a in ANALYSES.items()]


def _series(ticker: str) -> tuple[pd.Series, pd.Series]:
    df = db().df("SELECT date, adj_close, volume FROM prices WHERE ticker = ? AND date <= CAST(? AS DATE) ORDER BY date",
                 [ticker, last_day()])
    if df.empty:
        raise DataError(f"No prices for {ticker}.")
    idx = pd.to_datetime(df["date"])
    return pd.Series(df["adj_close"].to_numpy(dtype=float), index=idx), pd.Series(df["volume"].to_numpy(dtype=float), index=idx)


def resolve_period(px_index: pd.DatetimeIndex, period: str | None, start: str | None, end: str | None) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    first, last = px_index[0], px_index[-1]
    try:
        e = min(pd.Timestamp(end), last) if end else last
        s_given = pd.Timestamp(start) if start else None
    except (ValueError, TypeError):
        raise DataError("Dates must look like 2025-01-31.") from None
    if s_given is not None:
        s, label = max(s_given, first), "Custom"
    else:
        key = (period or "1y").lower()
        if key not in PERIODS:
            raise DataError(f"Unknown period '{period}'. Use one of: {', '.join(PERIODS)}.")
        label, days = PERIODS[key]
        if key == "ytd":
            s = pd.Timestamp(e.year, 1, 1)
        elif key == "max" or days is None:
            s = first
        else:
            s = e - pd.Timedelta(days=days)
        s = max(s, first)
    if s >= e:
        raise DataError("The start date needs to be before the end date.")
    return s, e, label


def _downsample(n: int) -> list[int]:
    if n <= MAX_POINTS:
        return list(range(n))
    step = math.ceil(n / MAX_POINTS)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def _ser(s: pd.Series, keep: list[int]) -> list:
    vals = s.to_numpy(dtype=float)
    out = []
    for i in keep:
        v = vals[i]
        out.append(None if not np.isfinite(v) else float(f"{v:.6g}"))
    return out


def run(ticker: str, analysis: str, period: str | None = "1y", start: str | None = None, end: str | None = None,
        params: dict | None = None) -> dict:
    a = ANALYSES.get(analysis)
    if not a:
        raise DataError(f"Unknown analysis '{analysis}'. Options: {', '.join(ANALYSES)}.")
    idx_info = indexes.get(ticker)
    if idx_info:
        t = idx_info["ticker"]
        comp = {"name": idx_info["name"], "sector": None}
        try:
            px, vol = _series(t)
        except DataError:
            raise DataError(f"No prices for {t} (the {idx_info['name']} fund) yet. Rerun the data build to add the "
                            "index funds: uv run python scripts/build_data.py") from None
    else:
        t = ticker_or_error(ticker)
        comp = db().rows("SELECT name, sector FROM companies WHERE ticker = ?", [t])[0]
        px, vol = _series(t)
    spy, _ = _series(BENCHMARK)
    spy = spy.reindex(px.index).ffill()
    etf = SECTOR_ETFS.get(comp["sector"]) if comp["sector"] else None
    sector_px = None
    if etf:
        try:
            sector_px = _series(etf)[0].reindex(px.index).ffill()
        except DataError:
            sector_px = None
    others = {}
    if idx_info and analysis == "relative":
        for other in indexes.TICKERS:
            if other != t:
                try:
                    others[other] = _series(other)[0].reindex(px.index).ffill()
                except DataError:
                    pass
    s, e, label = resolve_period(px.index, period, start, end)
    raw = params or {}
    values = {p.id: p.parse(raw.get(p.id)) for p in a["params"]}
    c = Ctx(t, comp["name"], comp["sector"], px, vol, spy, sector_px, s, e, values, others)
    if c.n < 10:
        raise DataError("Fewer than 10 trading days in that range. Pick a longer period.")
    out = a["fn"](c)
    keep = _downsample(c.n)
    data = {k: _ser(v.reindex(c.idx), keep) for k, v in out.get("data", {}).items()}
    return {
        "ticker": t, "name": comp["name"], "sector": comp["sector"], "kind": "index" if idx_info else "stock",
        "index": idx_info,
        "analysis": {"id": analysis, "name": a["name"], "group": a["group"], "short": a["short"],
                     "explain": a["explain"], "signals": a["signals"],
                     **(INDEX_RELATIVE if idx_info and analysis == "relative" else {})},
        "params": [{**p.public(), "value": values[p.id]} for p in a["params"]],
        "period": {"key": None if start else (period or "1y"), "label": label, "start": str(c.idx[0].date()),
                   "end": str(c.idx[-1].date()), "trading_days": c.n, "history_start": str(px.index[0].date())},
        "dates": [str(c.idx[i].date()) for i in keep],
        "panels": out.get("panels", []), "data": data, "markers": out.get("markers", []),
        "extra": out.get("extra"), "summary": out["summary"], "readout": out["readout"],
    }
