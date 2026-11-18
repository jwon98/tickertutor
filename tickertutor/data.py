"""Read access to the Ticker Tutor database (built offline by scripts/build_data.py).

The app's pages and the research agents' tools both read through here. The
database is opened read-only with external file access turned off, and the
free-form SQL tool only runs single SELECT statements with a row limit and a
time limit.
"""

from __future__ import annotations

import json
import logging
import math
import re
import shutil
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import config

log = logging.getLogger("tickertutor.data")


class DataError(Exception):
    """The data can't answer this (missing ticker, bad query, ...). The message says why."""


def clean(obj):
    """Make query results JSON-friendly (dates → ISO strings, NaN → None)."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if obj is pd.NaT or obj is None:
        return None
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.date().isoformat() if isinstance(obj, pd.Timestamp) or obj.time() == datetime.min.time() else obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


class Database:
    def __init__(self, path: Path | str):
        path = Path(path)
        if not path.exists():
            raise DataError(f"No database at {path}. Build it with: uv run python scripts/build_data.py "
                            "(or --demo for synthetic data).")
        self.path = path
        self._con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": False})
        self._lock = threading.Lock()
        self._meta: dict | None = None

    def cursor(self):
        with self._lock:
            return self._con.cursor()

    def df(self, sql: str, params: list | None = None) -> pd.DataFrame:
        cur = self.cursor()
        try:
            return cur.execute(sql, params or []).df()
        finally:
            cur.close()

    def rows(self, sql: str, params: list | None = None) -> list[dict]:
        return clean(self.df(sql, params).to_dict(orient="records"))

    def tables(self) -> list[str]:
        return [r[0] for r in self.cursor().execute("SELECT table_name FROM information_schema.tables").fetchall()]

    # --- metadata ------------------------------------------------------------------------------------
    def meta(self) -> dict:
        if self._meta is None:
            raw = {r["key"]: r["value"] for r in self.rows("SELECT key, value FROM meta")}
            for k in ("coverage", "market", "signals"):
                if k in raw:
                    try:
                        raw[k] = json.loads(raw[k])
                    except ValueError:
                        pass
            raw["synthetic"] = str(raw.get("synthetic", "False")).lower() == "true"
            self._meta = raw
        return self._meta

    def close(self) -> None:
        self._con.close()


_db: Database | None = None
_db_lock = threading.Lock()


def db() -> Database:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database(_resolve_path())
    return _db


def set_db(path: Path | None) -> None:
    """Point at another database file (tests, or after a refresh)."""
    global _db
    with _db_lock:
        if _db is not None:
            _db.close()
        _db = Database(path) if path else None


def pending_files() -> list[Path]:
    """Refreshed databases waiting to replace the main file (written next to it by the daily update)."""
    main = config.DB_PATH.stat().st_mtime if config.DB_PATH.exists() else 0
    found = [p for p in config.DB_PATH.parent.glob(f"{config.DB_PATH.stem}.new-*.duckdb") if not p.name.endswith(".tmp.duckdb")]
    for p in [p for p in found if p.stat().st_mtime <= main]:   # older than a build run by hand since: not needed
        try:
            p.unlink()
        except OSError:
            pass
    return sorted((p for p in found if p.exists() and p.stat().st_mtime > main), key=lambda p: p.stat().st_mtime)


def newest_file() -> Path:
    """The database file with the latest data: the main one, or a refreshed copy that couldn't replace it yet."""
    pending = pending_files()
    return pending[-1] if pending else config.DB_PATH


def _promote(new_file: Path) -> Path:
    """Move a refreshed database into place. If the old file can't be replaced right now (Windows keeps it
    locked while anything has it open), use the new file where it is. The next start tidies up."""
    try:
        new_file.replace(config.DB_PATH)
        return config.DB_PATH
    except OSError:
        return new_file


def swap_db(new_file: Path) -> None:
    """Switch the running app to a refreshed database."""
    global _db
    Database(new_file).close()   # make sure it opens before letting go of the old one
    with _db_lock:
        old, _db = _db, None
        if old is not None:
            old.close()
        _db = Database(_promote(new_file))


gcs_generation: int | None = None   # which upload of the Cloud Storage copy is loaded


def _download_from_bucket(only_if_newer: bool = False) -> Path | None:
    global gcs_generation
    from google.cloud import storage

    bucket, _, name = config.DATA_GCS_URI.removeprefix("gs://").partition("/")
    blob = storage.Client().bucket(bucket).get_blob(name)
    if blob is None or (only_if_newer and blob.generation == gcs_generation):
        return None
    dest = Path(f"/tmp/tickertutor-{blob.generation}.duckdb")
    blob.download_to_filename(str(dest))
    gcs_generation = blob.generation
    return dest


def reload_from_bucket() -> bool:
    """If a newer database was uploaded to DATA_GCS_URI since this one was loaded, switch to it."""
    global _db
    if not config.DATA_GCS_URI:
        return False
    dest = _download_from_bucket(only_if_newer=True)
    if dest is None:
        return False
    fresh = Database(dest)
    with _db_lock:
        old, _db = _db, fresh
    if old is not None:
        old.close()
        if str(old.path).startswith("/tmp/tickertutor-"):
            old.path.unlink(missing_ok=True)
    log.info("Switched to a newer database from %s", config.DATA_GCS_URI)
    return True


def _resolve_path() -> Path:
    """A fresher copy from Cloud Storage if DATA_GCS_URI is set, else the newest refreshed file, else the
    database that ships with the app."""
    if config.DATA_GCS_URI:
        try:
            dest = _download_from_bucket()
            if dest is not None:
                log.info("Loaded the database from %s", config.DATA_GCS_URI)
                return dest
        except Exception as exc:  # noqa: BLE001  (fall back to the copy that ships with the app)
            log.warning("Couldn't load %s (%s); using the shipped database", config.DATA_GCS_URI, exc)
    pending = pending_files()
    if pending:
        newest = pending[-1]
        for old in pending[:-1]:
            try:
                old.unlink()
            except OSError:
                pass
        try:
            Database(newest).close()
            return _promote(newest)
        except Exception as exc:  # noqa: BLE001  (a half-written file from an interrupted update)
            log.warning("Ignoring %s: %s", newest, exc)
            try:
                newest.unlink()
            except OSError:
                pass
    return config.DB_PATH


# --- helpers used by pages and tools ------------------------------------------------------------------------

def long_term_date(purchase: date | None = None) -> date:
    """Shares held more than one year get long-term capital gains treatment in the
    US. Holding starts the day after purchase, so the first long-term sale date is
    the day after the one-year anniversary."""
    p = purchase or date.today()
    try:
        anniversary = p.replace(year=p.year + 1)
    except ValueError:            # bought on Feb 29
        anniversary = date(p.year + 1, 3, 1) - timedelta(days=1)
    return anniversary + timedelta(days=1)


def last_day() -> str:
    """The data's as-of date (the S&P 500 fund's last trading day in the build). Price rows after it, which can
    appear when one fund was downloaded later than the rest, are ignored so every page describes the same day."""
    return str(db().meta().get("as_of") or "9999-12-31")


def ticker_or_error(ticker: str) -> str:
    t = (ticker or "").strip().upper().replace("-", ".").replace("/", ".")
    if not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", t):
        raise DataError(f"'{ticker}' isn't a valid ticker symbol.")
    found = db().rows("SELECT ticker FROM companies WHERE ticker = ?", [t])
    if not found:
        alt = db().rows("SELECT ticker, name FROM companies WHERE lower(name) LIKE ? LIMIT 5",
                        [f"%{ticker.lower()}%"]) if len(ticker) > 2 else []
        hint = f" Did you mean {', '.join(a['ticker'] + ' (' + a['name'] + ')' for a in alt)}?" if alt else ""
        raise DataError(f"{t} isn't in the S&P 500 data Ticker Tutor covers.{hint} Ticker Tutor only covers current "
                        "S&P 500 members.")
    return t


def find_company(text: str, limit: int = 5) -> list[dict]:
    q = text.strip().lower()
    return db().rows(
        "SELECT ticker, name, sector FROM companies WHERE lower(ticker) = ? OR lower(name) LIKE ? "
        "ORDER BY (lower(ticker) = ?) DESC, market_cap DESC NULLS LAST LIMIT ?", [q, f"%{q}%", q, limit])


# --- safe SQL for the research agents ------------------------------------------------------------------------

FORBIDDEN = re.compile(r"\b(insert|update|delete|create|drop|alter|attach|detach|copy|pragma|install|load|export|"
                       r"import|call|set|reset|checkpoint|vacuum|grant|revoke)\b|read_\w+\s*\(|glob\s*\(", re.I)


def run_sql(query: str, limit: int = 200, timeout: float = 15.0) -> dict:
    q = (query or "").strip().rstrip(";").strip()
    if not q:
        raise DataError("Empty query.")
    if ";" in q:
        raise DataError("Run one statement at a time (no semicolons).")
    if not re.match(r"(?is)^\s*(select|with)\b", q):
        raise DataError("Only SELECT (or WITH … SELECT) queries are allowed.")
    if FORBIDDEN.search(q):
        raise DataError("That query uses a statement or function that isn't allowed; read-only SELECTs only.")
    cur = db().cursor()
    timer = threading.Timer(timeout, cur.interrupt)
    timer.start()
    try:
        df = cur.execute(f"SELECT * FROM ({q}) AS sub LIMIT {int(limit) + 1}").df()
    except duckdb.Error as exc:
        msg = str(exc).split("\n")[0]
        if "Interrupt" in msg:
            raise DataError(f"The query took longer than {int(timeout)} seconds; narrow it down.") from exc
        raise DataError(f"SQL error: {msg[:300]}. Check table and column names with the schema.") from exc
    finally:
        timer.cancel()
        cur.close()
    truncated = len(df) > limit
    df = df.head(limit)
    return {"columns": list(df.columns), "rows": clean(df.to_dict(orient="records")), "row_count": len(df),
            "truncated": truncated}


SCHEMA = {
    "companies": "One row per current S&P 500 member: ticker, name, sector (GICS), sub_industry, cik, member_since, "
                 "years_in_index, market_cap (USD), cap_rank (1 = largest).",
    "snapshot": "Latest values per stock (as_of date): price, change_1d, ret_1m/3m/6m/1y (total return, fractions), "
                "ret_3y_ann, ret_5y_ann, ret_ytd, spy_ret_1y, sma50, sma200, above_200d, golden_cross, rsi14, mom_12_1, "
                "dist_52w_high, vol_1y (annualized), beta_1y, rel_sector_6m, max_drawdown, dd_peak, dd_trough, "
                "dd_recovered, current_drawdown, pct_up_1y (share of all 1-year holding periods that ended up), best_1y, "
                "worst_1y, median_1y, spy_pct_up_1y, history_start, revenue_ttm, net_income_ttm, eps_ttm, fcf_ttm, "
                "dividend_ps_ttm, dividend_yield, pe, pe_med5 (own 5-yr median P/E), earnings_yield, market_cap, "
                "fy_end, revenue_growth, op_margin, net_margin, debt_to_equity, roe, profitable_years (of last 5), "
                "dividend_years.",
    "prices": "Daily prices: ticker, date, close (as traded), adj_close (adjusted for splits and dividends), volume. "
              "Includes SPY and sector ETFs (XLK, XLF, XLV, XLY, XLP, XLE, XLI, XLB, XLU, XLRE, XLC).",
    "fundamentals": "Annual figures per ticker and fiscal year end (fy_end), with the date first filed (filed): revenue, "
                    "net_income, operating_income, gross_profit, eps_diluted, assets, equity, long_term_debt, cash, "
                    "operating_cash_flow, capex, dividends_per_share, diluted_shares. Source: SEC XBRL filings.",
    "signal_cards": "Track record of each signal: signal_id, label, family, universe ('All' or a sector), n_months, "
                    "hit_on/hit_off (share beating the S&P 500 over the next 12 months when the signal was on/off), "
                    "excess_on/excess_off (avg 12-month return minus the S&P 500), diff with 95% CI diff_lo/diff_hi, "
                    "is_diff/oos_diff (earlier vs held-out recent period), verdict, period_start, period_end.",
    "panel": "Monthly backtest panel (point-in-time): date (month end), ticker, sector, excess_12m (next-12-month "
             "return minus SPY), beat_12m, fwd_12m, and 0/1 signal columns: above_200d, golden_cross, "
             "momentum_top30, near_52w_high, rsi_oversold, big_dip, strong_vs_sector, low_volatility, profitable_5y, "
             "high_margin, low_debt, revenue_growth_10, cheap_vs_history, cheap_vs_market, dividend_5y; plus pe, "
             "pe_med5, mom, vol, rsi.",
    "sectors": "Per sector: etf, members, median_ret_1y, pct_above_200d, median_pe, "
               "etf_ret_1w/1m/3m/1y, market_cap.",
    "events": "Base rates after events across the index: event (one_day_drop, one_day_jump, earnings_up, "
              "earnings_down), horizon, n, mean (avg excess return after), pct_positive, mean_lo/mean_hi, pos_lo/pos_hi.",
    "recent_moves": "One-day moves of 5%+ vs the S&P 500 in the last ~30 trading days: date, ticker, kind, ret_1d, "
                    "excess_1d, n_similar (similar moves in this stock's history), n_beat_after, n_with_outcome.",
    "earnings": "Earnings releases (SEC 8-K item 2.02): ticker, date, url, reaction (2-day excess return), "
                "excess_next_3m, excess_next_12m.",
    "filings": "SEC filings for current members: ticker, form (10-K, 10-Q, 8-K), filed, report_date, items, "
               "item_names, url.",
    "index_changes": "S&P 500 additions/removals: date, added, added_name, removed, removed_name, reason.",
    "news": "Headline snapshot from build time: ticker ('_market' for general), headline, summary, source, url, published.",
    "meta": "key/value: as_of, built_at, provider, synthetic, coverage, market.",
}
