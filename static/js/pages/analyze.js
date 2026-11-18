// Analyze: pick a stock or index, an analysis, and a period. See the chart, the numbers, and what they mean.
import { api, el, dateStr, pct, pts, big, cls } from "../api.js";
import { meter, verdict, picker } from "../components.js";
import { ANALYSIS_TERMS, termLink, learnLink, statTerm } from "../glossary.js";
import { panelChart, histogramChart, scatterChart } from "../charts.js";

const PERIODS = [["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["ytd", "YTD"], ["1y", "1Y"], ["3y", "3Y"], ["5y", "5Y"], ["max", "Max"]];
const cache = { catalog: null, tickers: null, last: null, recent: [] };
const BACK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>';

export async function render(root, params, ctx) {
  if (!cache.catalog) {
    const [cat, tk] = await Promise.all([api("/api/analyses"), api("/api/tickers")]);
    cache.catalog = cat; cache.tickers = tk.tickers;
  }
  const { analyses, groups } = cache.catalog;
  const byId = Object.fromEntries(analyses.map((a) => [a.id, a]));
  // Nothing is analyzed until a stock or index is picked. The tab itself remembers the last one (see app.js).
  if (!params.t) return start(root, params, byId);
  const reserved = new Set(["t", "a", "p", "start", "end"]);
  const prev = cache.last || {};
  const state = {
    t: params.t.toUpperCase(),
    a: byId[params.a] ? params.a : prev.a || "moving_averages",
    p: params.start ? "custom" : params.p || prev.p || "1y",
    start: params.start || "", end: params.end || "",
    params: Object.fromEntries(Object.entries(params).filter(([k]) => !reserved.has(k))),
  };
  if (state.p === "custom" && !state.start) state.p = "1y";

  // --- stock search -----------------------------------------------------------------------------------------
  const search = picker(cache.tickers, { current: state.t, id: "stock-options", label: "Stock or index",
    onPick: (r) => { state.t = r.ticker; load(); } });

  // --- period ----------------------------------------------------------------------------------------------
  const fromIn = el("input", { type: "date", "aria-label": "From", value: state.start });
  const toIn = el("input", { type: "date", "aria-label": "To", value: state.end });
  const custom = el("div", { class: "custom-dates", hidden: state.p !== "custom" },
    el("label", {}, "From ", fromIn), el("label", {}, "to ", toIn),
    el("button", { class: "btn small", type: "button", onclick: () => {
      if (!fromIn.value) { fromIn.focus(); return; }
      state.start = fromIn.value; state.end = toIn.value; load(); } }, "Apply"));
  const seg = el("div", { class: "seg period-seg", role: "group", "aria-label": "Time period" },
    ...PERIODS.map(([k, lbl]) => el("button", { type: "button", "aria-pressed": String(state.p === k), onclick: () => {
      state.p = k; state.start = ""; state.end = ""; custom.hidden = true; markPeriod(); load(); } }, lbl)),
    el("button", { type: "button", "aria-pressed": String(state.p === "custom"), onclick: () => {
      state.p = "custom"; custom.hidden = false; markPeriod(); fromIn.focus(); } }, "Custom"));
  function markPeriod() {
    const keys = [...PERIODS.map(([k]) => k), "custom"];
    [...seg.children].forEach((b, i) => b.setAttribute("aria-pressed", String(keys[i] === state.p)));
  }

  // --- analysis list (sidebar on wide screens, a select on phones) ----------------------------------------
  const listBox = el("nav", { class: "analysis-list", "aria-label": "Analyses" });
  const select = el("select", { class: "analysis-select", "aria-label": "Analysis", onchange: (e) => pick(e.target.value) });
  for (const g of groups) {
    const items = analyses.filter((a) => a.group === g);
    if (!items.length) continue;
    listBox.append(el("h4", {}, g), ...items.map((a) => el("button", { type: "button", "data-id": a.id, onclick: () => pick(a.id) },
      el("b", {}, a.name), el("span", {}, a.short))));
    select.append(el("optgroup", { label: g }, ...items.map((a) => el("option", { value: a.id }, a.name))));
  }
  function markAnalysis() {
    listBox.querySelectorAll("button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.id === state.a)));
    select.value = state.a;
  }
  function pick(id) { state.a = id; state.params = {}; markAnalysis(); load(); }

  // --- result area -------------------------------------------------------------------------------------------
  const head = el("div", { class: "an-head" });
  const paramsBox = el("div", { class: "an-params" });
  const chartBox = el("div", { class: "card an-chart" });
  const statsBox = el("div", { class: "an-stats" });
  const readout = el("div", { class: "callout an-readout" });
  const explain = el("div", { class: "card an-explain" });
  const evidence = el("div");
  const actions = el("div", { class: "an-actions" });
  const main = el("div", { class: "an-main" }, head, paramsBox, chartBox, statsBox, readout, explain, evidence, actions);

  root.replaceChildren(
    el("a", { href: "#/analyze", class: "back", html: `${BACK}<span>Analyze start</span>` }),
    el("div", { class: "section-head", style: { marginTop: "10px" } }, el("div", {},
      el("h1", {}, "Analyze"),
      el("p", { class: "lede", style: { fontSize: "17px", maxWidth: "48em" } },
        "Change the stock, the analysis, or the time period. Every chart comes with what the numbers mean, how to read them, and what to watch out for."))),
    el("div", { class: "card an-toolbar" },
      search,
      seg, custom),
    el("div", { class: "an-layout" }, el("aside", {}, select, listBox), main));
  markAnalysis();

  let seq = 0, lastRes = null;
  async function load() {
    const my = ++seq;
    cache.last = { t: state.t, a: state.a, p: state.p === "custom" ? "" : state.p };
    const q = new URLSearchParams({ ticker: state.t, a: state.a });
    if (state.p === "custom") { q.set("start", state.start); if (state.end) q.set("end", state.end); }
    else q.set("period", state.p);
    for (const [k, v] of Object.entries(state.params)) if (v !== "" && v != null) q.set(k, v);
    const hash = new URLSearchParams({ t: state.t, a: state.a });
    if (state.p === "custom") { hash.set("start", state.start); if (state.end) hash.set("end", state.end); } else hash.set("p", state.p);
    for (const [k, v] of Object.entries(state.params)) if (v !== "" && v != null) hash.set(k, v);
    history.replaceState(null, "", `#/analyze?${hash}`);
    chartBox.classList.add("loading-dim");
    const a = byId[state.a];
    head.replaceChildren(el("h2", {}, a.name), el("p", { class: "muted" }, a.short));
    let res;
    try {
      res = await api(`/api/analysis?${q}`);
    } catch (e) {
      if (my !== seq) return;
      chartBox.classList.remove("loading-dim");
      chartBox.replaceChildren(el("p", { class: "err" }, e.message));
      statsBox.replaceChildren(); readout.hidden = true;
      drawExplain(a, null);
      drawParams(a.params.map((p) => ({ ...p, value: state.params[p.id] ?? p.default })));
      return;
    }
    if (my !== seq) return;
    lastRes = res;
    chartBox.classList.remove("loading-dim");
    head.replaceChildren(
      el("h2", {}, `${res.analysis.name} `, el("span", { class: "muted", style: { fontWeight: 500 } }, `· ${res.ticker}`)),
      el("p", { class: "muted" }, `${res.kind === "index" ? `${res.name} index, through the fund that tracks it` : res.name} · `
        + `${dateStr(res.period.start)} to ${dateStr(res.period.end)} · `
        + `${res.period.trading_days.toLocaleString()} trading days`
        + (res.period.start > res.period.history_start ? "" : " (all the history Ticker Tutor has)")));
    drawParams(res.params);
    drawChart(res);
    cache.recent = [res.ticker, ...cache.recent.filter((t) => t !== res.ticker)].slice(0, 6);
    statsBox.replaceChildren(...res.summary.map((s) => el("div", { class: "stat" },
      el("span", {}, s.label, statTerm(res.analysis.id, s.label) ? learnLink(statTerm(res.analysis.id, s.label)) : ""),
      el("b", { class: s.fmt === "pct_signed" && typeof s.value === "number" ? (s.value > 0 ? "up" : s.value < 0 ? "down" : "") : "" }, s.text),
      s.note ? el("small", {}, s.note) : "")));
    readout.hidden = false;
    readout.replaceChildren(el("h3", {}, "What this shows"), el("p", {}, res.readout),
      el("p", { class: "small muted", style: { margin: "6px 0 0" } }, "A description of the past, not a prediction or a recommendation."));
    drawExplain(res.analysis, res);
    drawEvidence(res);
    const per = state.p === "custom" ? `from ${res.period.start} to ${res.period.end}` : `over the past ${res.period.label.toLowerCase()}`;
    const subject = res.kind === "index" ? `the ${res.name} (${res.ticker})` : res.ticker;
    const ask = `Explain what the ${res.analysis.name.toLowerCase()} analysis shows for ${subject} ${per}, and what else I should look at to understand it.`;
    actions.replaceChildren(
      el("a", { class: "btn", href: `#/research?q=${encodeURIComponent(ask)}` }, "Ask the research desk about this"),
      res.kind === "index"
        ? el("a", { class: "btn ghost", href: `#/index/${res.ticker}` }, `${res.name} page`)
        : el("a", { class: "btn ghost", href: `#/stock/${res.ticker}` }, `${res.ticker} stock page`));
  }

  function drawChart(res) {
    const w = Math.max(300, chartBox.clientWidth - 32);
    const parts = [];
    if (res.panels.length) parts.push(panelChart(res, w));
    if (res.extra?.kind === "histogram") parts.push(histogramChart(res.extra, w));
    if (res.extra?.kind === "scatter") parts.push(scatterChart(res.extra, w));
    if (res.markers?.length) {
      const ups = res.markers.filter((m) => m.kind === "up"), downs = res.markers.filter((m) => m.kind === "down");
      parts.push(el("p", { class: "small muted", style: { margin: "6px 0 0" } },
        "Markers: ", ups.length ? el("span", { class: "up" }, `▲ ${[...new Set(ups.map((m) => m.label))].join(", ")}`) : "",
        ups.length && downs.length ? " · " : "", downs.length ? el("span", { class: "down" }, `▼ ${[...new Set(downs.map((m) => m.label))].join(", ")}`) : "",
        ". Hover a marker for its date."));
    }
    chartBox.replaceChildren(...parts);
    chartBox.dataset.w = String(w);
  }
  new ResizeObserver(() => {
    if (lastRes && Math.abs(Math.max(300, chartBox.clientWidth - 32) - Number(chartBox.dataset.w || 0)) > 40) drawChart(lastRes);
  }).observe(chartBox);

  function drawParams(ps) {
    if (!ps.length) { paramsBox.replaceChildren(); paramsBox.hidden = true; return; }
    paramsBox.hidden = false;
    const fields = ps.map((p) => {
      const ctl = p.choices
        ? el("select", { "data-id": p.id }, ...p.choices.map((c) => el("option", { value: c.value, selected: String(c.value) === String(p.value) }, c.label)))
        : el("input", { type: "number", "data-id": p.id, value: p.value, min: p.min, max: p.max, step: "any", inputmode: "decimal" });
      ctl.addEventListener("change", () => { state.params[p.id] = ctl.value; load(); });
      return el("label", { class: "param" }, el("span", {}, p.label), ctl, p.help ? el("small", {}, p.help) : "");
    });
    const isDefault = ps.every((p) => String(p.value) === String(p.default));
    paramsBox.replaceChildren(el("span", { class: "param-title" }, "Settings"), ...fields,
      isDefault ? el("small", { class: "muted" }, "Standard settings") :
        el("button", { class: "btn small ghost", type: "button", onclick: () => { state.params = {}; load(); } }, "Back to standard settings"));
  }

  function drawExplain(a) {
    const ex = a.explain;
    const terms = ANALYSIS_TERMS[a.id] || [];
    explain.replaceChildren(el("h3", {}, `About ${a.name}`),
      el("div", { class: "an-explain-grid" },
        sec("What it is", ex.what), sec("How it's calculated", ex.how), sec("How to read it", ex.read), sec("Watch out for", ex.watch)),
      terms.length ? el("p", { class: "related-terms" }, el("span", {}, "Related terms on Learn:"),
        ...terms.map((id) => termLink(id))) : "");
  }

  function drawEvidence(res) {
    const ev = res.evidence || [];
    if (!ev.length) { evidence.replaceChildren(); return; }
    const sector = res.sector;
    evidence.replaceChildren(el("details", { class: "method an-evidence" },
      el("summary", {}, "Does this signal predict anything? What history shows across S&P 500 stocks"),
      el("p", { class: "small muted" }, "For each month in the backtest, Ticker Tutor compared S&P 500 stocks with the signal against those without it, and "
        + "checked how often each group beat the index over the next 12 months. It describes the past across hundreds of stocks, not a "
        + "prediction for this one. ", el("a", { href: "#/learn?section=method" }, "How the test works")),
      el("div", { class: "grid g2" }, ...ev.map((c) => el("div", { class: "card", style: { padding: "12px 14px" } },
        el("b", {}, c.label), el("div", { class: "small muted" }, c.description),
        el("div", { style: { margin: "8px 0 4px" } }, verdict(c.verdict)), meter(c),
        c.hit_on != null ? el("div", { class: "small" }, `With it, ${pct(c.hit_on, 0)} of stocks beat the index over the next year. `
          + `Without it, ${pct(c.hit_off, 0)}. Extra return ${pts(c.diff)} a year (95% range ${pts(c.diff_lo)} to ${pts(c.diff_hi)}).`) : "",
        c.sector_card && c.sector_card.hit_on != null ? el("div", { class: "small muted", style: { marginTop: "4px" } },
          `Within ${sector}: `, verdict(c.sector_card.verdict), ` ${pts(c.sector_card.diff)} a year.`) : "")))));
  }

  load();
}

function sec(title, text) {
  return el("section", {}, el("h4", {}, title), el("p", {}, text));
}

// The start screen: a search box and a few places to begin. Nothing runs until something is picked.
async function start(root, params, byId) {
  const a = byId[params.a] ? params.a : "moving_averages";
  const href = (t, p = params.p || "1y") => `#/analyze?t=${encodeURIComponent(t)}&a=${a}&p=${p}`;
  const search = picker(cache.tickers, { id: "stock-options", label: "Stock or index", placeholder: "Search a company, ticker, or index",
    onPick: (r) => { location.hash = href(r.ticker); } });
  const sug = await api("/api/suggestions").catch(() => ({ indexes: [], movers: { up: [], down: [] }, largest: [] }));
  const row = (t, name, value, klass = "", period) => el("a", { class: "sug", href: href(t, period) },
    el("b", {}, t), el("span", {}, name), value != null ? el("em", { class: klass }, value) : "");
  const tidy = (n) => n.replace(/,? (Inc\.?|Corporation|Company|Corp\.?|plc|Ltd\.?)$/i, "").replace(/ \(Class [A-Z]\)$/, "");
  const recent = cache.recent.map((t) => cache.tickers.find((r) => r.ticker === t)).filter(Boolean);
  const mv = sug.movers || { up: [], down: [] };

  root.replaceChildren(
    el("div", { class: "an-start" },
      el("h1", {}, "Analyze"),
      el("p", { class: "lede" }, "Pick a stock or a market index to start. You'll get a chart, the key numbers, and a plain explanation of how to read them."),
      el("div", { class: "home-search" }, search,
        el("button", { class: "btn primary", type: "button", onclick: () => search.submit() }, "Analyze")),
      el("p", { class: "an-start-note" }, params.a && byId[params.a]
        ? ["Opens with ", el("b", {}, byId[a].name), `: ${lowerFirst(byId[a].short)}`]
        : `Opens with ${byId[a].name}. You can switch between all ${Object.keys(byId).length} analyses and any time period once you're in.`)),

    recent.length ? el("section", { class: "sug-group" }, el("h2", {}, "Pick up where you left off"),
      el("div", { class: "sug-list" }, ...recent.map((r) => row(r.ticker, r.kind === "index" ? r.name : tidy(r.name))))) : "",

    sug.indexes.length ? el("section", { class: "sug-group" },
      el("h2", {}, "Market indexes", learnLink("index")),
      el("p", {}, "The whole market, or a slice of it, in one chart. Past-year return shown."),
      el("div", { class: "sug-list" }, ...sug.indexes.map((x) => row(x.ticker, x.label || x.name, pct(x.ret_1y, 1, true), cls(x.ret_1y))))) : "",

    mv.up.length ? el("section", { class: "sug-group" },
      el("h2", {}, "Biggest moves this week"),
      el("p", {}, `S&P 500 stocks that rose or fell the most over the past five trading days${mv.since ? `, since ${dateStr(mv.since, { month: "short", day: "numeric" })}` : ""}. `,
        mv.spy != null ? `The S&P 500 itself moved ${pct(mv.spy, 1, true)}.` : ""),
      el("div", { class: "sug-cols" },
        el("div", { class: "sug-list" }, ...mv.up.map((r) => row(r.ticker, tidy(r.name), pct(r.ret_1w, 1, true), cls(r.ret_1w), "3m"))),
        el("div", { class: "sug-list" }, ...mv.down.map((r) => row(r.ticker, tidy(r.name), pct(r.ret_1w, 1, true), cls(r.ret_1w), "3m")))),
      el("p", { class: "sug-more" }, el("a", { href: "#/news" }, "See the news behind recent moves"))) : "",

    sug.largest.length ? el("section", { class: "sug-group" },
      el("h2", {}, "Largest companies", learnLink("market-cap")),
      el("p", {}, "The biggest companies in the S&P 500 by what the market says they're worth."),
      el("div", { class: "sug-list" }, ...sug.largest.map((r) => row(r.ticker, tidy(r.name), big(r.market_cap))))) : "",

    el("p", { class: "fine-note" }, "These are sorted by size and by recent moves. They are starting points, not suggestions to buy or sell."));
}

const lowerFirst = (t) => t.charAt(0).toLowerCase() + t.slice(1);
