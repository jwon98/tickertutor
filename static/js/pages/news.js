// In the news: what moved recently, the headlines around it, and what history says usually follows.
// Prices come from the daily data update. Headlines are fetched fresh when the page opens.
import { api, el, pct, pts, num, cls, dateStr } from "../api.js";
import { learnLink, termLink } from "../glossary.js";

const EVENT_HELP = {
  one_day_jump: "Stocks that jumped 5 points or more beyond the S&P 500 in a single day",
  one_day_drop: "Stocks that fell 5 points or more beyond the S&P 500 in a single day",
  earnings_up: "Stocks that rose 3 points or more vs the index in the two days after an earnings report",
  earnings_down: "Stocks that fell 3 points or more vs the index in the two days after an earnings report",
};
const HEADLINE_TERMS = ["beat-miss", "guidance", "priced-in", "analyst-rating", "gap", "merger", "fed", "inflation"];

// What the visitor last chose here, kept while they look at other tabs.
const view = { kind: "all", horizon: "1m", movers: "week", more: false };

export async function render(root, params, ctx) {
  const d = await api("/api/news");
  const m = d.market || {};
  const ev = groupEvents(d.events);
  const live = {};   // "TICKER|date" → headlines fetched just now

  // --- big moves ---------------------------------------------------------------------------------------------
  const movesBox = el("div");
  const kindSeg = el("div", { class: "seg", role: "group", "aria-label": "Show" }, ...[["all", "All"], ["jump", "Jumps"], ["drop", "Drops"]].map(([k, label]) =>
    el("button", { type: "button", "data-k": k, onclick: () => { view.kind = k; drawMoves(); } }, label)));
  function drawMoves() {
    kindSeg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.k === view.kind)));
    const all = d.moves.filter((mv) => view.kind === "all" || mv.kind === view.kind);
    if (!all.length) {
      movesBox.replaceChildren(el("p", { class: "empty" }, d.moves.length ? "None of that kind in the last few weeks." : "No unusually big one-day moves in the last few weeks."));
      return;
    }
    const rows = view.more ? all : all.slice(0, 8);
    const out = [];
    let day = "";
    for (const mv of rows) {
      if (mv.date !== day) { day = mv.date; out.push(el("h3", { class: "move-day" }, dateStr(day, { weekday: "long", month: "short", day: "numeric" }))); }
      out.push(moveRow(mv, live[`${mv.ticker}|${mv.date}`] || mv.headlines || []));
    }
    if (all.length > 8) out.push(el("button", { class: "btn small ghost", type: "button", style: { marginTop: "8px" },
      onclick: () => { view.more = !view.more; drawMoves(); } }, view.more ? "Show fewer" : `Show all ${all.length}`));
    movesBox.replaceChildren(...out);
  }
  drawMoves();

  // --- sectors -------------------------------------------------------------------------------------------------
  const sectorBox = el("div");
  const hseg = el("div", { class: "seg", role: "group", "aria-label": "Sector period" }, ...[["1w", "Week"], ["1m", "Month"], ["3m", "3 months"], ["1y", "Year"]].map(([k, label]) =>
    el("button", { type: "button", "aria-pressed": String(k === view.horizon), onclick: (e) => {
      view.horizon = k; hseg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget))); drawSectors(); } }, label)));
  function drawSectors() {
    const key = `etf_ret_${view.horizon}`;
    const rows = d.sectors.filter((s) => s[key] != null).sort((a, b) => b[key] - a[key]);
    const spy = m[`spy_ret_${view.horizon}`];
    const max = Math.max(...rows.map((r) => Math.abs(r[key])), Math.abs(spy || 0), 0.01);
    const x = (v) => `${50 + (v / max) * 48}%`;
    sectorBox.replaceChildren(...rows.map((r) => el("a", { class: "hbar link", href: `#/screener?sector=${encodeURIComponent(r.sector)}`, style: { textDecoration: "none", color: "inherit" } },
      el("span", {}, r.sector, el("small", { class: "muted" }, ` ${r.etf}`)),
      el("div", { class: "track" }, el("span", { class: "zero", style: { left: "50%" } }),
        spy != null ? el("span", { class: "zero", style: { left: x(spy), borderLeft: "2px dashed var(--focus)" }, title: `S&P 500: ${pct(spy, 1, true)}` }) : "",
        el("i", { style: r[key] >= 0 ? { left: "50%", width: `calc(${x(r[key])} - 50%)`, background: "var(--up)" } : { left: x(r[key]), width: `calc(50% - ${x(r[key])})`, background: "var(--down)" } })),
      el("b", { class: `r ${cls(r[key])}` }, pct(r[key], 1, true)))),
      el("p", { class: "small muted", style: { margin: "8px 0 0" } }, "Each bar is a sector fund", learnLink("sector-fund"),
        ". The blue dashed line is the S&P 500 over the same period", spy != null ? ` (${pct(spy, 1, true)}).` : ".", " Click a sector to see its companies."));
  }
  drawSectors();

  // --- biggest gains and losses ----------------------------------------------------------------------------------
  const moversBox = el("div");
  const mseg = el("div", { class: "seg", role: "group", "aria-label": "Period" }, ...[["week", "Week"], ["month", "Month"]].map(([k, label]) =>
    el("button", { type: "button", "data-k": k, onclick: () => { view.movers = k; drawMovers(); } }, label)));
  function drawMovers() {
    mseg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.k === view.movers)));
    const week = view.movers === "week", key = week ? "ret_1w" : "ret_1m";
    const up = week ? d.week.up : d.leaders, down = week ? d.week.down : d.laggards;
    moversBox.replaceChildren(moverTable("Up the most", up, key), moverTable("Down the most", down, key),
      el("p", { class: "small muted", style: { margin: "8px 0 0" } }, week ? "Over the past five trading days. " : "Over the past month. ",
        "One rough stretch says little by itself. Open one to see it against its own history."));
  }
  drawMovers();

  // --- headlines (fetched fresh) ---------------------------------------------------------------------------------
  const headBox = el("ul", { class: "news-list" });
  const stamp = el("span", { class: "small muted" }, "Checking for new headlines…");
  const again = el("button", { class: "btn small ghost", type: "button", onclick: () => refresh() }, "Check again");
  function drawHeadlines(items) {
    headBox.replaceChildren(...(items.length ? items.slice(0, 14).map((h) => el("li", {},
      el("a", { href: h.url, target: "_blank", rel: "noopener" }, h.headline),
      el("small", {}, h.ticker && h.ticker !== "_market" ? [el("a", { class: "tick", href: analyzeHref(h.ticker), style: { marginRight: "6px" } }, h.ticker)] : "",
        `${h.source || h.provider || ""} · ${when(h.published)}`))) : [el("li", { class: "muted" }, "No headlines available right now.")]));
  }
  drawHeadlines(d.headlines);
  async function refresh() {
    again.disabled = true;
    try {
      const n = await api("/api/news/live");
      if (!root.isConnected) return;
      Object.assign(live, n.moves || {});
      if (n.market?.length) drawHeadlines(n.market);
      drawMoves();
      stamp.textContent = n.live ? `Live from ${n.provider}, checked ${new Date(n.fetched_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
        : `Saved with the last data update (${dateStr(d.built_at, { month: "short", day: "numeric" })})`;
    } catch {
      stamp.textContent = "Couldn't reach the news feed. Showing saved headlines.";
    }
    again.disabled = false;
  }

  root.replaceChildren(
    el("div", { class: "section-head" }, el("div", {},
      el("h1", {}, "In the news"),
      el("p", { class: "lede", style: { fontSize: "17px", maxWidth: "48em" } },
        "Big recent moves, the news behind them, and what has usually followed moves like them. ",
        "A headline can explain why a price moved, but it rarely tells you what comes next.")),
      el("p", { class: "fresh" }, "Prices through ", el("b", {}, dateStr(d.as_of, { weekday: "short", month: "short", day: "numeric" })), ". Updated each trading day.")),
    el("div", { class: "card market-strip", style: { marginBottom: "18px" } },
      stat(["S&P 500, past week", learnLink("sp500")], pct(m.spy_ret_1w, 1, true), cls(m.spy_ret_1w), `past month ${pct(m.spy_ret_1m, 1, true)}`),
      stat("Past year", pct(m.spy_ret_1y, 1, true), cls(m.spy_ret_1y), "dividends included"),
      stat(["Stocks above their 200-day average", learnLink("market-breadth")], pct(m.pct_above_200d, 0), "", "how many stocks share the trend"),
      stat(["VIX (expected swings)", learnLink("vix")], num(m.macro_VIXCLS, 1), "", m.macro_VIXCLS > 25 ? "elevated: a nervous market" : m.macro_VIXCLS < 15 ? "low: a calm market" : "around its usual range"),
      stat(["10-year Treasury yield", learnLink("treasury-yield")], m.macro_DGS10 != null ? `${num(m.macro_DGS10, 2)}%` : "—", "", "what 'safe' money earns")),
    el("div", { class: "stock-layout" },
      el("div", {},
        el("div", { class: "card" },
          el("div", { class: "chart-controls" }, el("h2", {}, "Big moves lately", learnLink("big-move")), kindSeg),
          el("p", { class: "muted small", style: { margin: "0 0 4px" } }, "Days when a stock moved at least 5 points more or less than the S&P 500", learnLink("excess-return"),
            ", with the headlines from around that day. Click one to open it on the Analyze tab."),
          movesBox, baseNote(ev)),
        el("div", { class: "card" }, el("h2", {}, "What usually happens next?", learnLink("base-rate")),
          el("p", { class: "muted small", style: { margin: "4px 0 12px" } }, "Every move like these in Ticker Tutor's history, and how those stocks did against the S&P 500 afterwards",
            learnLink("beating-the-index"), ". Hover a number for its 95% range", learnLink("confidence-interval"), "."),
          el("div", { class: "grid g2" }, ...Object.entries(ev).map(([k, rows]) => eventCard(k, rows)))),
        el("div", { class: "card" }, el("div", { class: "chart-controls" }, el("h2", {}, "Sectors", learnLink("sector")), hseg), sectorBox)),
      el("aside", {},
        el("div", { class: "card" }, el("h3", {}, "Market headlines"),
          el("div", { class: "head-stamp" }, stamp, again), headBox),
        el("div", { class: "card" }, el("div", { class: "chart-controls", style: { alignItems: "center" } }, el("h3", {}, "Biggest gains and losses"), mseg), moversBox),
        el("div", { class: "card" }, el("h3", {}, "Words you'll see in headlines"),
          el("p", { class: "related-terms", style: { margin: "10px 0 0" } }, ...HEADLINE_TERMS.map((id) => termLink(id)))))));
  refresh();
}

const analyzeHref = (t, a = "moving_averages", p = "3m") => `#/analyze?t=${encodeURIComponent(t)}&a=${a}&p=${p}`;

function when(iso) {
  if (!iso) return "";
  const t = new Date(iso), hours = (Date.now() - t) / 36e5;
  if (hours >= 0 && hours < 1) return `${Math.max(1, Math.round(hours * 60))} min ago`;
  if (hours >= 1 && hours < 20) return `${Math.round(hours)} hr ago`;
  return dateStr(iso, { month: "short", day: "numeric" });
}

function groupEvents(rows) {
  const out = {};
  for (const r of rows) (out[r.event] ||= []).push(r);
  return out;
}

function eventCard(key, rows) {
  const label = rows[0]?.label || key;
  const help = el("div", { class: "small muted" }, EVENT_HELP[key] || "", key.startsWith("earnings") ? learnLink("earnings-report") : "");
  if (!rows[0]?.n) return el("div", { class: "card", style: { padding: "12px 14px", boxShadow: "none" } }, el("b", {}, label),
    help, el("p", { class: "small muted" }, "No moves like this in the data yet."));
  const order = (h) => (h.includes("3") ? 0 : h.includes("12") ? 1 : 2);
  return el("div", { class: "card", style: { padding: "12px 14px", boxShadow: "none" } },
    el("b", {}, label), help,
    el("dl", { class: "kv", style: { marginTop: "8px" } }, ...rows.slice().sort((a, b) => order(a.horizon) - order(b.horizon)).flatMap((r) => [
      el("dt", {}, `${cap(r.horizon)}: beat the index`), el("dd", { title: `95% range ${pct(r.pos_lo, 0)}–${pct(r.pos_hi, 0)}` }, `${pct(r.pct_positive, 0)}`),
      el("dt", {}, `${cap(r.horizon)}: average vs index`), el("dd", { class: cls(r.mean), title: `95% range ${pts(r.mean_lo)} to ${pts(r.mean_hi)}` }, pts(r.mean)),
    ])),
    el("div", { class: "small muted" }, `${rows[0]?.n ?? 0} moves${rows[0]?.clusters ? `, across ${Math.round(rows[0].clusters)} different months` : ""}.`, verdictLine(rows)));
}

function verdictLine(rows) {
  const r = rows.find((x) => x.horizon.includes("12")) || rows[0];
  if (!r || r.mean_lo == null) return "";
  if (r.mean_lo > 0) return " Over a year, these stocks did better than the index on average, and the range stays above zero.";
  if (r.mean_hi < 0) return " Over a year, these stocks did worse than the index on average, and the range stays below zero.";
  return " Over a year, the range includes zero: no reliable pattern either way.";
}

// One big move. The whole row opens the stock on the Analyze tab; the headlines open their articles.
function moveRow(mv, headlines) {
  const go = analyzeHref(mv.ticker);
  const why = `Why did ${mv.name} (${mv.ticker}) ${mv.kind === "jump" ? "jump" : "drop"} ${pct(Math.abs(mv.ret_1d), 1)} on ${dateStr(mv.date)}? What was in the news, and how unusual was that move for this stock?`;
  const stop = (e) => e.stopPropagation();
  return el("div", { class: "move link", onclick: () => { location.hash = go; } },
    el("a", { class: "tick", href: go, onclick: stop, "aria-label": `Analyze ${mv.ticker}` }, mv.ticker),
    el("div", {},
      el("b", {}, mv.name), el("span", { class: "small muted" }, ` · ${mv.sector}`),
      headlines.length ? el("ul", { class: "move-news" }, ...headlines.map((h) => el("li", {},
        el("a", { href: h.url, target: "_blank", rel: "noopener", onclick: stop }, h.headline),
        el("small", {}, ` ${h.source || h.provider || ""}, ${dateStr(h.published, { month: "short", day: "numeric" })}`))))
        : el("div", { class: "small muted move-none" }, "No headline found around that day."),
      el("div", { class: "small muted move-facts" },
        mv.times_typical ? [el("span", {}, `${num(mv.times_typical, 1)}× its typical day`, learnLink("typical-daily-move"))] : "",
        el("span", {}, `${pct(mv.dist_52w_high, 0)} from its high`, learnLink("52-week-high")),
        el("span", {}, `past year ${pct(mv.ret_1y, 0, true)}`),
        mv.n_with_outcome >= 3 ? el("span", {}, `beat the index the year after ${mv.n_beat_after} of its ${mv.n_with_outcome} earlier ${mv.kind}s like this`) : ""),
      el("div", { class: "move-links" },
        el("a", { href: go, onclick: stop }, `Analyze ${mv.ticker}`),
        el("a", { href: analyzeHref(mv.ticker, "returns_distribution", "1y"), onclick: stop }, "How unusual was it?"),
        el("a", { href: `#/research?q=${encodeURIComponent(why)}`, onclick: stop }, "Ask why"))),
    el("div", { class: `chg ${cls(mv.ret_1d)}` }, pct(mv.ret_1d, 1, true),
      el("div", { class: "small muted", style: { fontWeight: 400, fontSize: "12px" } }, `${pts(mv.excess_1d)} vs S&P 500`)));
}

// What followed moves like these across the whole index, said once for the list.
function baseNote(ev) {
  const year = (k) => (ev[k] || []).find((r) => r.horizon.includes("12"));
  const j = year("one_day_jump"), dr = year("one_day_drop");
  if (!(j?.n >= 20) || !(dr?.n >= 20)) return "";
  return el("p", { class: "small muted", style: { margin: "12px 0 0" } }, "For context: across S&P 500 stocks, ",
    el("b", {}, pct(j.pct_positive, 0)), ` of ${j.n.toLocaleString()} past jumps like these and `, el("b", {}, pct(dr.pct_positive, 0)),
    ` of ${dr.n.toLocaleString()} drops were followed by a year that beat the index`, learnLink("base-rate"), ". A big day by itself says little about the next year.");
}

function moverTable(title, rows, key) {
  return el("table", { class: "movers", style: { marginTop: "8px" } },
    el("thead", {}, el("tr", {}, el("th", { colspan: "2" }, title))),
    el("tbody", {}, ...(rows || []).map((r) => el("tr", { class: "link", onclick: () => { location.hash = analyzeHref(r.ticker); } },
      el("td", {}, el("a", { class: "tick", href: analyzeHref(r.ticker), onclick: (e) => e.stopPropagation() }, r.ticker), el("div", { class: "small muted" }, r.name)),
      el("td", { class: `r ${cls(r[key])}` }, pct(r[key], 1, true))))));
}

function stat(label, value, klass = "", sub = "") {
  return el("div", { class: "stat" }, el("span", {}, label), el("b", { class: klass }, value), sub ? el("small", {}, sub) : "");
}
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
