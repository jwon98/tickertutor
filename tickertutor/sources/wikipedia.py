"""S&P 500 members and the history of index changes, from Wikipedia.

Two Wikipedia pages:
  "List of S&P 500 companies"              constituents: ticker, company, GICS sector and
                                            sub-industry, date added, CIK
  "Historical components of the S&P 500"   dated additions and removals (this table used
                                            to sit on the list page, so both are checked)

Walking the changes backwards from today's list rebuilds who was in the index on
any past date. Backtests use that, so they don't only test today's survivors.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import StringIO
from pathlib import Path

import pandas as pd

from .. import config
from . import SourceError, get

API = "https://en.wikipedia.org/w/api.php"
PAGE = "List of S&P 500 companies"
CHANGES_PAGE = "Historical components of the S&P 500"
EARLIEST = date(1957, 3, 4)   # the index's launch: "member since before our data"


def fetch_html(page: str = PAGE) -> str:
    data = get(API, {"action": "parse", "page": page, "prop": "text", "format": "json", "formatversion": 2})
    html = (data.get("parse") or {}).get("text")
    if not html:
        raise SourceError(f"Wikipedia returned no page text for \"{page}\".")
    return html


def _date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = re.sub(r"\[[^\]]*\]", "", str(value)).replace("\u00a0", " ").strip()   # drop footnote marks like [12]
    s = s.split("(")[0].strip().rstrip(".")
    s = re.sub(r"\bSept\b\.?", "Sep", s)
    s = re.sub(r"\s+", " ", s)
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%b. %d, %Y", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%Y"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d
        except ValueError:
            continue
    return None


def _clean_ticker(t) -> str:
    if t is None or (isinstance(t, float) and pd.isna(t)):
        return ""
    return str(t).strip().upper().replace("​", "")


def parse(html: str) -> tuple[list[dict], list[dict]]:
    """→ (constituents, changes)."""
    try:
        cons = pd.read_html(StringIO(html), attrs={"id": "constituents"}, flavor="lxml")[0]
    except (ValueError, IndexError) as exc:
        raise SourceError("Couldn't find the constituents table on the Wikipedia page; its layout may have "
                          "changed.") from exc
    cols = {c.lower(): c for c in cons.columns}

    def col(*names):
        for n in names:
            if n.lower() in cols:
                return cols[n.lower()]
        return None

    sym, sec, sector, sub = col("Symbol", "Ticker"), col("Security", "Company"), col("GICS Sector"), col("GICS Sub-Industry")
    added, cik, founded, hq = col("Date added", "Date first added"), col("CIK"), col("Founded"), col("Headquarters Location")
    constituents = []
    for _, r in cons.iterrows():
        t = _clean_ticker(r[sym])
        if not t:
            continue
        constituents.append({
            "ticker": t, "name": str(r[sec]).strip(), "sector": str(r[sector]).strip(),
            "sub_industry": str(r[sub]).strip() if sub else "",
            "date_added": _date(r[added]) if added else None,
            "cik": int(r[cik]) if cik and not pd.isna(r[cik]) else None,
            "founded": str(r[founded]).strip() if founded and not pd.isna(r[founded]) else "",
            "hq": str(r[hq]).strip() if hq and not pd.isna(r[hq]) else "",
        })
    if len(constituents) < 400:
        raise SourceError(f"Only parsed {len(constituents)} constituents; expected ~500. The page layout may have changed.")
    return constituents, parse_changes(html)


def _flat(columns) -> list[str]:
    out = []
    for c in columns:
        parts = [str(p) for p in (c if isinstance(c, tuple) else (c,))]
        out.append(" ".join(dict.fromkeys(p for p in parts if not p.startswith("Unnamed"))).lower())
    return out


def parse_changes(html: str) -> list[dict]:
    """Dated additions and removals from every table on the page that has them.

    Two layouts are understood: a changes table (Date | Added: Ticker, Security | Removed: Ticker, Security |
    Reason), and a list of former components with the dates each was added and removed."""
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError:
        return []
    changes: list[dict] = []
    for ch in tables:
        ch = ch.copy()
        ch.columns = _flat(ch.columns)

        def find(*keys, exclude=()):
            for c in ch.columns:
                if all(k in c for k in keys) and not any(x in c for x in exclude):
                    return c
            return None

        text = lambda r, c: "" if not c or pd.isna(r[c]) else str(r[c]).strip()   # noqa: E731
        acol, rcol = find("added", "ticker") or find("added", "symbol"), find("removed", "ticker") or find("removed", "symbol")
        if acol or rcol:   # a changes table
            dcol = find("date") or ch.columns[0]
            anm, rnm, reason = find("added", "security"), find("removed", "security"), find("reason")
            for _, r in ch.iterrows():
                d = _date(r[dcol])
                if d:
                    changes.append({"date": d, "added": _clean_ticker(r[acol]) if acol else "", "added_name": text(r, anm),
                                    "removed": _clean_ticker(r[rcol]) if rcol else "", "removed_name": text(r, rnm),
                                    "reason": text(r, reason)[:300]})
            continue
        tcol = find("ticker") or find("symbol")
        removed_on = find("removed") or find("date", "left") or find("end")
        if tcol and removed_on:   # a list of former components
            added_on = find("added", exclude=("removed",)) or find("start")
            ncol = find("security") or find("company") or find("name")
            for _, r in ch.iterrows():
                t = _clean_ticker(r[tcol])
                d_out = _date(r[removed_on])
                if not t or not d_out:
                    continue
                changes.append({"date": d_out, "added": "", "added_name": "", "removed": t, "removed_name": text(r, ncol),
                                "reason": ""})
                d_in = _date(r[added_on]) if added_on else None
                if d_in and d_in < d_out:
                    changes.append({"date": d_in, "added": t, "added_name": text(r, ncol), "removed": "", "removed_name": "",
                                    "reason": ""})
    # The same change can appear on both pages or in overlapping tables.
    seen, out = set(), []
    for c in changes:
        key = (c["date"], c["added"], c["removed"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def membership(constituents: list[dict], changes: list[dict], today: date | None = None) -> list[dict]:
    """Membership intervals [start, end) per ticker; end None = still a member.

    Sweeps the changes from newest to oldest: an addition on date d means the
    ticker wasn't a member before d; a removal on d means it was."""
    today = today or date.today()
    open_end: dict[str, date | None] = {c["ticker"]: None for c in constituents}
    known_added = {c["ticker"]: c.get("date_added") for c in constituents}
    intervals: list[dict] = []
    for ch in sorted(changes, key=lambda c: c["date"], reverse=True):
        d = ch["date"]
        if d > today:
            continue
        a, r = ch["added"], ch["removed"]
        if a and a in open_end:
            intervals.append({"ticker": a, "start": d, "end": open_end.pop(a)})
        if r and r not in open_end:
            open_end[r] = d
    for t, end in open_end.items():
        start = known_added.get(t) if end is None and known_added.get(t) else EARLIEST
        intervals.append({"ticker": t, "start": start, "end": end})
    return sorted(intervals, key=lambda i: (i["ticker"], i["start"]))


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        raise SourceError(f"Couldn't read {path}: {exc}") from exc


def _download(page: str, cache_name: str) -> str:
    html = fetch_html(page)
    try:   # keep a copy for troubleshooting and for --wiki-html reruns
        cache = Path(config.CACHE_DIR) / cache_name
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")
    except OSError:
        pass
    return html


def fetch(html_path: str | None = None, changes_html_path: str | None = None) -> dict:
    """Download both pages, or read copies saved from a browser if Wikipedia blocks the download."""
    html = _read(html_path) if html_path else _download(PAGE, "wikipedia_sp500.html")
    constituents, changes = parse(html)
    if changes_html_path:
        changes += parse_changes(_read(changes_html_path))
    elif not changes:   # the changes table moved off the list page to its own article
        try:
            changes += parse_changes(_download(CHANGES_PAGE, "wikipedia_sp500_changes.html"))
        except SourceError as exc:
            if not changes:
                raise SourceError(f"{exc} Index changes now live on Wikipedia's \"{CHANGES_PAGE}\" page. Save it from "
                                  "your browser and pass --wiki-changes-html with the file.") from exc
    seen, unique = set(), []
    for c in changes:
        key = (c["date"], c["added"], c["removed"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return {"constituents": constituents, "changes": unique, "membership": membership(constituents, unique)}
