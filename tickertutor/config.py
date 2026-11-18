"""Settings. Every value comes from an environment variable.

Locally they're read from `.env` (see `.env.example`). On Cloud Run, set them
under "Variables & Secrets" (see README → Deploy).
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("tickertutor")

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else default


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


# --- Gemini (Vertex AI / Agent Platform) -------------------------------------------
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.8-flash")
GOOGLE_CLOUD_LOCATION = _env("GOOGLE_CLOUD_LOCATION", "global")
GEMINI_THINKING = _env("GEMINI_THINKING", "low").lower()
GEMINI_TOOL_THINKING = _env("GEMINI_TOOL_THINKING", "minimal").lower()
GEMINI_MAX_CONCURRENT = _int("GEMINI_MAX_CONCURRENT", 8)

# --- Data ----------------------------------------------------------------------------
# The database the offline build produces (scripts/build_data.py). It ships with the
# deploy. DATA_GCS_URI (optional) points at a fresher copy a scheduled job uploads.
DB_PATH = Path(_env("TICKERTUTOR_DB", str(ROOT / "data" / "tickertutor.duckdb")))
DATA_GCS_URI = _env("DATA_GCS_URI")          # e.g. gs://my-bucket/tickertutor.duckdb
CACHE_DIR = Path(_env("CACHE_DIR", str(ROOT / "data" / "cache")))

# --- Data sources (keys are free; see README) -----------------------------------------
PRICE_PROVIDER = _env("PRICE_PROVIDER", "alpaca").lower()   # alpaca | tiingo | stooq
ALPACA_API_KEY = _env("ALPACA_API_KEY")
ALPACA_API_SECRET = _env("ALPACA_API_SECRET")
TIINGO_API_KEY = _env("TIINGO_API_KEY")
FINNHUB_API_KEY = _env("FINNHUB_API_KEY")
FRED_API_KEY = _env("FRED_API_KEY")
# The SEC and Wikipedia both require clients to identify themselves with a contact email;
# Wikipedia answers HTTP 403 to requests without one. SEC_USER_AGENT holds yours (see .env.example),
# and the same email goes into the User-Agent for every other site (or set CONTACT_EMAIL).
SEC_USER_AGENT = _env("SEC_USER_AGENT", "Ticker Tutor research tool (set SEC_USER_AGENT to include your email)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _contact() -> str:
    if _env("CONTACT_EMAIL"):
        return _env("CONTACT_EMAIL")
    m = _EMAIL.search(SEC_USER_AGENT)
    return m.group(0) if m else ""


CONTACT_EMAIL = _contact()
USER_AGENT = ("TickerTutor/1.0 (educational class project" + (f"; {CONTACT_EMAIL}" if CONTACT_EMAIL else "")
              + ") python-httpx")


def contact_problem() -> str:
    """Why the contact email is missing or a placeholder, or "" if it looks fine."""
    if (ROOT / ".env.txt").exists() and not (ROOT / ".env").exists():
        return ("Found .env.txt but no .env, so your keys aren't being read. Rename it: "
                "Rename-Item .env.txt .env  (Windows hides the .txt ending).")
    if not CONTACT_EMAIL:
        return ("SEC_USER_AGENT has no email. Set it in .env, e.g. SEC_USER_AGENT=Ticker Tutor class project "
                "you@school.edu. Wikipedia and the SEC both refuse requests without a contact.")
    if CONTACT_EMAIL.endswith("example.com"):
        return "SEC_USER_AGENT still has the placeholder email. Put your own email in .env."
    return ""

# --- Agents -----------------------------------------------------------------------------
MAX_ROUNDS = _int("MAX_ROUNDS", 3)                 # Lead → Researchers rounds
MAX_RESEARCHERS = _int("MAX_RESEARCHERS", 5)       # per round
MAX_RESEARCHER_STEPS = _int("MAX_RESEARCHER_STEPS", 6)
TIME_BUDGET_SECONDS = _int("TIME_BUDGET_SECONDS", 200)   # graders wait up to 5 minutes
CHAT_RATE_PER_HOUR = _int("CHAT_RATE_PER_HOUR", 40)

LOCAL_USER = _env("LOCAL_USER", "local-dev")


@lru_cache(maxsize=1)
def project_id() -> str | None:
    for name in ("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT", "GCP_PROJECT"):
        if _env(name):
            return _env(name)
    try:
        import google.auth

        _, project = google.auth.default()
        return project
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not determine GCP project: %s", exc)
        return None


def features() -> dict:
    return {"model": GEMINI_MODEL, "news": "finnhub" if FINNHUB_API_KEY else "gdelt",
            "max_rounds": MAX_ROUNDS}
