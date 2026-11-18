// Screener: the big indexes across the top, then every S&P 500 stock grouped by sector (treemap) or as a sortable list.
import { api, el, pct, num, money, big, cls } from "../api.js";
import { treemap, indexCards } from "../components.js";
import { learnLink } from "../glossary.js";

const COLS = [
  // key, label, numeric?, tooltip, Learn term
  ["ticker", "Stock", false, ""],
  ["market_cap", "Company value", true, "Share price × shares outstanding", "market-cap"],
  ["price", "Price", true, ""],
  ["change_1d", "1 day", true, "Change on the last trading day"],
  ["ret_1m", "1 month", true, "Return over the past month, dividends included"],
  ["ret_1y", "1 year", true, "Return over the past year, dividends included"],
  ["dist_52w_high", "From 52‑wk high", true, "How far below its highest price of the past year", "52-week-high"],
  ["vol_1y", "Volatility", true, "Annualized size of daily swings over the past year", "volatility"],
  ["beta_1y", "Beta", true, "How much it has moved when the S&P 500 moves 1% (past year)", "beta"],
  ["pe", "P/E", true, "Price ÷ the last 12 months of earnings per share", "pe"],
  ["dividend_yield", "Dividend yield", true, "Yearly dividends ÷ price", "dividend-yield"],
];
// A header's last word and its "?" stay on one line when the header wraps.
function withTerm(text, term) {
  if (!term) return [text];
  const i = text.lastIndexOf(" ");
  return [text.slice(0, i + 1), el("span", { style: { whiteSpace: "nowrap" } }, text.slice(i + 1), learnLink(term))];
}
const PERIOD_COLOR = [["change_1d", "1 day"], ["ret_1m", "1 month"], ["ret_ytd", "Year to date"], ["ret_1y", "1 year"]];

function retColor(r, scale) {
  if (r == null) return "#9fb3c8";
  const t = Math.max(-1, Math.min(1, r / scale));
  const mid = [159, 179, 200], up = [23, 121, 90], dn = [194, 73, 47];
  const to = t >= 0 ? up : dn, k = Math.abs(t);
  return `rgb(${mid.map((v, i) => Math.round(v + (to[i] - v) * k)).join(",")})`;
}
const SCALE = { change_1d: 0.03, ret_1m: 0.1, ret_ytd: 0.3, ret_1y: 0.4 };

const saved = { sector: "", view: "sector", sort: "market_cap", dir: -1, q: "", color: "ret_1y" };

export async function render(root, params, ctx) {
  // Grouped by sector unless a link asked for one sector's list (from the Overview or Learn).
  // A link can ask for one sector's list. Otherwise the Screener looks the way you left it.
  if (params.sector) Object.assign(saved, { sector: params.sector, view: "list", q: "" });
  else if (params.view) saved.view = params.view;
  const state = saved;
  const [{ stocks }, ix] = await Promise.all([api("/api/stocks"), api("/api/indexes").catch(() => ({ indexes: [] }))]);
  const info = ctx.meta.sector_info || {};
  if (state.view === "sector") state.sector = "";
  const body = el("div");
  const count = el("span", { class: "muted small" });

  function filtered() {
    const q = state.q.toLowerCase();
    return stocks.filter((s) => (!state.sector || s.sector === state.sector)
      && (!q || s.ticker.toLowerCase().startsWith(q) || s.name.toLowerCase().includes(q)));
  }
  const about = el("p", { class: "sector-about", style: { margin: "0 0 12px", fontSize: "14px" } });
  function draw() {
    const si = state.view === "list" && state.sector ? info[state.sector] : null;
    about.hidden = !si;
    if (si) about.replaceChildren(el("b", {}, `${state.sector}: `), si.about, ` For example: ${si.examples}.`);
    const rows = filtered();
    sectorSel.hidden = state.view === "sector";
    count.textContent = `${rows.length} stocks`;
    body.replaceChildren(state.view === "list" ? table(rows) : bySector(rows));
  }

  function table(rows) {
    if (!rows.length) return el("p", { class: "empty" }, "No stocks match. Clear the sector or the search.");
    const key = state.sort, dir = state.dir;
    rows = rows.slice().sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * dir;
    });
    const head = el("tr", {}, ...COLS.map(([k, label, numeric, tip, term]) => el("th", {
      class: `sortable ${numeric ? "r" : ""}`, title: tip || "Sort", "aria-sort": state.sort === k ? (dir < 0 ? "descending" : "ascending") : null,
      onclick: () => { if (state.sort === k) state.dir = -state.dir; else { state.sort = k; state.dir = numeric ? -1 : 1; } draw(); } },
      ...withTerm(label + (state.sort === k ? (dir < 0 ? " ▾" : " ▴") : ""), term))));
    return el("div", { class: "card table-wrap" }, el("table", { class: "screener-table" }, el("thead", {}, head), el("tbody", {}, ...rows.map((s) =>
      el("tr", { class: "link", onclick: () => { location.hash = `#/stock/${s.ticker}`; } },
        el("td", { class: "name" }, el("a", { class: "tick", href: `#/stock/${s.ticker}` }, s.ticker),
          el("div", { class: "muted small" }, `${s.name} · ${s.sector}`)),
        el("td", { class: "r" }, big(s.market_cap)),
        el("td", { class: "r" }, money(s.price)),
        el("td", { class: `r ${cls(s.change_1d)}` }, pct(s.change_1d, 1, true)),
        el("td", { class: `r ${cls(s.ret_1m)}` }, pct(s.ret_1m, 1, true)),
        el("td", { class: `r ${cls(s.ret_1y)}` }, pct(s.ret_1y, 0, true)),
        el("td", { class: "r" }, pct(s.dist_52w_high, 0)),
        el("td", { class: "r" }, pct(s.vol_1y, 0)),
        el("td", { class: "r" }, num(s.beta_1y, 2)),
        el("td", { class: "r" }, num(s.pe, 0)),
        el("td", { class: "r" }, s.dividend_yield ? pct(s.dividend_yield, 1) : "—"))))));
  }

  function bySector(rows) {
    const groups = new Map();
    for (const s of rows) {
      if (!groups.has(s.sector)) groups.set(s.sector, []);
      groups.get(s.sector).push(s);
    }
    const key = state.color, scale = SCALE[key];
    const tm = treemap([...groups].map(([sector, items]) => ({ label: sector, items: items.filter((i) => i.market_cap).map((i) => ({
      label: i.ticker, value: i.market_cap, href: `#/stock/${i.ticker}`, title: `${i.name}, ${PERIOD_COLOR.find((p) => p[0] === key)[1]}: ${pct(i[key], 1, true)}`,
      sub: pct(i[key], key === "change_1d" ? 1 : 0, true), ret: i[key] })) })), (c) => retColor(c.ret, scale));
    const legend = el("div", { class: "legend" }, "Size: company value. Color: return ",
      ...[-1, -0.5, 0, 0.5, 1].map((f) => el("span", {}, el("span", { class: "sw", style: { background: retColor(f * scale, scale) } }), ` ${pct(f * scale, 0, true)}`)));
    const colorSeg = el("div", { class: "seg", role: "group", "aria-label": "Color by return over" },
      ...PERIOD_COLOR.map(([v, label]) => el("button", { type: "button", "aria-pressed": String(state.color === v),
        onclick: () => { state.color = v; draw(); } }, label)));
    const cards = el("div", { class: "grid g3", style: { marginTop: "18px" } }, ...[...groups].sort((a, b) => a[0].localeCompare(b[0])).map(([sector, items]) => {
      const sorted = items.slice().sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0));
      const ups = items.filter((i) => (i[key] ?? 0) > 0).length;
      return el("div", { class: "card" }, el("h3", {}, sector),
        info[sector] ? el("p", { class: "sector-about", style: { margin: "4px 0 8px" } }, info[sector].about) : "",
        el("p", { class: "small muted", style: { margin: "0 0 6px" } }, `${items.length} companies · ${ups} up over ${PERIOD_COLOR.find((p) => p[0] === key)[1].toLowerCase()}. Largest:`),
        el("table", {}, el("tbody", {}, ...sorted.slice(0, 5).map((s) =>
          el("tr", { class: "link", onclick: () => { location.hash = `#/stock/${s.ticker}`; } },
            el("td", {}, el("a", { class: "tick", href: `#/stock/${s.ticker}` }, s.ticker)),
            el("td", { class: "r muted small" }, big(s.market_cap)),
            el("td", { class: `r ${cls(s[key])}` }, pct(s[key], 1, true)))))),
        el("button", { class: "btn small ghost", type: "button", onclick: () => { state.view = "list"; state.sector = sector; sectorSel.value = sector; syncView(); draw(); } },
          `All ${items.length} in ${sector}`));
    }));
    return el("div", {}, el("div", { class: "chart-controls" }, legend, colorSeg), tm, cards);
  }

  const viewSeg = el("div", { class: "seg", role: "group", "aria-label": "View" },
    ...[["sector", "By sector"], ["list", "One by one"]].map(([v, label]) => el("button", { type: "button", "data-v": v,
      onclick: () => { state.view = v; syncView(); draw(); } }, label)));
  function syncView() {
    viewSeg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === state.view)));
  }
  const sectorSel = el("select", { "aria-label": "Sector", onchange: () => { state.sector = sectorSel.value; draw(); } },
    el("option", { value: "" }, "All sectors"), ...ctx.meta.sectors.map((s) => el("option", { value: s, selected: s === state.sector }, s)));
  let t;
  const search = el("input", { type: "search", placeholder: "Search ticker", "aria-label": "Search by ticker or company name", value: state.q, oninput: () => {
    clearTimeout(t); t = setTimeout(() => { state.q = search.value.trim(); draw(); }, 150); } });
  syncView();
  const indexes = ix.indexes || [];
  root.replaceChildren(
    el("div", { class: "section-head" }, el("div", {}, el("h1", {}, "Screener"),
      el("p", {}, "The big market indexes, then every S&P 500 company and its key numbers, grouped by sector or one by one in a table you can sort. Click any of them to dig in."))),
    indexes.length ? el("section", { style: { marginBottom: "26px" } },
      el("div", { class: "strip-head" }, el("h2", {}, "Market indexes", learnLink("index")),
        el("p", {}, "Followed through the funds that track them, dividends included. Click one to open its page.")),
      indexCards(indexes)) : "",
    el("div", { class: "strip-head" }, el("h2", {}, "S&P 500 companies")),
    el("div", { class: "chart-controls" }, el("div", { class: "chips" }, viewSeg, sectorSel, search), count),
    about, body);
  draw();
}
