"""The research team: a Lead that plans, Researchers that dig in parallel, a Writer
that reports, and a Verifier that checks the report against the evidence.

    question ─► Lead: clear enough?  ──no──► clarifying question back to the user
                  │ yes: plan 2–5 tasks
                  ▼
        Researchers (parallel, each in a fresh context with its own tools)
                  │ findings with citation ids
                  ▼
        Lead: any gaps? ──yes──► another round (up to MAX_ROUNDS, within the time budget)
                  │ no
                  ▼
        Writer: cited report ─► Verifier: every number and citation backed? ─► (one revision) ─► answer

Every step, including each Researcher's tool calls, is recorded in tool_calls
with an "agent" field, so /chat shows the work.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Callable

from google.genai import types

from . import config, indexes, llm
from .data import db, find_company
from .tools import ROLE_TOOLS, TOOLS, Sources, preview, run_tool

log = logging.getLogger("tickertutor.agents")

DISCLAIMER = ("Educational, not financial advice. Ticker Tutor explains analyses and evidence. It doesn't recommend "
              "buying or selling anything, and past results don't guarantee future returns.")

ROLE_NAMES = {"market": "Market data researcher", "fundamentals": "Fundamentals researcher", "news": "News researcher"}


# --- sessions (conversation memory) ------------------------------------------------------------------------

class Sessions:
    def __init__(self, cap: int = 500):
        self._items: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self.cap = cap

    def get(self, sid: str | None) -> dict:
        with self._lock:
            if sid and sid in self._items:
                self._items.move_to_end(sid)
                return self._items[sid]
            sid = "s_" + secrets.token_hex(8)
            s = {"id": sid, "turns": [], "pending": None}
            self._items[sid] = s
            while len(self._items) > self.cap:
                self._items.popitem(last=False)
            return s


sessions = Sessions()


def history_text(session: dict, max_turns: int = 6) -> str:
    lines = []
    for t in session["turns"][-max_turns:]:
        lines.append(f"User: {t['user']}")
        lines.append(f"Ticker Tutor: {t['assistant'][:700]}")
    return "\n".join(lines)


# --- context for the Lead -------------------------------------------------------------------------------------

STOP = {"A", "I", "AN", "THE", "AND", "OR", "IS", "IT", "TO", "OF", "IN", "ON", "AT", "BE", "BY", "FOR", "IF", "SO",
        "DO", "MY", "ME", "WE", "US", "VS", "ETF", "ETFS", "CEO", "AI", "PE", "EPS", "RSI", "SMA", "USA", "OK", "UP",
        "ALL", "ANY", "BUY", "NOW", "YES", "NO", "HOW", "WHAT", "WHY", "WHO", "ARE", "CAN", "HOLD", "LONG", "SELL", "TAX"}


# Everyday names people use that don't match the start of the company's official name.
NICKNAMES = {"google": "GOOGL", "facebook": "META", "coke": "KO", "disney": "DIS", "chase": "JPM", "exxon": "XOM"}


def mentioned_companies(text: str) -> tuple[list[dict], list[str]]:
    """Tickers and company names in the question that Ticker Tutor covers, and ticker-like
    words it doesn't (so the Lead can say they're out of scope)."""
    found, missing = {}, []
    for tok in set(re.findall(r"\b[A-Z]{1,5}(?:\.[A-Z])?\b", text)):
        if tok in STOP or tok in indexes.BY_TICKER:
            continue
        rows = db().rows("SELECT ticker, name, sector FROM companies WHERE ticker = ?", [tok])
        if rows:
            found[tok] = rows[0]
        elif len(tok) >= 2:
            missing.append(tok)
    for word in re.findall(r"[A-Za-z][A-Za-z&'.-]{3,}", text):
        if word.upper() in STOP or len(found) >= 6:
            continue
        word = word.rstrip(".'").removesuffix("'s")
        alias = NICKNAMES.get(word.lower())
        if alias:
            rows = db().rows("SELECT ticker, name, sector FROM companies WHERE ticker = ?", [alias])
            if rows:
                found.setdefault(alias, rows[0])
            continue
        for r in find_company(word, 1):
            if r["name"].lower().removeprefix("the ").startswith(word.lower()) and len(word) >= 4:
                found.setdefault(r["ticker"], r)
    return list(found.values()), missing


# --- Lead ------------------------------------------------------------------------------------------------------

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["clarify", "research", "out_of_scope"]},
        "clarifying_question": {"type": "string", "description": "for clarify: one short question"},
        "options": {"type": "array", "items": {"type": "string"}, "description": "for clarify: 2–4 example answers"},
        "scope_note": {"type": "string", "description": "for out_of_scope, or parts of the question the data can't answer"},
        "restated_question": {"type": "string", "description": "the question, self-contained, using earlier turns"},
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "role": {"type": "string", "enum": ["market", "fundamentals", "news"]},
            "brief": {"type": "string", "description": "what to find out, specific tickers/sectors, what to return"}},
            "required": ["role", "brief"]}},
    },
    "required": ["action", "clarifying_question", "options", "scope_note", "restated_question", "tasks"],
}

LEAD_SYSTEM = """You are the Lead of Ticker Tutor's research team. Ticker Tutor helps beginners learn to analyze S&P 500
stocks on their own: run common analyses (moving averages, trend lines, MACD, RSI, momentum, volatility, Bollinger
Bands, drawdowns, beta, performance vs the index, rolling returns, return distributions, volume), understand what the
numbers mean, and see what history and the news say. It explains; it never recommends buying or selling anything,
never ranks stocks as good or bad picks, and doesn't do day-trading timing, options, shorting, crypto, or personal
financial or tax advice.

Data available to your Researchers:
- market: Ticker Tutor's analyses on daily prices (run_analysis), stock snapshots and returns vs the S&P 500 and sector,
  sorted lists of facts, backtested track records of 15 popular signals (did stocks with the signal beat the S&P 500
  over the next 12 months?), and read-only SQL on the database. run_analysis also works on the four big indexes
  through the funds that track them: SPY (S&P 500), QQQ (Nasdaq-100), DIA (Dow Jones Industrial Average), and
  IWM (Russell 2000). Those indexes are in scope even though only S&P 500 companies have stock pages.
- fundamentals: SEC filings data (revenue, profit, margins, debt, cash flow, dividends, P/E vs own history) and the
  Risk Factors text of 10-K annual reports (what's new vs last year).
- news: live company and market news (the same feed as the app's "In the news" tab), recent big price moves and
  earnings reactions with historical base rates, SEC 8-K filings, and Google-grounded web search.
Both market and news Researchers can also measure a move with get_price_move: returns over 1 day to this year next to
the S&P 500 and the sector, distance from the 52-week high, the biggest days, and how unusual they are for the stock.
"""

TRIAGE_RULES = """Decide what to do with the user's message.
- clarify: the request is too vague to research well, or asks Ticker Tutor to pick stocks ("what should I buy?",
  "best stocks?", "is it a good stock?" with no company). Ask ONE short question that turns it into something
  Ticker Tutor can help them analyze or learn: which company or sector, or which kind of analysis (trend, risk, how it
  compares with the market, what's in the news). Options should be concrete things to analyze, never picks. Never ask
  about income, savings, age, or account size. If the user is answering an earlier clarifying question, research.
- out_of_scope: entirely outside the data (crypto, options, forex, day-trading timing, shorting, stocks not in the
  S&P 500, personal tax filing). Write scope_note explaining what Ticker Tutor covers instead.
- research: everything else. If part can't be answered (e.g. "will it go up next month?" or "should I buy it?"),
  still research what the data can show (analyses, history, track records) and put the unanswerable part in
  scope_note, including that Ticker Tutor doesn't make recommendations.
"Why did it move" questions ("why is Nvidia down so bad?", "what happened to Tesla?", "why did it jump?") are
research, never clarify, as long as a company, index, or sector is named. Casual or blunt wording is fine. Plan at
least these two tasks so the answer has both the story and the numbers:
  1. news: find what was reported around the move. Call get_price_move first to get the dates of the biggest days,
     then get_company_news, get_recent_moves, and get_recent_filings for that ticker, and get_market_news or web_search
     if the whole market or sector moved. Return headlines with dates and links, matched to the days the price moved.
  2. market: size up the move with get_price_move (returns vs the S&P 500 and sector, distance from the 52-week
     high, biggest days and how unusual they were) and run_analysis drawdown and returns_distribution over 1y.
Add a fundamentals task only if earnings or the company's finances look like part of the story.
For research, plan 2–5 tasks for Researchers who start with no context: name tickers/sectors explicitly, say exactly
which analyses to run (by name, with periods) or what to find, and split work so tasks don't overlap. Prefer
run_analysis for questions about trends, momentum, risk, or performance, so the answer teaches how to read them."""


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "enough": {"type": "boolean"},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "tasks": {"type": "array", "items": TRIAGE_SCHEMA["properties"]["tasks"]["items"]},
    },
    "required": ["enough", "gaps", "tasks"],
}


# --- Researcher -------------------------------------------------------------------------------------------------

RESEARCHER_SYSTEM = """You are a {role_name} on Ticker Tutor's research team (an educational tool that helps beginners
learn to analyze S&P 500 stocks themselves). You start fresh: everything you know about this task is in the brief.
Use your tools to gather evidence; don't rely on memory for numbers. Data is as of {as_of}.
Rules:
- Every factual claim must cite the ref id(s) from the tool result it came from, like [S3].
- If a tool says the data doesn't cover something, record that under cannot_answer instead of guessing.
- Stop when you have what the brief asks for (at most {steps} tool rounds).
- Finish with ONLY a JSON object (no prose around it):
  {{"summary": "2-4 sentences", "findings": [{{"claim": "...", "refs": ["S1"], "confidence": "high|medium|low"}}],
    "gaps": ["what you couldn't find"], "cannot_answer": ["parts the data can't answer"]}}"""


def _declarations(role: str) -> list[types.FunctionDeclaration]:
    return [types.FunctionDeclaration(name=n, description=TOOLS[n].description, parameters_json_schema=TOOLS[n].parameters)
            for n in ROLE_TOOLS[role]]


def parse_json_text(text: str) -> dict | None:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


class Run:
    """One question through the whole team."""

    def __init__(self, question: str, session: dict, on_event: Callable[[dict], None] | None = None):
        self.question = question
        self.session = session
        self.emit = on_event or (lambda e: None)
        self.sources = Sources()
        self.tool_calls: list[dict] = []
        self._lock = threading.Lock()
        self.t0 = time.time()
        self.deadline = self.t0 + config.TIME_BUDGET_SECONDS
        self.researcher_count = 0

    # bookkeeping
    def record(self, agent: str, name: str, args: dict, result) -> None:
        entry = {"agent": agent, "name": name, "args": args, "result": preview(result) if isinstance(result, dict) else result}
        with self._lock:
            self.tool_calls.append(entry)
        self.emit({"type": "tool_call", **entry})

    def time_left(self) -> float:
        return self.deadline - time.time()

    # --- Lead ---------------------------------------------------------------------------------------------------
    def triage(self) -> dict:
        found, missing = mentioned_companies(self.question)
        pending = self.session.get("pending")
        context = [f"Today: {date.today().isoformat()}. Data as of {db().meta().get('as_of')}."]
        if found:
            context.append("Companies in the question that Ticker Tutor covers: " +
                           ", ".join(f"{f['ticker']} ({f['name']}, {f['sector']})" for f in found))
        named_indexes = indexes.find(self.question)
        if named_indexes:
            context.append("Indexes in the question (analyze them through their funds with run_analysis): " +
                           ", ".join(f"{i['ticker']} ({i['name']})" for i in named_indexes))
        if missing:
            context.append("Ticker-like words not in Ticker Tutor's S&P 500 data: " + ", ".join(missing[:6]))
        hist = history_text(self.session)
        if hist:
            context.append("Conversation so far:\n" + hist)
        if pending:
            context.append(f"You asked a clarifying question about \"{pending['question']}\": \"{pending['asked']}\". "
                           "The user's message below is their answer.")
        prompt = "\n".join(context) + f"\n\nUser's message: {self.question}\n\n{TRIAGE_RULES}"
        plan = llm.generate_json(prompt, TRIAGE_SCHEMA, system=LEAD_SYSTEM, thinking=config.GEMINI_THINKING)
        plan["tasks"] = [t for t in plan.get("tasks", []) if t.get("role") in ROLE_TOOLS][: config.MAX_RESEARCHERS]
        if plan.get("action") == "research" and not plan["tasks"]:
            plan["tasks"] = [{"role": "market", "brief": plan.get("restated_question") or self.question}]
        self.record("lead", "plan_research", {"question": self.question}, {
            "action": plan.get("action"), "restated_question": plan.get("restated_question"),
            "tasks": plan.get("tasks"), "clarifying_question": plan.get("clarifying_question"),
            "scope_note": plan.get("scope_note")})
        self.emit({"type": "plan", "plan": plan})
        return plan

    def review(self, question: str, findings: list[dict], round_no: int) -> dict:
        prompt = (f"Question: {question}\nRound {round_no} of at most {config.MAX_ROUNDS}. Findings so far:\n"
                  + json.dumps(findings, ensure_ascii=False)[:12000]
                  + "\n\nIs this enough to answer the question well, with numbers, track records where relevant, and "
                    "risks? If something important is missing or the findings conflict, list the gaps and give 1–3 new "
                    "tasks (fresh Researchers, so be specific). Don't repeat work already done.")
        rv = llm.generate_json(prompt, REVIEW_SCHEMA, system=LEAD_SYSTEM, thinking=config.GEMINI_TOOL_THINKING)
        rv["tasks"] = [t for t in rv.get("tasks", []) if t.get("role") in ROLE_TOOLS][:3]
        self.record("lead", "review_findings", {"round": round_no}, rv)
        self.emit({"type": "review", "round": round_no, "review": rv})
        return rv

    # --- Researchers ----------------------------------------------------------------------------------------------
    def researcher(self, task: dict, n: int) -> dict:
        role = task["role"]
        agent = f"researcher:{role}#{n}"
        self.emit({"type": "researcher_start", "agent": agent, "role": role, "brief": task["brief"]})
        system = RESEARCHER_SYSTEM.format(role_name=ROLE_NAMES[role], as_of=db().meta().get("as_of"),
                                          steps=config.MAX_RESEARCHER_STEPS)
        cfg = types.GenerateContentConfig(system_instruction=system,
                                          tools=[types.Tool(function_declarations=_declarations(role))],
                                          automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        history = [types.Content(role="user", parts=[types.Part(text=f"Brief: {task['brief']}")])]
        final = ""
        for step in range(config.MAX_RESEARCHER_STEPS + 1):
            if self.time_left() < 25:
                history.append(types.Content(role="user", parts=[types.Part(text="Time is up: reply now with the JSON.")]))
            try:
                resp = llm.generate(history, cfg, config.GEMINI_TOOL_THINKING)
            except Exception as exc:  # noqa: BLE001
                final = json.dumps({"summary": f"Researcher stopped: {llm.describe_api_error(exc)}", "findings": [],
                                    "gaps": [task["brief"]], "cannot_answer": []})
                break
            content = resp.candidates[0].content if resp.candidates else None
            if content is None or not content.parts:
                break
            history.append(content)
            calls = [p.function_call for p in content.parts if p.function_call]
            if not calls or step == config.MAX_RESEARCHER_STEPS:
                final = "".join(p.text for p in content.parts if p.text and not p.thought)
                if calls:   # out of steps: ask for the JSON
                    history.append(types.Content(role="user", parts=[types.Part(text="No more tools: reply with the JSON now.")]))
                    try:
                        r2 = llm.generate(history, types.GenerateContentConfig(system_instruction=system),
                                          config.GEMINI_TOOL_THINKING)
                        final = r2.text or final
                    except Exception:  # noqa: BLE001
                        pass
                break
            parts = []
            for fc in calls:
                args = dict(fc.args or {})
                result = run_tool(self, fc.name, args)
                self.record(agent, fc.name, args, result)
                parts.append(types.Part(function_response=types.FunctionResponse(id=fc.id, name=fc.name,
                                                                                 response={"result": result})))
            history.append(types.Content(role="user", parts=parts))
        out = parse_json_text(final) or {"summary": final.strip()[:800], "findings": [], "gaps": [], "cannot_answer": []}
        out.update({"agent": agent, "role": role, "brief": task["brief"]})
        self.emit({"type": "researcher_done", "agent": agent, "summary": out.get("summary", "")})
        return out

    def research_round(self, tasks: list[dict]) -> list[dict]:
        numbered = []
        for t in tasks:
            self.researcher_count += 1
            numbered.append((t, self.researcher_count))
        with ThreadPoolExecutor(max_workers=max(1, len(numbered))) as pool:
            return list(pool.map(lambda tn: self.researcher(*tn), numbered))

    # --- Writer & Verifier ----------------------------------------------------------------------------------------
    def write(self, question: str, findings: list[dict], scope_note: str, issues: list[dict] | None = None,
              draft: str = "") -> str:
        srcs = "\n".join(f"[{r}] {s['title']}" + (f" <{s['url']}>" if s["url"] else "") for r, s in self.sources.items.items())
        pages = "\n".join(f"- [{label}]({href})" for label, href in self.pages().items())
        prompt = (
            f"Question: {question}\nData as of {db().meta().get('as_of')}.\n"
            + (f"Scope note (parts the data can't answer, say so plainly): {scope_note}\n" if scope_note else "")
            + f"\nResearch findings (JSON):\n{json.dumps(findings, ensure_ascii=False)[:16000]}\n\nSources:\n{srcs}\n\n"
        )
        if issues:
            prompt += ("A fact-checker found problems in your draft. Fix every one, change nothing else.\nIssues:\n"
                       + json.dumps(issues, ensure_ascii=False) + f"\n\nDraft:\n{draft}\n")
        else:
            prompt += (
                "Write the answer for a beginner who is learning to analyze stocks. Plain words, short paragraphs, "
                "markdown headings allowed. Structure:\n"
                "1. **In short** (2–3 sentences: what the analyses and evidence show).\n"
                "2. **What the numbers show**: the key results, each followed by its citation like [S2]. When you "
                "mention an analysis (RSI, beta, drawdown…), add one plain sentence on how to read that number.\n"
                "3. **What history says**: for any signal or pattern you mention, how it has worked across S&P 500 "
                "stocks (cite it). Say clearly when a popular signal has no clear edge.\n"
                "4. **What the data can't tell you**: limits, including that nobody can predict future prices.\n"
                "5. **Try it yourself**: name the Ticker Tutor analyses (and periods) the reader can run on the Analyze "
                "page to explore this further.\n"
                "If the question asks why something moved (why is it down, what happened, why did it jump), use this "
                "structure instead:\n"
                "1. **In short** (2–3 sentences: how big the move is and the most likely reasons in the news).\n"
                "2. **What's in the news**: the reported reasons, each with its date and citation, matched to the days "
                "the price moved. If the news doesn't clearly explain the move, say so. Mention that the In the news "
                "tab tracks moves like this.\n"
                "3. **The move in numbers**: its return over the past day, week, and month next to the S&P 500 and its "
                "sector, how far it is below its 52-week high, and its biggest days with how many times a typical day "
                "they were (cite each). Explain in one sentence what 'vs the S&P 500' and 'typical daily move' mean.\n"
                "4. **How unusual is this?**: how often days or drops this size have happened in this stock's history, "
                "and what has usually followed similar moves across S&P 500 stocks (cite the base rates).\n"
                "5. **What the data can't tell you**: news explains the past, and nobody knows what comes next.\n"
                "6. **Try it yourself**: the pages to open next.\n"
                + (f"You may link to these Ticker Tutor pages with markdown links, using exactly these targets:\n{pages}\n"
                   if pages else "")
                + "Rules: only use facts from the findings; cite only the [S#] ids listed above; never invent numbers; "
                "if findings disagree, say so. Never recommend buying, selling, or holding, and never call a stock a "
                "good or bad pick. 250–450 words.")
        text = llm.generate(prompt, types.GenerateContentConfig(system_instruction=
                            "You are the Writer on Ticker Tutor's research team. Clear, honest, beginner-friendly, cited. You explain; "
                            "you never recommend."),
                            config.GEMINI_TOOL_THINKING).text or ""
        return text.strip()

    def pages(self) -> dict[str, str]:
        """Ticker Tutor pages worth pointing the reader to, from what the Researchers looked at."""
        out: dict[str, str] = {}
        for c in self.tool_calls:
            res = c.get("result")
            if not c["agent"].startswith("researcher") or not isinstance(res, dict) or res.get("ok") is False:
                continue
            if c["name"] == "run_analysis" and res.get("chart_link"):
                out.setdefault(f"{res.get('analysis')} for {res.get('ticker')}", res["chart_link"])
            elif c["name"] == "get_price_move":
                out.update({k: v for k, v in (res.get("pages") or {}).items() if k not in out})
            elif c["name"] in ("get_company_news", "get_market_news", "get_recent_moves"):
                out.setdefault("In the news", "#/news")
        return dict(list(out.items())[:8])

    def verify(self, draft: str, findings: list[dict]) -> dict:
        evidence = [{"agent": c["agent"], "name": c["name"], "args": c["args"], "result": c["result"]}
                    for c in self.tool_calls if c["agent"].startswith("researcher")]
        prompt = ("Check this report against the evidence. Flag any number or claim that isn't supported by the tool "
                  "results, any citation [S#] that doesn't match the source, missing citations on key numbers, and any "
                  "sentence that recommends buying, selling, or holding, or calls a stock a good or bad pick. Ignore style and "
                  "ignore links to Ticker Tutor pages (targets starting with #/).\n\nReport:\n" + draft +
                  "\n\nTool results:\n" + json.dumps(evidence, ensure_ascii=False, default=str)[:24000] +
                  "\n\nValid source ids: " + ", ".join(self.sources.items))
        rv = llm.generate_json(prompt, VERIFY_SCHEMA, system="You are the Verifier on Ticker Tutor's research team. "
                               "Be strict about numbers and citations.", thinking=config.GEMINI_TOOL_THINKING)
        return rv

    # --- the whole run -------------------------------------------------------------------------------------------
    def run(self) -> dict:
        plan = self.triage()
        action = plan.get("action")
        if action == "clarify":
            q = plan.get("clarifying_question") or "Could you say a bit more about what you'd like to look into?"
            opts = plan.get("options") or []
            self.session["pending"] = {"question": self.question, "asked": q}
            text = q + ("\n\nFor example: " + "; ".join(f"“{o}”" for o in opts[:4]) if opts else "")
            return self.finish(text, clarification=True)
        self.session["pending"] = None
        if action == "out_of_scope":
            note = plan.get("scope_note") or "That's outside what Ticker Tutor's data covers."
            text = (f"{note}\n\nTicker Tutor covers current S&P 500 stocks: common analyses (trends, momentum, "
                    f"volatility, drawdowns, beta, performance vs the index), company financials from SEC filings, "
                    f"track records of popular signals, and recent news.\n\n_{DISCLAIMER}_")
            return self.finish(text)
        question = plan.get("restated_question") or self.question
        findings: list[dict] = []
        tasks = plan["tasks"]
        round_no = 0
        stopped = ""
        while tasks and round_no < config.MAX_ROUNDS:
            round_no += 1
            self.emit({"type": "round", "round": round_no, "tasks": tasks})
            findings += self.research_round(tasks)
            if round_no >= config.MAX_ROUNDS:
                stopped = f"the {config.MAX_ROUNDS}-round limit"
                break
            if self.time_left() < config.TIME_BUDGET_SECONDS * 0.45:
                stopped = "the time budget"
                break
            rv = self.review(question, findings, round_no)
            tasks = [] if rv.get("enough") else rv.get("tasks", [])
        scope_note = plan.get("scope_note", "") or ""
        if stopped:
            # Say what wasn't followed up, rather than quietly answering with less.
            gaps = list(dict.fromkeys(g for f in findings for g in (f.get("gaps") or []) if isinstance(g, str) and g.strip()))[:4]
            self.record("lead", "stop_research", {"reason": stopped}, {"rounds": round_no, "unresolved_gaps": gaps})
            if gaps:
                scope_note = (scope_note + " " if scope_note else "") + (
                    f"Research stopped at {stopped}; these weren't followed up: " + "; ".join(gaps) + ".")
        self.emit({"type": "writing"})
        draft = self.write(question, findings, scope_note)
        self.record("writer", "write_report", {"findings": len(findings), "sources": len(self.sources.items)},
                    {"draft_chars": len(draft)})
        try:
            check = self.verify(draft, findings)
        except llm.LLMError as exc:
            check = {"ok": True, "issues": [], "note": f"verification skipped: {exc}"}
        self.record("verifier", "verify_report", {"draft_chars": len(draft)}, check)
        self.emit({"type": "verified", "check": check})
        if not check.get("ok", True) and check.get("issues") and self.time_left() > 20:
            draft = self.write(question, findings, scope_note, check["issues"], draft)
            self.record("writer", "revise_report", {"issues": len(check["issues"])}, {"draft_chars": len(draft)})
        return self.finish(self.cite(draft))

    def cite(self, text: str) -> str:
        """[S3] → numbered [1] links, plus a Sources list. Unknown ids are dropped."""
        order: list[str] = []

        def sub(m):
            refs = [r.strip() for r in re.split(r"[,\s]+", m.group(1)) if r.strip()]
            nums = []
            for r in refs:
                if r in self.sources.items:
                    if r not in order:
                        order.append(r)
                    nums.append(str(order.index(r) + 1))
            return "".join(f"[{n}]" for n in nums)

        body = re.sub(r"\[((?:S\d+(?:\s*,\s*)?)+)\]", sub, text)
        body = re.sub(r"[ \t]+([.,;:])", r"\1", body)
        if DISCLAIMER.split(".")[0] not in body:
            body += f"\n\n_{DISCLAIMER}_"
        if order:
            lines = []
            for i, r in enumerate(order, 1):
                s = self.sources.items[r]
                label = s["title"] + (f" — `{s['detail']}`" if s["kind"] == "data" and s["detail"] else "")
                lines.append(f"{i}. [{label}]({s['url']})" if s["url"] else f"{i}. {label}")
            body += "\n\n**Sources**\n" + "\n".join(lines)
        return body

    def finish(self, text: str, clarification: bool = False) -> dict:
        self.session["turns"].append({"user": self.question, "assistant": text, "clarification": clarification,
                                      "seconds": round(time.time() - self.t0, 1)})
        result = {"response": text, "session_id": self.session["id"], "tool_calls": self.tool_calls}
        self.emit({"type": "done", **result, "sources": list(self.sources.items.values())})
        return result


VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "problem": {"type": "string"}, "fix": {"type": "string"}},
            "required": ["text", "problem", "fix"]}},
    },
    "required": ["ok", "issues"],
}


def answer(message: str, session_id: str | None = None, on_event: Callable[[dict], None] | None = None) -> dict:
    message = (message or "").strip()
    if not message:
        raise ValueError("Ask a question about S&P 500 stocks.")
    session = sessions.get(session_id)
    run = Run(message, session, on_event)
    try:
        return run.run()
    except llm.LLMError as exc:
        return run.finish(f"Sorry, the research team couldn't reach the model: {exc}")
