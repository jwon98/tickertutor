// Research desk: a Lead plans, Researchers work in parallel (fresh contexts), a Writer drafts a cited
// report, and a Verifier checks it. The board on the right shows the team working, live.
import { el } from "../api.js";
import { markdown } from "../components.js";

const ROLE = {
  market: { name: "Market data researcher", tools: "analyses on daily prices, returns vs the index, signal track records, SQL" },
  fundamentals: { name: "Fundamentals researcher", tools: "SEC financials, valuation vs history, 10-K risk factors" },
  news: { name: "News researcher", tools: "company and market news, big moves and how unusual they were, earnings reactions, filings, web search" },
};
const EXAMPLES = [
  ["Walk me through Microsoft's trend over the past year using moving averages and RSI, and compare its volatility with the S&P 500's.", "Runs analyses and explains how to read them"],
  ["Why is Nvidia down so much lately?", "Pairs the headlines with how big and how unusual the move is"],
  ["Does buying the dip work for S&P 500 stocks? What has happened after big one-day drops?", "Tests a popular belief against history"],
  ["How do Coca-Cola and PepsiCo compare on volatility, drawdowns, and beta over the last five years?", "Side by side"],
  ["How have the Nasdaq-100 and the Russell 2000 done against the S&P 500 over the past three years, and which swung more?", "The big indexes, compared"],
  ["What should I buy?", "Ticker Tutor doesn't pick stocks: watch the Lead turn this into something you can analyze"],
];

// Module state survives navigation, so a running answer keeps going if you visit another page.
const S = { sid: null, turns: [], busy: false, nodes: null, activeBoard: null };

export async function render(root, params) {
  if (!S.nodes) S.nodes = build();
  const { page } = S.nodes;
  root.replaceChildren(page);
  if (params.q && !S.busy) {
    history.replaceState(null, "", "#/research");
    ask(params.q);
  }
}

function build() {
  const thread = el("div", { class: "thread", "aria-live": "polite" });
  const board = el("div", { class: "board", "aria-label": "The research team" });
  const input = el("textarea", { rows: 2, placeholder: "Ask about S&P 500 stocks, indexes, sectors, or signals…", "aria-label": "Your question", maxlength: 2000 });
  const send = el("button", { class: "btn primary", type: "submit" }, "Ask");
  const reset = el("button", { class: "btn ghost small", type: "button", onclick: () => {
    if (S.busy) return;
    S.sid = null; S.turns = []; thread.replaceChildren(intro()); showBoard(howItWorks()); input.placeholder = "Ask about S&P 500 stocks, indexes, sectors, or signals…";
  } }, "New conversation");
  const form = el("form", { class: "ask", onsubmit: (e) => { e.preventDefault(); ask(input.value); } }, input, send);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  thread.append(intro());
  const page = el("div", {},
    el("div", { class: "section-head" }, el("div", {},
      el("h1", {}, "Research desk"),
      el("p", { class: "lede", style: { fontSize: "17px", maxWidth: "48em" } },
        "Ask a question in plain words. A small team of AI agents digs into Ticker Tutor's data, SEC filings, and the news, then writes a short report where every number links to its source. ",
        "It explains the evidence. It won't tell you what to buy or sell. Answers take one to three minutes.")), reset),
    el("div", { class: "desk" },
      el("div", {}, thread, el("div", { style: { position: "sticky", bottom: "0", background: "var(--paper)", paddingTop: "10px", paddingBottom: "6px" } }, form,
        el("p", { class: "small muted", style: { margin: "6px 2px 0" } }, "Enter to send, Shift+Enter for a new line. Follow-up questions remember the conversation."))),
      board));
  S.nodes = { page, thread, board, input, send };
  showBoard(howItWorks());
  return S.nodes;
}

function intro() {
  return el("div", { class: "card" },
    el("h2", { style: { fontSize: "19px" } }, "Try one of these"),
    el("div", { class: "examples", style: { marginTop: "12px" } }, ...EXAMPLES.map(([q, sub]) =>
      el("button", { type: "button", onclick: () => ask(q) }, q, el("small", {}, sub)))));
}

function howItWorks() {
  const card = (kind, title, text) => el("div", { class: `agent-card ${kind}` }, el("header", {}, el("b", {}, title)), el("div", { class: "brief" }, text));
  return el("div", { class: "board-inner" },
    el("h3", {}, "How the team works"),
    card("lead", "Lead", "Reads your question. If it's too vague, asks you one clarifying question. Otherwise splits it into focused tasks and sends out researchers."),
    card("researcher", "Researchers, in parallel", "Each starts fresh with just its task and a set of tools: market data, company financials and annual reports, or news. They return findings with sources."),
    card("lead", "Lead review", "Checks the findings for gaps or conflicts and sends more researchers if needed (up to 3 rounds)."),
    card("writer", "Writer", "Turns the findings into a short, plain-language report. Every number gets a citation."),
    card("verifier", "Verifier", "Checks each number and citation against what the researchers actually found. If something's off, the Writer fixes it."));
}

function showBoard(node) {
  S.activeBoard = node;
  S.nodes.board.replaceChildren(node);
}

// --- asking ---------------------------------------------------------------------------------------------------
async function ask(text) {
  const q = (text || "").trim();
  const { thread, input, send } = S.nodes;
  if (!q || S.busy) return;
  if (!S.turns.length) thread.replaceChildren();
  thread.querySelectorAll(".report.clarify .chip").forEach((b) => { b.disabled = true; });
  S.busy = true; send.disabled = true; input.value = ""; input.disabled = true;
  const turn = { q, board: liveBoard(), started: Date.now(), plan: null };
  S.turns.push(turn);
  const answer = el("div", { class: "report working" }, el("p", { class: "status run" }, el("span", { class: "spin" }), " The Lead is reading your question…"));
  turn.answer = answer;
  thread.append(el("div", { class: "q" }, q), answer);
  showBoard(turn.board.node);
  answer.scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    await stream(q, (ev) => onEvent(turn, ev));
    if (!turn.done) throw new Error("The connection closed before the answer finished. Please try again.");
  } catch (e) {
    answer.className = "report";
    answer.replaceChildren(el("p", { class: "err" }, e.message),
      el("button", { class: "btn small", type: "button", onclick: () => ask(q) }, "Try again"));
    turn.board.fail(e.message);
  } finally {
    S.busy = false; send.disabled = false; input.disabled = false; input.focus();
    turn.board.stop();
    input.placeholder = "Ask a follow-up…";
  }
}

async function stream(message, handle) {
  let res;
  try {
    res = await fetch("/chat/stream", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: S.sid }) });
  } catch { throw new Error("Can't reach Ticker Tutor. Check your connection and try again."); }
  if (!res.ok) {
    let data = {};
    try { data = await res.json(); } catch { /* empty */ }
    throw new Error(data.error || (typeof data.detail === "string" ? data.detail : "") || `Request failed (${res.status}).`);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      for (const line of chunk.split("\n")) if (line.startsWith("data: ")) handle(JSON.parse(line.slice(6)));
    }
  }
}

function onEvent(turn, ev) {
  const b = turn.board;
  switch (ev.type) {
    case "plan": turn.plan = ev.plan; b.plan(ev.plan); status(turn, ev.plan.action === "research" ? "Researchers are on it…" : "The Lead is replying…"); break;
    case "round": b.round(ev.round, ev.tasks); break;
    case "researcher_start": b.start(ev.agent, ev.role, ev.brief); break;
    case "tool_call": b.call(ev); break;
    case "researcher_done": b.finish(ev.agent, ev.summary); break;
    case "review": b.review(ev.round, ev.review); break;
    case "writing": b.writing(); status(turn, "The Writer is drafting the report…"); break;
    case "verified": b.verified(ev.check); status(turn, ev.check.ok === false ? "The Verifier found issues. The Writer is fixing them…" : "Checked. Finishing up…"); break;
    case "error": throw new Error(ev.error || "Something went wrong.");
    case "done": turn.done = true; S.sid = ev.session_id; b.done(ev); renderAnswer(turn, ev); break;
    default: break;
  }
}

function status(turn, text) {
  if (turn.done) return;
  turn.answer.replaceChildren(el("p", { class: "status run" }, el("span", { class: "spin" }), " ", text));
}

// --- the report -----------------------------------------------------------------------------------------------
function renderAnswer(turn, ev) {
  const a = turn.answer;
  a.className = "report";
  const plan = turn.plan || {};
  if (plan.action === "clarify") {
    a.classList.add("clarify");
    a.replaceChildren(el("div", { class: "small muted", style: { fontWeight: 700, marginBottom: "4px" } }, "The Lead asks"),
      el("p", { style: { fontSize: "17px" } }, plan.clarifying_question || ev.response),
      (plan.options || []).length ? el("div", { class: "chips" }, ...plan.options.slice(0, 4).map((o) =>
        el("button", { class: "chip", type: "button", onclick: () => ask(o) }, o))) : "",
      el("p", { class: "small muted", style: { margin: "10px 0 0" } }, "Pick one or type your own answer below."));
    return;
  }
  const [body, srcText] = ev.response.split(/\n\n\*\*Sources\*\*\n/);
  const content = el("div", { html: markdown(body) });
  const sources = parseSources(srcText || "");
  const srcList = sources.length ? el("div", { class: "sources" }, el("b", {}, "Sources"),
    el("ol", {}, ...sources.map((s) => el("li", { "data-n": s.n }, s.url ? el("a", { href: s.url, target: "_blank", rel: "noopener" }, s.title) : s.title,
      s.detail ? el("code", { style: { marginLeft: "6px" } }, s.detail) : "")))) : "";
  content.addEventListener("click", (e) => {
    const link = e.target.closest("a.cite");
    if (!link) return;
    e.preventDefault();
    const li = a.querySelector(`.sources li[data-n="${link.dataset.src}"]`);
    if (li) { li.scrollIntoView({ behavior: "smooth", block: "center" }); li.classList.add("flash"); setTimeout(() => li.classList.remove("flash"), 1600); }
  });
  const researchers = new Set(ev.tool_calls.filter((c) => c.agent.startsWith("researcher")).map((c) => c.agent)).size;
  const dataCalls = ev.tool_calls.filter((c) => c.agent.startsWith("researcher")).length;
  const secs = Math.round((Date.now() - turn.started) / 1000);
  const verified = ev.tool_calls.find((c) => c.name === "verify_report");
  const revised = ev.tool_calls.some((c) => c.name === "revise_report");
  a.replaceChildren(content, srcList,
    el("div", { class: "made" },
      el("span", {}, `${researchers} researcher${researchers === 1 ? "" : "s"} · ${dataCalls} data lookups · ${sources.length} sources · ${secs}s`),
      verified ? el("span", {}, revised ? "Verifier found issues, Writer fixed them" : "Verifier checked the numbers") : "",
      el("button", { class: "btn small ghost", type: "button", onclick: () => showBoard(turn.board.node) }, "Show the team's work")));
}

function parseSources(text) {
  const out = [];
  for (const line of text.split("\n")) {
    const m = line.match(/^\s*(\d+)\.\s+(.*)$/);
    if (!m) continue;
    let rest = m[2], url = "", title = rest, detail = "";
    const lk = rest.match(/^\[(.*)\]\((https?:\/\/[^)\s]+)\)$/);
    if (lk) { title = lk[1]; url = lk[2]; }
    const dm = title.match(/^(.*?) — `(.*)`$/);
    if (dm) { title = dm[1]; detail = dm[2]; }
    out.push({ n: m[1], title, url, detail });
  }
  return out;
}

// --- the live board -------------------------------------------------------------------------------------------
function liveBoard() {
  const node = el("div", { class: "board-inner" });
  const clock = el("span", { class: "status run" }, "0:00");
  const head = el("div", { class: "board-head" }, el("h3", {}, "The team at work"), clock);
  const lead = agentCard("lead", "Lead", "Reading the question…");
  node.append(head, lead.node);
  const researchers = {};
  let writer = null, verifier = null;
  const t0 = Date.now();
  const timer = setInterval(() => { const s = Math.round((Date.now() - t0) / 1000); clock.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }, 1000);

  return {
    node,
    plan(p) {
      if (p.action === "clarify") lead.set("done", "The question could mean several things, so I'll ask you one question first.");
      else if (p.action === "out_of_scope") lead.set("done", p.scope_note || "That's outside what Ticker Tutor covers.");
      else {
        lead.set("done", el("span", {}, el("b", {}, "Plan: "), p.restated_question || "",
          p.scope_note ? el("div", { class: "small", style: { marginTop: "4px" } }, el("b", {}, "Can't answer from data: "), p.scope_note) : ""));
      }
    },
    round(n, tasks) {
      node.append(el("div", { class: "round-label" }, `Round ${n} · ${tasks.length === 1 ? "1 researcher" : `${tasks.length} researchers in parallel`}`));
    },
    start(agent, role, brief) {
      const num = agent.split("#")[1];
      const c = agentCard("researcher", `${ROLE[role]?.name || role} #${num}`, brief, "run");
      researchers[agent] = c;
      node.append(c.node);
    },
    call(ev) {
      const c = researchers[ev.agent];
      if (!c) return;
      const ok = !(ev.result && ev.result.ok === false);
      const args = Object.entries(ev.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
      c.calls.append(el("div", { class: `call${ok ? "" : " bad"}`, title: `${ev.name}(${args})${ok ? "" : `\n${ev.result.error || ""}`}` }, `${ev.name}(${args})`));
    },
    finish(agent, summary) { const c = researchers[agent]; if (c) { c.set("done"); if (summary) c.note(summary); } },
    review(n, rv) {
      const more = (rv.tasks || []).length;
      const c = agentCard("lead", `Lead review, round ${n}`, rv.enough || !more
        ? "Enough evidence to answer."
        : el("span", {}, el("b", {}, "Gaps: "), (rv.gaps || []).join("; ") || "needs more detail", ` → sending ${more} more researcher${more === 1 ? "" : "s"}.`), "done");
      node.append(c.node);
    },
    writing() { writer = agentCard("writer", "Writer", "Drafting a cited report from the findings…", "run"); node.append(writer.node); },
    verified(check) {
      writer?.set("done", "Draft written.");
      const issues = (check.issues || []).length;
      verifier = agentCard("verifier", "Verifier", check.ok === false && issues
        ? el("span", {}, `Found ${issues} issue${issues === 1 ? "" : "s"}: `, (check.issues || []).map((i) => i.problem || i.claim || "").filter(Boolean).slice(0, 2).join("; "), ". Sent back to the Writer.")
        : (check.note || "Every number and citation matches the evidence."), "done");
      node.append(verifier.node);
    },
    done(ev) {
      if (ev.tool_calls.some((c) => c.name === "revise_report")) node.append(agentCard("writer", "Writer", "Revised the report to fix the Verifier's issues.", "done").node);
      if (!writer && !verifier && (turnAction(ev) === "research")) lead.set("done");
      this.stop();
      clock.className = "status done";
    },
    fail(msg) { this.stop(); clock.className = "status"; node.append(el("p", { class: "err small" }, msg)); },
    stop() { clearInterval(timer); for (const c of Object.values(researchers)) if (c.state === "run") c.set("done"); },
  };
}

function turnAction(ev) { return ev.tool_calls.find((c) => c.name === "plan_research")?.result?.action; }

function agentCard(kind, title, brief, state = "run") {
  const st = el("span", { class: "status" });
  const briefNode = el("div", { class: "brief" });
  const calls = el("div", { class: "calls" });
  const node = el("div", { class: `agent-card ${kind}` }, el("header", {}, el("b", {}, title), st), briefNode, calls);
  const c = {
    node, calls, state,
    note(text) { node.append(el("div", { class: "found" }, el("b", {}, "Found: "), text)); },
    set(s, text) {
      c.state = s;
      st.className = `status ${s}`;
      st.replaceChildren(...(s === "run" ? [el("span", { class: "spin" }), " working"] : [s === "done" ? "done" : s]));
      if (text !== undefined) briefNode.replaceChildren(text);
    },
  };
  c.set(state, brief);
  return c;
}
