"""Optional market context from FRED (free key): the 10-year Treasury yield and
the VIX "fear index". Used on the overview page; skipped without a key."""

from __future__ import annotations

from datetime import date

from .. import config
from . import SourceError, get

SERIES = {"DGS10": "10-year Treasury yield (%)", "VIXCLS": "VIX volatility index"}


def series(series_id: str, start: date) -> list[dict]:
    if not config.FRED_API_KEY:
        raise SourceError("Set FRED_API_KEY (free at fred.stlouisfed.org → My Account → API Keys).")
    data = get("https://api.stlouisfed.org/fred/series/observations",
               {"series_id": series_id, "api_key": config.FRED_API_KEY, "file_type": "json",
                "observation_start": start.isoformat()})
    out = []
    for o in data.get("observations", []):
        try:
            out.append({"series": series_id, "date": o["date"], "value": float(o["value"])})
        except (ValueError, KeyError):
            continue   # FRED marks missing days with "."
    return out
