"""Run Ticker Tutor locally without Gemini or API keys, for working on the UI.

    uv run python scripts/dev_server.py            # demo data + a scripted stand-in for the model
    uv run python scripts/dev_server.py --real-llm # demo data, real Gemini on Vertex (needs gcloud auth)

The stand-in plays every agent role (Lead, parallel Researchers calling the real tools, Writer,
Verifier) with short pauses, so the research desk's live board behaves like the real thing.
It is for development only; the deployed app always uses Gemini.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import types as pytypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install_stand_in(delay: float) -> None:
    from google.genai import types

    from tests.fakes import FakeLLM, _resp
    from tickertutor.data import db

    class StandIn(FakeLLM):
        def generate_json(self, *a, **k):
            time.sleep(delay)
            return super().generate_json(*a, **k)

        def generate(self, contents, cfg, thinking=None):
            time.sleep(delay * (0.6 if cfg is not None and cfg.tools else 1.6))
            if cfg is not None and cfg.tools:
                return super().generate(contents, cfg, thinking)
            return _resp([types.Part(text=self._report(contents if isinstance(contents, str) else str(contents)))])

        def _report(self, prompt: str) -> str:
            refs = re.findall(r"^\[(S\d+)\] (.*)$", prompt, re.M)
            def ref(word, default=0):
                for r, title in refs:
                    if word.lower() in title.lower():
                        return f"[{r}]"
                return f"[{refs[default][0]}]" if len(refs) > default else ""
            q = re.search(r"Question: (.*)", prompt)
            question = q.group(1) if q else ""
            m = re.search(r"\b([A-Z]{2,5})\b(?='s| over| trend)", question) or re.search(r"\b([A-Z]{2,5})\b", question)
            t = m.group(1) if m else "KO"
            rows = db().rows("SELECT s.*, c.name FROM snapshot s JOIN companies c USING (ticker) WHERE ticker = ?", [t])
            if not rows:
                return f"**Bottom line:** Ticker Tutor's data doesn't include {t}. {ref('')}"
            s = rows[0]
            p = lambda v, d=0: "—" if v is None else f"{v * 100:+.{d}f}%"
            if "Why has" in question:
                return self._why(t, s, prompt, refs, ref, p)
            above = s["price"] > s["sma200"] if s.get("sma200") else None
            return (
                f"### In short\n{s['name']} is trading {'above' if above else 'below'} its 200-day average and its 14-day RSI "
                f"is {s['rsi14']:.0f} {ref('moving')}. Its price has swung about {round((s['vol_1y'] or 0) * 100)}% a year "
                f"{ref('volatility')}.\n\n"
                f"### What the numbers show\n"
                f"- Over the past year it returned {p(s['ret_1y'], 1)}, vs {p(s['spy_ret_1y'], 1)} for the S&P 500 {ref('snapshot')}.\n"
                f"- Price vs its 200-day average: a price above a rising 200-day average is the most common definition of "
                f"an uptrend {ref('moving')}.\n"
                f"- RSI {s['rsi14']:.0f}: above 70 is traditionally called overbought, below 30 oversold {ref('moving')}.\n\n"
                f"### What history says\nAcross S&P 500 stocks, being above the 200-day average has its own track record "
                f"{ref('signal')}.\n\n"
                f"### What the data can't tell you\nWhere the price goes next. These describe the past.\n\n"
                f"### Try it yourself\nOn the Analyze tab, run Moving averages and Volatility for {t} over 1Y and 5Y and compare."
            )

        def _why(self, t, s, prompt, refs, ref, p):
            from tickertutor import views

            m = views.price_move(t)
            by = {r["period"]: r for r in m["returns"]}
            hi, days = m["from_52_week_high"], m["biggest_down_days"] or m["biggest_up_days"]
            news = [(r, title) for r, title in refs if not title.startswith("Ticker Tutor") and " filed " not in title][:3]
            move = ref("price-move")
            lines = [f"- {title.split(': ', 1)[-1]} [{r}]" for r, title in news] or ["- No headlines about it turned up in the feed."]
            day_lines = [f"- {d['date']}: {p(d['return'], 1)} (the S&P 500 moved {p(d['sp500_same_day'], 1)} that day). That is "
                         f"{d['times_typical_day']:.1f} times its typical daily move, and only {d['days_this_extreme_in_history']} of "
                         f"{d['history_days']:,} trading days in its history were that extreme {move}." for d in days[:2]]
            wk, mo = by["1 week"], by["1 month"]
            return (
                f"### In short\n{s['name']} is {p(mo['stock'], 1)} over the past month while the S&P 500 is {p(mo['sp500'], 1)}, "
                f"so most of the move is about the company or its industry, not the whole market {move}.\n\n"
                f"### What's in the news\n" + "\n".join(lines) + "\n\nThe [In the news](#/news) tab tracks big moves like this one.\n\n"
                f"### The move in numbers\n"
                f"- Past week: {p(wk['stock'], 1)}, which is {p(wk['vs_sp500'], 1)} against the S&P 500. \"Vs the S&P 500\" "
                f"subtracts the market's move, so what's left is specific to the stock {move}.\n"
                f"- It is {p(hi['below_high'], 1)} from its 52-week high, set on {hi['high_date']} {move}.\n"
                + "\n".join(day_lines) + "\n\n"
                f"### How unusual is this?\nIts typical daily move is about {m['typical_daily_move'] * 100:.1f}%, so days like the "
                f"ones above stand out. Across S&P 500 stocks, big one-day drops have their own track record {ref('recent_moves')}.\n\n"
                f"### What the data can't tell you\nHeadlines explain why a price moved. They don't say what it does next.\n\n"
                f"### Try it yourself\nOpen [{t} daily returns](#/analyze?t={t}&a=returns_distribution&p=1y) to see where these days sit, "
                f"and [{t} drawdowns](#/analyze?t={t}&a=drawdown&p=1y) for how deep past drops went."
            )

    StandIn().install(pytypes.SimpleNamespace(setattr=setattr))

    # Stay offline: live headlines fall back to the database snapshot right away.
    from tickertutor.sources import SourceError, news

    def offline(*_a, **_k):
        raise SourceError("live news is off in the offline dev server")
    news.gdelt = offline
    news.market_news = offline


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("TICKERTUTOR_DB", str(ROOT / "data" / "tickertutor.duckdb")))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--delay", type=float, default=1.2, help="seconds the stand-in 'thinks' per step")
    ap.add_argument("--real-llm", action="store_true", help="use Gemini instead of the stand-in")
    args = ap.parse_args()
    os.environ["TICKERTUTOR_DB"] = args.db
    os.environ.setdefault("FINNHUB_API_KEY", "")
    if not args.real_llm:
        install_stand_in(args.delay)
        print("Using the scripted stand-in for the model (no Gemini calls).")
    import uvicorn

    from app import app
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
