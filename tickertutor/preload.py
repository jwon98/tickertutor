"""Ready-made answers for the Research desk's example questions.

A full research run takes one to three minutes, and the examples are the same for everyone. So the server runs
each example once per data day (the database's as-of date) and keeps the result: every event the team emitted
along the way, plus the final answer. Clicking an example replays those events over about ten to fourteen
seconds, so the desk still shows the Lead, the Researchers, the Writer, and the Verifier at work, and then adds
the answer to the conversation as if it had just been researched (so follow-ups work).

Answers are saved next to the database (data/research_examples.json). Commit that file with the database and
the deployed app starts with them ready.

When answers are prepared:
  - when the app starts on your computer, and after each daily price update;
  - when anyone opens the app: the page sends one background request that stays open while missing answers are
    prepared. On Cloud Run that open request is what keeps the CPU on (it's paused between requests).
An example clicked while its answer is still being prepared follows that same run instead of starting another.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import agents, config, llm
from .data import DataError, db

log = logging.getLogger("tickertutor.preload")

EXAMPLES = [
    ("Walk me through Microsoft's (MSFT) trend over the past year using moving averages and RSI, and compare its "
     "volatility with the S&P 500's.", "Runs analyses and explains how to read them"),
    ("Why is Nvidia down so much lately?", "Pairs the headlines with how big and how unusual the move is"),
    ("Does buying the dip work for S&P 500 stocks? What has happened after big one-day drops?",
     "Tests a popular belief against history"),
    ("How do Coca-Cola and PepsiCo compare on volatility, drawdowns, and beta over the last five years?", "Side by side"),
    ("How have the Nasdaq-100 and the Russell 2000 done against the S&P 500 over the past three years, and which "
     "swung more?", "The big indexes, compared"),
    ("What should I buy?", "Ticker Tutor doesn't pick stocks: watch the Lead turn this into something you can analyze"),
]

REPLAY_MIN = 10.0     # a researched answer never appears faster than this
REPLAY_MAX = 14.0
REPLAY_QUICK = 5.0    # a clarifying question or an out-of-scope reply (the Lead alone) takes about this long live
CONCURRENCY = 2       # examples prepared at once (each one already runs its researchers in parallel)
RETRY_AFTER = 30 * 60
FILE_NAME = "research_examples.json"

_lock = threading.Lock()
_cache: dict[str, dict] = {}
_loaded_from: Path | None = None
_jobs: dict[str, "Job"] = {}
_failed: dict[str, float] = {}
_warm_thread: threading.Thread | None = None


def key(question: str) -> str:
    return " ".join((question or "").lower().split()).rstrip("?.! ")


_BY_KEY = {key(q): q for q, _ in EXAMPLES}


def is_example(question: str) -> bool:
    return key(question) in _BY_KEY


def _path() -> Path:
    return config.DB_PATH.parent / FILE_NAME


def _stamp() -> dict:
    m = db().meta()
    return {"as_of": m.get("as_of"), "model": config.GEMINI_MODEL}


def _valid(entry: dict | None, stamp: dict | None = None) -> bool:
    if not entry:
        return False
    stamp = stamp or _stamp()
    return entry.get("as_of") == stamp["as_of"] and entry.get("model") == stamp["model"]


def _load() -> None:
    """Read the saved answers once (and again if the database moved, as in tests)."""
    global _loaded_from
    path = _path()
    if _loaded_from == path:
        return
    _loaded_from = path
    _cache.clear()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        for e in saved.get("examples", []):
            if is_example(e.get("question", "")):
                _cache[key(e["question"])] = e
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("Ignoring %s: %s", path, exc)


def _save() -> None:
    stamp = _stamp()
    keep = [e for e in _cache.values() if _valid(e, stamp)]
    path = _path()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps({"note": "Ready-made answers to the Research desk's examples. See tickertutor/preload.py.",
                                   "examples": sorted(keep, key=lambda e: list(_BY_KEY).index(key(e["question"])))},
                                  ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:   # a read-only disk just means the answers live in memory
        log.info("Couldn't save %s: %s", path, exc)


def ready(question: str) -> dict | None:
    with _lock:
        _load()
        e = _cache.get(key(question))
    return e if _valid(e) else None


# --- preparing one example --------------------------------------------------------------------------------------

class Job:
    """One run of an example. Anyone who clicks that example meanwhile follows its events as they arrive."""

    def __init__(self, question: str):
        self.question = question
        self.t0 = time.time()
        self.events: list[tuple[float, dict]] = []
        self.finished = False
        self.error = ""
        self.entry: dict | None = None
        self.cond = threading.Condition()

    def add(self, ev: dict) -> None:
        with self.cond:
            self.events.append((round(time.time() - self.t0, 3), ev))
            self.cond.notify_all()

    def end(self, entry: dict | None, error: str = "") -> None:
        with self.cond:
            self.entry, self.error, self.finished = entry, error, True
            self.cond.notify_all()


def _run(job: Job) -> None:
    stamp = _stamp()
    session = {"id": "s_example", "turns": [], "pending": None}
    entry, error = None, ""
    try:
        run = agents.Run(job.question, session, on_event=job.add)
        result = run.run()
        if result["response"].startswith("Sorry, the research team couldn't"):
            raise llm.LLMError(result["response"])
        turn = session["turns"][-1]
        entry = {"question": job.question, **stamp, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "seconds": turn.get("seconds"), "clarification": turn.get("clarification", False),
                 "pending": session.get("pending"), "events": [[t, ev] for t, ev in job.events]}
    except (llm.LLMError, DataError) as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001  (a failed example must not take anything else down)
        log.exception("preparing an example failed")
        error = f"{exc.__class__.__name__}: {exc}"
    with _lock:
        if entry:
            _cache[key(job.question)] = entry
            _failed.pop(key(job.question), None)
        else:
            _failed[key(job.question)] = time.time()
        _jobs.pop(key(job.question), None)
        if entry:
            _save()
    job.end(entry, error)


def _job(question: str, start: bool = True) -> Job | None:
    """The run already preparing this example, or a new one."""
    k = key(question)
    with _lock:
        if k in _jobs or not start:
            return _jobs.get(k)
        job = _jobs[k] = Job(_BY_KEY[k])
    threading.Thread(target=_run, args=(job,), daemon=True, name=f"example-{k[:20]}").start()
    return job


# --- warming up -------------------------------------------------------------------------------------------------

def status() -> dict:
    with _lock:
        _load()
        stamp = _stamp()
        out = {"ready": [], "preparing": [], "waiting": []}
        for q, _ in EXAMPLES:
            k = key(q)
            out["ready" if _valid(_cache.get(k), stamp) else "preparing" if k in _jobs else "waiting"].append(q)
    out["as_of"] = stamp["as_of"]
    return out


def _missing() -> list[str]:
    with _lock:
        _load()
        stamp = _stamp()
        now = time.time()
        return [q for q, _ in EXAMPLES if not _valid(_cache.get(key(q)), stamp)
                and now - _failed.get(key(q), 0) > RETRY_AFTER]


def warm(wait: float = 0) -> dict:
    """Prepare any examples that aren't ready, two at a time, in the background. With wait, block up to that many
    seconds until they're done (that's what keeps a Cloud Run instance's CPU on while it works)."""
    global _warm_thread
    if _missing():
        with _lock:
            alive = _warm_thread is not None and _warm_thread.is_alive()
            if not alive:
                _warm_thread = threading.Thread(target=_warm_all, daemon=True, name="examples")
                _warm_thread.start()
    t = _warm_thread
    if wait and t is not None:
        t.join(wait)
    return status()


def _warm_all() -> None:
    todo = _missing()
    if not todo:
        return
    log.info("Preparing %d example answers", len(todo))

    def one(q: str) -> None:
        job = _job(q)
        with job.cond:
            while not job.finished:
                job.cond.wait(30)

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        list(pool.map(one, todo))


def auto_enabled() -> bool:
    """Prepare examples without being asked: on by default with real data, off with the synthetic demo data."""
    setting = os.environ.get("PRELOAD_EXAMPLES", "").strip().lower()
    if setting in ("0", "false", "off", "no"):
        return False
    if setting in ("1", "true", "on", "yes"):
        return True
    try:
        return not db().meta().get("synthetic")
    except DataError:
        return False


# --- answering ----------------------------------------------------------------------------------------------------

def _remember(session: dict, entry: dict, question: str) -> None:
    done = next(ev for _, ev in entry["events"] if ev.get("type") == "done")
    session["turns"].append({"user": question, "assistant": done["response"], "clarification": entry.get("clarification", False),
                             "seconds": entry.get("seconds"), "prepared": True})
    session["pending"] = ({**entry["pending"], "question": question} if entry.get("pending") else None)


def _label(ev: dict, session: dict, entry: dict) -> dict:
    if ev.get("type") != "done":
        return ev
    return {**ev, "session_id": session["id"],
            "prepared": {"seconds": entry.get("seconds"), "created": entry.get("created"), "as_of": entry.get("as_of")}}


def answer_now(question: str, session_id: str | None) -> dict | None:
    """For POST /chat: the ready answer at once, recorded in the session, or None."""
    entry = ready(question) if is_example(question) else None
    if not entry:
        return None
    session = agents.sessions.get(session_id)
    _remember(session, entry, question)
    done = _label(next(ev for _, ev in entry["events"] if ev.get("type") == "done"), session, entry)
    return {"response": done["response"], "session_id": session["id"], "tool_calls": done["tool_calls"]}


def stream(question: str, session_id: str | None, put: Callable[[dict], None], sleep=time.sleep, now=time.time) -> bool:
    """For the Research desk. If the question is an example, send its events through put() at a readable pace and
    record the answer in the session, then return True. Otherwise return False (the caller runs it live)."""
    if not is_example(question):
        return False
    entry = ready(question)
    if entry:
        _replay(entry, question, session_id, put, sleep, now)
        return True
    if not auto_enabled() and not _job(question, start=False):
        return False
    job = _job(question)
    _follow(job, question, session_id, put, sleep, now)
    return True


def _span(events: list, total: float) -> float:
    plan = next((ev.get("plan", {}) for _, ev in events if ev.get("type") == "plan"), {})
    if plan.get("action") == "research":
        return min(max(total, REPLAY_MIN), REPLAY_MAX)
    return min(total, REPLAY_QUICK)


def _replay(entry: dict, question: str, session_id: str | None, put, sleep, now) -> None:
    events = entry["events"]
    total = max(events[-1][0], 0.001)
    k = _span(events, total) / total
    start = now()
    session = agents.sessions.get(session_id)
    for t, ev in events:
        wait = start + t * k - now()
        if wait > 0:
            sleep(wait)
        if ev.get("type") == "done":
            _remember(session, entry, question)
        put(_label(ev, session, entry))


def _follow(job: Job, question: str, session_id: str | None, put, sleep, now) -> None:
    """Join a run in progress: catch up on what already happened quickly, then show the rest as it arrives."""
    start = now()
    behind = start - job.t0
    k = min(1.0, 8.0 / behind) if behind > 0 else 1.0
    i = 0
    session = agents.sessions.get(session_id)
    while True:
        with job.cond:
            while i >= len(job.events) and not job.finished:
                job.cond.wait(15)
            batch, finished = job.events[i:], job.finished
        for t, ev in batch:
            i += 1
            if ev.get("type") == "done":
                continue   # sent below, once the run is saved
            wait = (start + t * k - now()) if t <= behind else 0
            if wait > 0:
                sleep(wait)
            put(ev)
        if finished and i >= len(job.events):
            break
    if not job.entry:
        put({"type": "error", "error": job.error or "The research team couldn't finish. Please try again."})
        return
    entry = job.entry
    research = _span(entry["events"], 1.0) > REPLAY_QUICK
    wait = start + (REPLAY_MIN if research else 0) - now()
    if wait > 0:
        sleep(wait)
    _remember(session, entry, question)
    done = next(ev for _, ev in entry["events"] if ev.get("type") == "done")
    put(_label(done, session, entry))
