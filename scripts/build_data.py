"""Build the Ticker Tutor database.

    uv run python scripts/build_data.py                  # real data (needs keys; see README)
    uv run python scripts/build_data.py --refresh        # daily update: new prices and headlines, reusing the rest
    uv run python scripts/build_data.py --limit 20       # quick smoke test with 20 companies
    uv run python scripts/build_data.py --demo           # synthetic data, no network
    uv run python scripts/build_data.py --upload gs://BUCKET/tickertutor.duckdb   # also copy to Cloud Storage

Writes data/tickertutor.duckdb (override with --out). Raw downloads are cached in
data/cache, so a rerun after an interruption continues where it stopped.

--refresh is what the app runs for you once a day (see tickertutor/refresh.py). It stops early
when there are no newer prices, and reuses index membership and SEC data for up to a week.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tickertutor import config  # noqa: E402
from tickertutor.build import compute  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="synthetic data (no network, for development)")
    ap.add_argument("--provider", default=None, help="alpaca | tiingo | stooq (default: PRICE_PROVIDER or alpaca)")
    ap.add_argument("--start", default="2014-01-01", help="first date of price history (default 2014-01-01)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N companies (smoke test)")
    ap.add_argument("--no-fundamentals", action="store_true", help="skip SEC data")
    ap.add_argument("--no-news", action="store_true", help="skip the headline snapshot")
    ap.add_argument("--refresh", action="store_true",
                    help="daily update: stop if prices are already current, and reuse index members and SEC data "
                         "saved by a full build in the last week")
    ap.add_argument("--force", action="store_true", help="with --refresh: rebuild even if there are no newer prices")
    ap.add_argument("--out", default=str(config.DB_PATH), help="output DuckDB path")
    ap.add_argument("--upload", default="", help="gs:// URI to upload the finished database to")
    ap.add_argument("--wiki-html", default=None,
                    help="use a saved copy of Wikipedia's 'List of S&P 500 companies' page instead of downloading it")
    ap.add_argument("--wiki-changes-html", default=None,
                    help="use a saved copy of Wikipedia's 'Historical components of the S&P 500' page (index changes)")
    args = ap.parse_args()
    if not args.demo:
        problem = config.contact_problem()
        if problem.startswith("Found .env.txt"):
            sys.exit(problem)
        if problem:
            print(f"Warning: {problem}\n")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    t0 = time.time()
    if args.demo:
        from tickertutor.build import demo

        print("Generating synthetic demo data…")
        raw = demo.generate()
    else:
        from tickertutor.build import fetch
        from tickertutor.sources import SourceError

        try:
            if args.refresh:
                if args.upload:
                    pull_inputs(args.upload)
                have, latest = current_as_of(), newest_price_day(date.fromisoformat(args.start), args.provider)
                if latest is None:
                    sys.exit(f"\nBuild stopped: couldn't download prices for the S&P 500 fund from "
                             f"{args.provider or config.PRICE_PROVIDER}. Check the price keys in .env and your connection.")
                if have and latest <= have and not args.force:
                    print(f"Prices are already current: the data runs through {have} and the newest finished "
                          f"trading day is {latest}. Nothing to do.")
                    return
                print(f"Updating from {have or 'no data'} to {latest}…")
            raw = fetch.fetch_raw(date.fromisoformat(args.start), args.provider, args.limit,
                                  fundamentals=not args.no_fundamentals, with_news=not args.no_news,
                                  wiki_html=args.wiki_html, wiki_changes_html=args.wiki_changes_html,
                                  refresh=args.refresh)
        except SourceError as exc:
            sys.exit(f"\nBuild stopped: {exc}")
    print("Computing indicators, backtests, and summaries…")
    tables = compute.compute(raw)
    out = compute.write_db(tables, Path(args.out))
    size = out.stat().st_size / 1e6
    print(f"\nWrote {out} ({size:.1f} MB) in {time.time() - t0:.0f}s.")
    if size > 95:
        print("Note: that's close to GitHub's 100 MB file limit. Use --start with a later date, or ship it via "
              "Cloud Storage (DATA_GCS_URI; see README).")
    if args.upload:
        from google.cloud import storage

        bucket, _, name = args.upload.removeprefix("gs://").partition("/")
        storage.Client().bucket(bucket).blob(name).upload_from_filename(str(out))
        print(f"Uploaded to {args.upload}")
        if not args.demo:
            push_inputs(args.upload)


def current_as_of() -> str | None:
    """The as-of date of the database the app is using now, if there is one."""
    import duckdb

    from tickertutor import data

    path = data.newest_file()
    if not path.exists():
        return None
    try:
        con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": False})
        try:
            row = con.execute("SELECT value FROM meta WHERE key = 'as_of'").fetchone()
        finally:
            con.close()
        return row[0] if row else None
    except Exception:  # noqa: BLE001  (an unreadable file just means building a new one)
        return None


def newest_price_day(start: date, provider: str | None) -> str | None:
    """The last day the price provider has for the S&P 500 fund: one small request that tells whether a
    refresh would change anything (it wouldn't on a weekend or a market holiday)."""
    from datetime import timedelta

    from tickertutor.sources import prices

    df = prices.download([prices.BENCHMARK], start - timedelta(days=400), prices.last_finished_day(), provider)
    return str(df["date"].max()) if len(df) else None


def _inputs_blob(uri: str):
    from google.cloud import storage

    from tickertutor.build import fetch

    bucket, _, name = uri.removeprefix("gs://").partition("/")
    folder = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
    return storage.Client().bucket(bucket).blob(folder + fetch.INPUTS_FILE)


def pull_inputs(uri: str) -> None:
    """A scheduled job starts with an empty cache, so fetch the saved inputs that sit next to the database."""
    from tickertutor.build import fetch

    path = fetch._inputs_path()
    if path.exists():
        return
    try:
        blob = _inputs_blob(uri)
        if blob.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(path))
            print(f"Fetched saved build inputs from {uri.rsplit('/', 1)[0]}/")
    except Exception as exc:  # noqa: BLE001  (without them the build downloads everything, which is fine)
        print(f"(couldn't fetch saved build inputs: {exc})")


def push_inputs(uri: str) -> None:
    from tickertutor.build import fetch

    path = fetch._inputs_path()
    if not path.exists():
        return
    try:
        _inputs_blob(uri).upload_from_filename(str(path))
    except Exception as exc:  # noqa: BLE001
        print(f"(couldn't upload the saved build inputs: {exc})")


if __name__ == "__main__":
    main()
