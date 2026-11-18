"""An offline stand-in for Gemini, so the whole research team runs in tests.

It plays each role the way a good model would on the demo database: the Lead
asks for clarification on vague questions, plans tasks by role, and asks for one
more round when news is missing; Researchers call real tools (on the demo DB)
and cite the refs those tools return; the Writer cites only listed sources; the
Verifier can be told to flag an issue once.
"""

from __future__ import annotations

import json
import re

from google.genai import types


# "why is nvidia down so bad?", "what happened to Tesla?", "why did it jump?"
WHY_MOVED = re.compile(r"\b(why|what happened|what's going on|how come)\b.*\b(down|up|drop|dropp|fall|fell|sink|sank|tank|"
                       r"crash|plung|slid|slump|jump|soar|surg|rall|spik|mov|happen|sell)", re.I)


def _resp(parts: list[types.Part]) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=parts))])


class FakeLLM:
    def __init__(self):
        self.calls: list[str] = []
        self.flag_issue_once = False
        self.force_clarify = False

    def install(self, monkeypatch):
        from tickertutor import llm

        monkeypatch.setattr(llm, "generate_json", self.generate_json)
        monkeypatch.setattr(llm, "generate", self.generate)
        monkeypatch.setattr(llm, "grounded_answer", self.grounded_answer)
        return self

    # --- structured calls (Lead, Verifier) ----------------------------------------------------------------
    def generate_json(self, prompt, schema, system=None, thinking=None, parts=None):
        from tickertutor import agents

        if schema is agents.TRIAGE_SCHEMA:
            self.calls.append("lead.triage")
            msg = prompt.split("User's message:", 1)[1].split("\n\n", 1)[0].strip().lower()
            answering = "The user's message below is their answer" in prompt
            covered = re.findall(r"([A-Z]{1,5}(?:\.[A-Z])?) \(", prompt.split("Companies in the question that Ticker Tutor covers:", 1)[1].split("\n")[0]) \
                if "Companies in the question that Ticker Tutor covers:" in prompt else []
            if any(w in msg for w in ("bitcoin", "crypto", "options")):
                return {"action": "out_of_scope", "clarifying_question": "", "options": [],
                        "scope_note": "Ticker Tutor doesn't cover crypto or options.", "restated_question": msg, "tasks": []}
            if (self.force_clarify or msg in ("what should i buy?", "is it good?")) and not answering and not covered:
                return {"action": "clarify",
                        "clarifying_question": "Ticker Tutor doesn't pick stocks, but it can help you analyze them. What would you like to look at?",
                        "options": ["How the biggest consumer staples stocks have moved this year",
                                    "How volatile tech stocks are compared with the market",
                                    "Whether 'buying the dip' has worked historically"], "scope_note": "",
                        "restated_question": msg, "tasks": []}
            if answering:
                sector = "Energy" if "energy" in msg else "Consumer Staples"
                return {"action": "research", "clarifying_question": "", "options": [], "scope_note": "",
                        "restated_question": f"How have the largest {sector} stocks performed this year?",
                        "tasks": [{"role": "market", "brief": f"List the largest {sector} stocks by company value "
                                                              "and run performance vs the S&P 500 for the largest."}]}
            t = covered[0] if covered else "KO"
            if WHY_MOVED.search(msg) and covered:
                return {"action": "research", "clarifying_question": "", "options": [],
                        "scope_note": "Nobody can say where the price goes next.",
                        "restated_question": f"Why has {t} moved recently, and how unusual is the move?",
                        "tasks": [{"role": "news", "brief": f"Find what was reported around the recent move in {t}: news, big moves, filings."},
                                  {"role": "market", "brief": f"Size up the recent move in {t}: price move, drawdown, daily returns."}]}
            scope = "Nobody can predict next month's price." if "next month" in msg else ""
            return {"action": "research", "clarifying_question": "", "options": [], "scope_note": scope,
                    "restated_question": f"What do {t}'s trend and risk analyses show?",
                    "tasks": [{"role": "market", "brief": f"Run moving averages and volatility for {t} over 1y; track record of above_200d."},
                              {"role": "fundamentals", "brief": f"Fundamentals for {t}."}]}
        if schema is agents.REVIEW_SCHEMA:
            self.calls.append("lead.review")
            has_news = '"role": "news"' in prompt or "Why has" in prompt
            m = re.search(r"What do ([A-Z.]+)'s trend", prompt)
            t = m.group(1) if m else "KO"
            if not has_news:
                return {"enough": False, "gaps": ["No recent news or big moves checked."],
                        "tasks": [{"role": "news", "brief": f"Recent news and big moves for {t}."}]}
            return {"enough": True, "gaps": [], "tasks": []}
        if schema is agents.VERIFY_SCHEMA:
            self.calls.append("verifier")
            if self.flag_issue_once:
                self.flag_issue_once = False
                return {"ok": False, "issues": [{"text": "beat the index every year", "problem": "Not in the evidence.",
                                                 "fix": "Remove it."}]}
            return {"ok": True, "issues": []}
        raise AssertionError(f"unexpected schema: {prompt[:100]}")

    # --- tool-calling Researchers and the Writer --------------------------------------------------------------
    def generate(self, contents, cfg, thinking=None):
        sysmsg = (cfg.system_instruction or "") if cfg else ""
        if cfg is not None and cfg.tools:
            return self._researcher(contents, sysmsg)
        self.calls.append("writer")
        prompt = contents if isinstance(contents, str) else str(contents)
        refs = re.findall(r"^\[(S\d+)\]", prompt, re.M)
        cite = "".join(f"[{r}]" for r in refs[:2]) or ""
        fix = "Draft:" in prompt
        body = ("**In short:** The analyses show a mixed picture. " + cite + "\n\n"
                "**What the numbers show:** The moving averages and volatility are summarized above "
                + (f"[{refs[0]}]" if refs else "") + ".\n\n"
                + ("" if fix else "It beat the index every year. ")
                + "**What the data can't tell you:** nobody can predict next year's price. Bogus cite [S999].")
        return _resp([types.Part(text=body)])

    def _researcher(self, contents, sysmsg):
        role = "market" if "Market data" in sysmsg else "fundamentals" if "Fundamentals" in sysmsg else "news"
        self.calls.append(f"researcher.{role}")
        brief = contents[0].parts[0].text
        m = re.search(r"\b([A-Z]{1,5}(?:\.[A-Z])?)\b(?= |;|\.|$)", brief.replace("Brief:", ""))
        tickers = [w for w in re.findall(r"\b[A-Z]{1,5}(?:\.[A-Z])?\b", brief) if w not in {"I", "A"}]
        t = tickers[0] if tickers else "KO"
        last = contents[-1]
        if last.parts and last.parts[0].function_response:
            refs = []
            for c in contents:
                for p in c.parts or []:
                    if p.function_response:
                        refs += re.findall(r"'ref': '(S\d+)'|\"ref\": \"(S\d+)\"", str(p.function_response.response))
            flat = sorted({a or b for a, b in refs})
            return _resp([types.Part(text=json.dumps({
                "summary": f"{role} research on {t} done.",
                "findings": [{"claim": f"{t} {role} evidence collected.", "refs": flat[:3], "confidence": "medium"}],
                "gaps": [], "cannot_answer": []}))])
        if role == "market":
            if "List the largest" in brief:
                sector = "Energy" if "Energy" in brief else "Consumer Staples"
                calls = [("screen_stocks", {"sector": sector, "sort_by": "market_cap", "limit": 5}),
                         ("get_signal_track_record", {"signal_id": "strong_vs_sector"})]
            elif "Size up" in brief:
                calls = [("get_price_move", {"ticker": t, "days": 30}),
                         ("run_analysis", {"ticker": t, "analysis_id": "drawdown", "period": "1y"}),
                         ("run_analysis", {"ticker": t, "analysis_id": "returns_distribution", "period": "1y"})]
            else:
                calls = [("run_analysis", {"ticker": t, "analysis_id": "moving_averages", "period": "1y"}),
                         ("run_analysis", {"ticker": t, "analysis_id": "volatility", "period": "1y"}),
                         ("get_signal_track_record", {"signal_id": "above_200d"})]
        elif role == "fundamentals":
            calls = [("get_fundamentals", {"ticker": t})]
        elif "reported around" in brief:
            calls = [("get_price_move", {"ticker": t}), ("get_company_news", {"ticker": t, "days": 30}),
                     ("get_recent_moves", {"ticker": t}), ("get_recent_filings", {"ticker": t})]
        else:
            calls = [("get_company_news", {"ticker": t}), ("get_recent_moves", {"ticker": t})]
        return _resp([types.Part(function_call=types.FunctionCall(id=f"c{i}", name=n, args=a))
                      for i, (n, a) in enumerate(calls)])

    def grounded_answer(self, prompt, system=None):
        self.calls.append("web")
        return "Example grounded answer.", [{"title": "Example", "url": "https://example.org"}]
