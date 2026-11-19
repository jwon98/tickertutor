"""Keeping prices current without anyone running the build by hand.

The database is a snapshot. Two things keep it fresh:

  On your computer   When the app starts, and every half hour while it's open, it checks whether the data is
                     behind the last finished trading day. If so (and price keys are set) it runs
                     `scripts/build_data.py --refresh` in a separate process, then switches to the new file.
                     Pages keep working on the old data while that runs.

  Deployed           Cloud Run instances are short-lived and paused between requests, so they don't rebuild.
                     Instead a scheduled job (or your computer, with REFRESH_UPLOAD_URI set) uploads the fresh
                     database to Cloud Storage, and the app (DATA_GCS_URI) switches to a newer upload within
                     about ten minutes. See README → "Keeping prices current".

Prices are final after 6 pm New York time, so "current" means through the last weekday that has passed that
point. On a market holiday the providers simply have nothing newer, and the refresh stops after one small check.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time

from . import config, data
from .sources import prices

log = logging.getLogger("tickertutor.refresh")

CHECK_EVERY = 30 * 60          # seconds between looks at whether the data is behind
BUCKET_EVERY = 10 * 60         # seconds between looks for a newer upload in Cloud Storage
RETRY_AFTER = 3 * 3600         # after a failed or empty attempt, wait this long before trying the same day again
MAX_TRIES_PER_DAY = 2
TIMEOUT = 2 * 60 * 60        # the first update after a full build re-downloads SEC data, which is slow

_lock = threading.Lock()
_state = {"state": "idle", "message": "", "started": None, "finished": None}
_last_check = 0.0
_last_bucket = 0.0


def enabled() -> bool:
    """On by default on your own computer. Off on Cloud Run (where a scheduled job does it) unless AUTO_REFRESH=1."""
    setting = os.environ.get("AUTO_REFRESH", "").strip().lower()
    if setting in ("0", "false", "off", "no"):
        return False
    if setting in ("1", "true", "on", "yes"):
        return True
    return not os.environ.get("K_SERVICE")


def can_fetch() -> str:
    """"" if the price provider is usable, else why not."""
    provider = config.PRICE_PROVIDER
    if provider == "alpaca" and not (config.ALPACA_API_KEY and config.ALPACA_API_SECRET):
        return "Set ALPACA_API_KEY and ALPACA_API_SECRET in .env to update prices automatically."
    if provider == "tiingo" and not config.TIINGO_API_KEY:
        return "Set TIINGO_API_KEY in .env to update prices automatically."
    return ""


def _memo_path():
    return config.CACHE_DIR / "refresh.json"


def _memo() -> dict:
    try:
        return json.loads(_memo_path().read_text())
    except (OSError, ValueError):
        return {}


def _remember(day: str, ok: bool) -> None:
    memo = _memo()
    tries = memo.get("tries", 0) + 1 if memo.get("day") == day else 1
    try:
        _memo_path().parent.mkdir(parents=True, exist_ok=True)
        _memo_path().write_text(json.dumps({"day": day, "tries": tries, "at": time.time(), "ok": ok}))
    except OSError:
        pass


def status() -> dict:
    """What the page's "Prices as of" corner needs to know."""
    meta = data.db().meta()
    as_of, expected = meta.get("as_of"), str(prices.last_finished_day())
    with _lock:
        s = dict(_state)
    behind = bool(as_of) and as_of < expected and not meta.get("synthetic")
    if s["state"] == "idle" and behind and not s["message"]:
        if config.DATA_GCS_URI:
            s["message"] = "Waiting for the next scheduled data update."
        elif not enabled():
            s["message"] = "Automatic updates are off here."
        else:
            s["message"] = can_fetch()
    return {"as_of": as_of, "expected": expected, "behind": behind, **s}


def tick() -> None:
    """Start whatever check is due, in the background. Cheap to call often (the page calls it when it polls)."""
    global _last_check, _last_bucket
    now = time.time()
    if config.DATA_GCS_URI:
        if not _last_bucket:      # the copy loaded at startup is the newest one, so the first look can wait
            _last_bucket = now
        elif now - _last_bucket >= BUCKET_EVERY:
            _last_bucket = now
            threading.Thread(target=_check_bucket, daemon=True).start()
        return
    if now - _last_check < CHECK_EVERY:
        return
    _last_check = now
    with _lock:
        if _state["state"] == "running":
            return
    try:
        meta = data.db().meta()
    except data.DataError:
        return
    expected = str(prices.last_finished_day())
    if meta.get("synthetic") or not enabled() or (meta.get("as_of") or "") >= expected or can_fetch():
        return
    memo = _memo()
    if memo.get("day") == expected and (memo.get("tries", 0) >= MAX_TRIES_PER_DAY or now - memo.get("at", 0) < RETRY_AFTER):
        return
    with _lock:
        _state.update(state="running", message=f"Getting prices through {expected}…", started=now, finished=None)
    threading.Thread(target=_run, args=(expected,), daemon=True).start()


def _check_bucket() -> None:
    try:
        if data.reload_from_bucket():
            with _lock:
                _state.update(state="idle", message="", finished=time.time())
    except Exception as exc:  # noqa: BLE001  (keep serving the copy already loaded)
        log.warning("Couldn't check %s for a newer database: %s", config.DATA_GCS_URI, exc)


def _run(expected: str) -> None:
    before = data.db().meta().get("as_of")
    out = config.DB_PATH.with_name(f"{config.DB_PATH.stem}.new-{int(time.time())}.duckdb")
    cmd = [sys.executable, str(config.ROOT / "scripts" / "build_data.py"), "--refresh", "--out", str(out)]
    upload = os.environ.get("REFRESH_UPLOAD_URI", "").strip()
    if upload:
        cmd += ["--upload", upload]
    logfile = config.CACHE_DIR / "refresh.log"
    ok, message = False, ""
    try:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        with open(logfile, "w", encoding="utf-8") as fh:
            done = subprocess.run(cmd, cwd=str(config.ROOT), stdout=fh, stderr=subprocess.STDOUT, timeout=TIMEOUT,
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        tail = logfile.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:] or [""]
        if done.returncode != 0:
            message = f"The update stopped: {tail[0][:200]} (details in data/cache/refresh.log)"
        elif out.exists():
            data.swap_db(out)
            ok = True
            now = data.db().meta().get("as_of")
            log.info("Prices updated from %s to %s", before, now)
        else:
            ok, message = True, "No newer prices yet. Markets may have been closed."
    except subprocess.TimeoutExpired:
        message = "The update took too long and was stopped."
    except Exception as exc:  # noqa: BLE001  (a failed update must never take the app down)
        log.exception("refresh failed")
        message = f"The update failed: {exc}"
    _remember(expected, ok)
    with _lock:
        _state.update(state="idle" if ok else "failed", message=message, finished=time.time())
    from . import preload   # new prices mean new example answers (and if nothing changed, this does nothing)

    if preload.auto_enabled():
        preload.warm()
