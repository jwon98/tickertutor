"""Run a read-only SQL query against the Ticker Tutor database (the same safe runner the agents use).

    uv run python scripts/sql.py "SELECT ticker, price, sma200, rsi14, vol_1y FROM snapshot WHERE ticker = 'MSFT'"
    uv run python scripts/sql.py --tables      # what each table holds

Uses data/tickertutor.duckdb, or TICKERTUTOR_DB if set. Shows at most 200 rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    import pandas as pd

    from tickertutor.data import SCHEMA, DataError, run_sql
    if args[0] == "--tables":
        for table, about in SCHEMA.items():
            print(f"{table}\n  {about}\n")
        return
    try:
        out = run_sql(" ".join(args))
    except DataError as exc:
        sys.exit(f"Query refused or failed: {exc}")
    df = pd.DataFrame(out["rows"], columns=out["columns"])
    with pd.option_context("display.max_rows", 200, "display.max_columns", 60, "display.width", 220):
        print(df.to_string(index=False) if len(df) else "(no rows)")
    if out.get("truncated"):
        print(f"(showing the first 200 of {out['row_count']} rows)")


if __name__ == "__main__":
    main()
