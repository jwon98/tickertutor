"""Ticker Tutor: learn to analyze S&P 500 stocks yourself.

Run locally:   uv run uvicorn app:app --reload
Deployed:      Cloud Run, buildpack entrypoint `uvicorn app:app --host 0.0.0.0 --port $PORT` (see README).

Pages read the offline-built database (data/tickertutor.duckdb). /chat runs the
deep-research team (Lead → parallel Researchers → Writer → Verifier) and returns
{"response", "session_id", "tool_calls"}, where every tool call, including the
Researchers', carries an "agent" field.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from tickertutor import agents, analysis, config, preload, refresh, views
from tickertutor.data import DataError, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tickertutor.app")
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Ticker Tutor", description="Learn to analyze S&P 500 stocks yourself: common analyses, explained.")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def revalidate_code(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/static/js/", "/static/css/")):
        response.headers["Cache-Control"] = "no-cache"
    elif request.url.path.startswith("/static/fonts/"):   # font files never change, so browsers can keep them
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(DataError)
async def data_error(_request: Request, exc: DataError):
    return JSONResponse({"error": str(exc)}, status_code=404)


# --- pages ---------------------------------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True, "as_of": db().meta().get("as_of")}


@app.on_event("startup")
def keep_data_fresh():
    refresh.tick()
    # On your computer, prepare the example answers right away (unless new prices are on the way, in which case
    # the update does it when it finishes). On Cloud Run the first visitor's page asks for it instead.
    if preload.auto_enabled() and not config.running_on_cloud_run() and refresh.status()["state"] != "running":
        preload.warm()


@app.get("/api/data-status")
def data_status():
    """How current the prices are, and whether an update is running. Asking also starts one if it's due."""
    refresh.tick()
    return refresh.status()


@app.get("/api/meta")
def meta():
    return {**views.meta_public(), "features": config.features(), "disclaimer": agents.DISCLAIMER}


@app.get("/api/overview")
def overview():
    return views.overview()


@app.get("/api/stocks")
def stocks(sector: str = "", sort: str = "market_cap", q: str = ""):
    return {"stocks": views.screener(sector, sort, q[:40])}


@app.get("/api/tickers")
def tickers():
    return {"tickers": views.tickers()}


@app.get("/api/indexes")
def market_indexes():
    return {"indexes": views.market_indexes()}


@app.get("/api/indexes/{ticker}")
def index_page(ticker: str):
    return views.index_page(ticker)


@app.get("/api/stocks/{ticker}")
def stock(ticker: str):
    return views.stock(ticker)


@app.get("/api/stocks/{ticker}/prices")
def prices(ticker: str, range: str = "ytd", start: str = "", end: str = ""):  # noqa: A002
    try:
        return views.price_series(ticker, range, start or None, end or None)
    except DataError as exc:
        msg = str(exc)
        raise HTTPException(404 if "isn't in the S&P 500 data" in msg or msg.startswith("No prices") else 400, msg) from None


@app.get("/api/analyses")
def analyses_catalog():
    return {"analyses": analysis.catalog(), "groups": analysis.GROUPS,
            "periods": [{"key": k, "label": v[0]} for k, v in analysis.PERIODS.items()]}


@app.get("/api/analysis")
def run_analysis(request: Request, ticker: str, a: str, period: str = "1y", start: str = "", end: str = ""):
    """Run one analysis. Parameters beyond these (e.g. ?window=21) are passed to the analysis."""
    known = {"ticker", "a", "period", "start", "end"}
    params = {k: v for k, v in request.query_params.items() if k not in known}
    try:
        out = analysis.run(ticker, a, period or "1y", start or None, end or None, params)
    except DataError as exc:
        msg = str(exc)
        status = 404 if "isn't in the S&P 500 data" in msg or msg.startswith("No prices") else 400
        raise HTTPException(status, str(exc)) from None
    # Backtests describe S&P 500 stocks, so they're shown for companies, not for the index funds.
    out["evidence"] = [] if out["kind"] == "index" else views.signal_evidence(out["analysis"]["signals"], out["sector"])
    out["as_of"] = db().meta().get("as_of")
    return out


@app.get("/api/news")
def news_page():
    return views.news_page()


@app.get("/api/news/live")
async def news_live():
    """Fresh headlines (cached for 30 minutes), or the saved ones when the live feed can't be reached."""
    return await run_in_threadpool(views.live_headlines)


@app.get("/api/suggestions")
def suggestions():
    return views.suggestions()


@app.get("/api/stocks/{ticker}/live-news")
async def live_news(ticker: str):
    from tickertutor.data import ticker_or_error
    from tickertutor.sources import SourceError
    from tickertutor.sources import news as news_src

    t = ticker_or_error(ticker)
    name = db().rows("SELECT name FROM companies WHERE ticker = ?", [t])[0]["name"]
    if db().meta().get("synthetic"):
        return {"articles": views.stock(t)["news"], "provider": "demo snapshot"}
    try:
        items = await run_in_threadpool(news_src.company_news, t, name, 14)
        return {"articles": news_src.about(items, name, t)[:12], "provider": items[0]["provider"] if items else ""}
    except SourceError as exc:
        return {"articles": views.stock(t)["news"], "provider": "snapshot", "note": str(exc)}


# --- chat (deep research) ------------------------------------------------------------------------------------

class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limit(request: Request) -> None:
    """A simple per-visitor hourly cap, so a public URL can't run up the model bill."""
    key = request.headers.get("x-goog-authenticated-user-email") or (request.client.host if request.client else "?")
    now = time.time()
    with _hits_lock:
        q = _hits[key]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= config.CHAT_RATE_PER_HOUR:
            raise HTTPException(429, f"That's {config.CHAT_RATE_PER_HOUR} questions this hour; try again a bit later.")
        q.append(now)


@app.get("/api/research/examples")
def research_examples():
    ready = set(preload.status()["ready"])
    return {"examples": [{"q": q, "sub": sub, "ready": q in ready} for q, sub in preload.EXAMPLES]}


@app.post("/api/research/preload")
async def research_preload():
    """Prepare the example answers that aren't ready yet. The page sends this once when it opens and leaves it
    open: on Cloud Run, an open request is what keeps the CPU running while the answers are prepared."""
    if not preload.auto_enabled():
        return {**preload.status(), "skipped": "Examples are prepared only with real data."}
    return await run_in_threadpool(preload.warm, max(30, config.PRELOAD_WAIT_SECONDS))


@app.post("/chat")
async def chat(body: ChatIn, request: Request):
    """{"response", "session_id", "tool_calls": [{"agent", "name", "args", "result"}]}"""
    ready = preload.answer_now(body.message, body.session_id)
    if ready:
        return ready
    _rate_limit(request)
    try:
        return await run_in_threadpool(agents.answer, body.message, body.session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/chat/stream")
async def chat_stream(body: ChatIn, request: Request):
    """Server-sent events while the team works: plan, researcher_start, tool_call, researcher_done,
    review, writing, verified, then done (same payload as /chat plus the sources list)."""
    if not preload.is_example(body.message):
        _rate_limit(request)
    events: queue.Queue = queue.Queue()

    def work():
        try:
            if preload.stream(body.message, body.session_id, events.put):
                return   # an example: its prepared answer, replayed at a readable pace
            agents.answer(body.message, body.session_id, on_event=events.put)
        except Exception as exc:  # noqa: BLE001
            log.exception("chat failed")
            events.put({"type": "error", "error": str(exc)})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    async def gen():
        while True:
            try:
                ev = await asyncio.to_thread(events.get, True, 15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if ev is None:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/chat/{session_id}")
def chat_history(session_id: str):
    s = agents.sessions.get(session_id)
    return {"session_id": s["id"], "turns": s["turns"]}


if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("app:app", host="0.0.0.0" if os.environ.get("K_SERVICE") else "127.0.0.1", port=port)
