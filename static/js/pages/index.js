// One market index (through the fund that tracks it): chart, returns next to the other indexes, what it is, risk.
import { api, el, pct, num, money, big, cls, dateStr } from "../api.js";
import { priceChart, facts } from "../components.js";
import { learnLink } from "../glossary.js";

const BACK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>';

export async function render(root, params, ctx) {
  const [d, cat] = await Promise.all([api(`/api/indexes/${encodeURIComponent(params.ticker)}`), api("/api/analyses")]);
  const { index: ix, snapshot: s } = d;
  const isSpy = ix.ticker === "SPY";
  const chart = priceChart(ix.ticker, { noSpy: isSpy });

  // Beta can't run on the S&P 500 fund itself (it would compare it with itself).
  const analyze = el("div", { class: "try-grid" }, ...cat.analyses.filter((a) => !(isSpy && a.id === "beta")).map((a) =>
    el("a", { href: `#/analyze?t=${ix.ticker}&a=${a.id}&p=1y` }, el("small", {}, a.group),
      el("b", {}, a.id === "relative" ? "Performance vs the other indexes" : a.name),
      el("span", {}, a.id === "relative" ? "Total return over your dates next to the other big US indexes." : a.short))));

  const returns = el("div", { class: "table-wrap" }, el("table", { class: "returns-table" },
    el("thead", {}, el("tr", {}, el("th", {}, ""), ...d.periods.map((p) => el("th", { class: "r" }, p.label,
      p.per_year ? el("small", { style: { display: "block", fontWeight: 400 } }, "per year") : "")))),
    el("tbody", {}, ...d.returns.map((r) => el("tr", { class: r.me ? "me" : "link", onclick: r.me ? null : () => { location.hash = `#/index/${r.ticker}`; } },
      el("th", { scope: "row" }, r.me ? r.label : el("a", { class: "tick", href: `#/index/${r.ticker}` }, r.label), el("small", {}, `${r.ticker} fund`)),
      ...r.values.map((v) => el("td", { class: `r ${cls(v)}` }, r.me ? el("b", {}, pct(v, 1, true)) : pct(v, 1, true))))))));

  const months = (days) => Math.round((days || 0) / 30.4);
  const risk = facts([
    ["Biggest drop from a peak", pct(s.max_drawdown, 0), { term: "drawdown", klass: "down",
      note: `${dateStr(s.dd_peak, { month: "short", year: "numeric" })} → ${dateStr(s.dd_trough, { month: "short", year: "numeric" })}` }],
    ["Back to that peak", s.dd_recovered ? dateStr(s.dd_recovered, { month: "short", year: "numeric" }) : "not yet",
      { note: s.dd_recovered ? `${months(s.dd_days_to_recover)} months after the low` : "still below the old peak" }],
    ["Below its peak now", pct(s.current_drawdown, 0), { term: "drawdown" }],
    ["Volatility", pct(s.vol_1y, 0), { note: "yearly swings, past year", term: "volatility" }],
    isSpy ? null : ["Beta", num(s.beta_1y, 2), { note: "moves vs the S&P 500, past year", term: "beta" }],
  ]);

  const h = d.holdings;
  const asks = [`How has the ${ix.name} done against the other big indexes over the past three years, and which swung more?`,
    `Walk me through the ${ix.name}'s trend over the past year using moving averages and RSI.`,
    `How deep were the ${ix.name}'s biggest drops, and how long did it take to recover?`];

  root.replaceChildren(
    el("a", { href: "#/screener", class: "back", html: `${BACK}<span>Screener</span>` }),
    el("div", { class: "stock-head", style: { marginTop: "10px" } },
      el("div", {}, el("div", { class: "title" }, el("h1", {}, ix.name), el("span", { class: "muted", style: { fontSize: "19px" } }, "Market index")),
        el("div", { class: "chips", style: { marginTop: "10px" } },
          el("span", { class: "badge" }, `${ix.members} companies`), el("span", { class: "badge" }, `Weighted ${lower(ix.weighting)}`, learnLink("index-weighting")),
          el("span", { class: "badge" }, `Since ${ix.started}`)),
        el("p", { class: "sector-about", style: { margin: "10px 0 0", maxWidth: "52em" } },
          `An index is a list, so it can't be bought. Ticker Tutor follows it through the ${ix.fund}, a fund that tracks it`, learnLink("index-fund"), ".")),
      el("div", { class: "px" }, el("b", {}, money(s.price)), el("div", { class: cls(s.change_1d) }, `${pct(s.change_1d, 2, true)} last day`),
        el("div", { class: "muted small" }, `${ix.ticker} fund price, as of ${dateStr(s.as_of)}`))),
    el("div", { class: "stock-layout" },
      el("div", {},
        el("div", { class: "card" },
          chart,
          el("div", { class: "grid g4 stats-row", style: { marginTop: "14px" } },
            stat("Past year", pct(s.ret_1y, 1, true), cls(s.ret_1y), "dividends included"),
            stat("5 yrs, per year", pct(s.ret_5y_ann, 1, true), cls(s.ret_5y_ann)),
            stat(["From 52-week high", learnLink("52-week-high")], pct(s.dist_52w_high, 1), cls(s.dist_52w_high)),
            stat(["RSI (14 day)", learnLink("rsi")], num(s.rsi14, 0), "", s.rsi14 > 70 ? "often called overbought" : s.rsi14 < 30 ? "often called oversold" : "neutral range"))),
        el("div", { class: "card" }, el("h2", {}, "Returns"),
          el("p", { class: "muted small", style: { margin: "4px 0 10px" } }, `The ${ix.name} next to the other big indexes. Dividends included`, learnLink("total-return"),
            ". 3- and 5-year figures are per year", learnLink("annualized"), "."),
          returns),
        el("div", { class: "card" }, el("h2", {}, `Analyze the ${ix.name}`),
          el("p", { class: "muted small", style: { margin: "4px 0 12px" } }, "Open any analysis for this index. You can change the period and settings there, and each one explains how to read it."),
          analyze),
        h ? el("div", { class: "card" }, el("h2", {}, "Its largest companies"),
          el("p", { class: "muted small", style: { margin: "4px 0 10px" } }, `The 10 biggest of ${h.n} make up about ${pct(h.top_share, 0)} of the index's value, `
            + "which is why a few names can move the whole thing. Shares are approximate, from each company's value", learnLink("market-cap"), "."),
          el("div", { class: "table-wrap" }, el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "Company"), el("th", {}, "Sector"), el("th", { class: "r" }, "Company value"),
              el("th", { class: "r" }, "Share of index"), el("th", { class: "r" }, "1 year"))),
            el("tbody", {}, ...h.top.map((r) => el("tr", { class: "link", onclick: () => { location.hash = `#/stock/${r.ticker}`; } },
              el("td", { class: "name" }, el("a", { class: "tick", href: `#/stock/${r.ticker}` }, r.ticker), el("span", { class: "muted" }, ` ${r.name}`)),
              el("td", { class: "muted" }, r.sector), el("td", { class: "r" }, big(r.market_cap)), el("td", { class: "r" }, pct(r.share, 1)),
              el("td", { class: `r ${cls(r.ret_1y)}` }, pct(r.ret_1y, 0, true)))))))) : ""),
      el("aside", {},
        el("div", { class: "card" }, el("h3", {}, "What it is"),
          el("p", { style: { margin: "8px 0 0", fontSize: "15px" } }, ix.about),
          el("p", { style: { margin: "10px 0 0", fontSize: "15px" } }, el("b", {}, "Keep in mind: "), ix.watch),
          el("p", { class: "small", style: { margin: "10px 0 0" } }, el("a", { href: `#/learn?term=${ix.id}` }, "More about indexes on Learn"))),
        el("div", { class: "card" }, el("h3", {}, "Risk"),
          el("p", { class: "muted small", style: { margin: "4px 0 2px" } }, `Drops are measured since ${dateStr(s.history_start, { year: "numeric" })}, where the price history here starts.`),
          risk),
        el("div", { class: "card" }, el("h3", {}, "Ask the research desk"),
          el("div", { class: "examples", style: { marginTop: "10px" } }, ...asks.map((q) => el("button", { type: "button", onclick: () => { location.hash = `#/research?q=${encodeURIComponent(q)}`; } }, q)))),
        el("div", { class: "card" }, el("h3", {}, "The other indexes"),
          el("table", { style: { marginTop: "6px" } }, el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", { class: "r" }, "1 month"), el("th", { class: "r" }, "1 year"))),
            el("tbody", {}, ...d.others.map((o) => o.available ? el("tr", { class: "link", onclick: () => { location.hash = `#/index/${o.ticker}`; } },
              el("td", {}, el("a", { class: "tick", href: `#/index/${o.ticker}` }, o.label)), el("td", { class: `r ${cls(o.ret_1m)}` }, pct(o.ret_1m, 1, true)),
              el("td", { class: `r ${cls(o.ret_1y)}` }, pct(o.ret_1y, 1, true)))
              : el("tr", {}, el("td", {}, o.label), el("td", { class: "r muted small", colspan: "2" }, "not in this database yet")))))),
        el("p", { class: "disclaimer" }, "Educational, not financial advice. Numbers describe the past. They don't predict future returns, and nothing here is a recommendation."))));
}

const lower = (t) => t.charAt(0).toLowerCase() + t.slice(1);

function stat(label, value, klass = "", sub = "") {
  return el("div", { class: "stat" }, el("span", {}, label), el("b", { class: klass }, value), sub ? el("small", {}, sub) : "");
}
