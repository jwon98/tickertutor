// One stock: chart, finances, returns vs the index and sector, the analyses you can run on it, risk, news.
import { api, el, pct, num, money, big, cls, dateStr } from "../api.js";
import { priceChart, bars, facts } from "../components.js";
import { learnLink } from "../glossary.js";

const BACK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>';

export async function render(root, params, ctx) {
  // The index funds have their own kind of page.
  if ((ctx.meta.indexes || []).some((i) => i.ticker === params.ticker)) {
    location.replace(`#/index/${params.ticker}`);
    return;
  }
  const d = await api(`/api/stocks/${encodeURIComponent(params.ticker)}`);
  const { company: c, snapshot: s } = d;
  const chart = priceChart(c.ticker);

  const cat = await api("/api/analyses");
  const analyze = el("div", { class: "try-grid" }, ...cat.analyses.map((a) =>
    el("a", { href: `#/analyze?t=${c.ticker}&a=${a.id}&p=1y` }, el("small", {}, a.group), el("b", {}, a.name), el("span", {}, a.short))));

  // Periods across, the stock and its two yardsticks down, so it fits the main column (and scrolls on a phone).
  const short = { "1m": "1 month", "3m": "3 months", ytd: "This year", "1y": "1 year", "3y": "3 years", "5y": "5 years" };
  const retRow = (label, sub, key, me = false) => el("tr", { class: me ? "me" : "" },
    el("th", { scope: "row" }, label, sub ? el("small", {}, sub) : ""),
    ...d.returns.map((r) => el("td", { class: `r ${cls(r[key])}` }, me ? el("b", {}, pct(r[key], 1, true)) : pct(r[key], 1, true))));
  const returns = el("div", { class: "table-wrap" }, el("table", { class: "returns-table" },
    el("thead", {}, el("tr", {}, el("th", {}, ""), ...d.returns.map((r) => el("th", { class: "r" }, short[r.period] || r.label, r.period === "ytd" ? learnLink("ytd") : "",
      r.period === "3y" || r.period === "5y" ? el("small", { style: { display: "block", fontWeight: 400 } }, "per year") : "")))),
    el("tbody", {},
      retRow(c.ticker, c.name, "stock", true),
      retRow("S&P 500", "SPY, the index fund", "spy"),
      d.sector?.etf ? retRow(c.sector, `${d.sector.etf}, the sector fund`, "sector") : "")));

  const fy = d.fundamentals.slice(0, 6).reverse();
  const rev = bars(fy.map((r) => ({ label: `'${String(r.fy_end).slice(2, 4)}`, value: r.revenue })), big);
  const ni = bars(fy.map((r) => ({ label: `'${String(r.fy_end).slice(2, 4)}`, value: r.net_income })), big);
  const fin = facts([
    ["Revenue", big(s.revenue_ttm), { note: ["last 12 months", learnLink("ttm")], term: "revenue" }],
    ["Revenue growth", pct(s.revenue_growth, 1, true), { note: "latest year vs the year before", term: "revenue", klass: cls(s.revenue_growth) }],
    ["Profit margin", pct(s.net_margin, 1), { term: "profit-margin" }],
    ["Operating margin", pct(s.op_margin, 1), { term: "operating-margin" }],
    ["Free cash flow", big(s.fcf_ttm), { note: "last 12 months", term: "free-cash-flow" }],
    ["Debt to equity", num(s.debt_to_equity, 2), { term: "debt-to-equity" }],
    ["P/E", num(s.pe, 1), { note: "price ÷ yearly earnings per share", term: "pe" }],
    ["Its usual P/E", num(s.pe_med5, 1), { note: "median over the past 5 years", term: "pe" }],
    ["Dividend yield", s.dividend_yield ? pct(s.dividend_yield, 2) : "none", { term: "dividend-yield" }],
    ["Years paying dividends", s.dividend_years ?? "—", { term: "dividend-yield" }],
    ["Profitable years", s.profitable_years != null ? `${s.profitable_years} of 5` : "—", { note: "net income above zero", term: "net-income" }],
  ], { columns: 2 });

  const months = (days) => Math.round((days || 0) / 30.4);
  const risk = facts([
    ["Biggest drop from a peak", pct(s.max_drawdown, 0), { term: "drawdown", klass: "down",
      note: s.dd_peak ? `${dateStr(s.dd_peak, { month: "short", year: "numeric" })} → ${dateStr(s.dd_trough, { month: "short", year: "numeric" })}` : "" }],
    ["Back to that peak", s.dd_recovered ? dateStr(s.dd_recovered, { month: "short", year: "numeric" }) : "not yet",
      { note: s.dd_recovered ? `${months(s.dd_days_to_recover)} months after the low` : "still below the old peak" }],
    ["Below its peak now", pct(s.current_drawdown, 0), { term: "drawdown" }],
    ["Volatility", pct(s.vol_1y, 0), { note: "yearly swings, past year", term: "volatility" }],
    ["Beta", num(s.beta_1y, 2), { note: "moves vs the S&P 500, past year", term: "beta" }],
  ]);

  const newsList = el("ul", { class: "news-list" }, ...(d.news.length ? d.news.map(newsItem) : [el("li", { class: "muted" }, "No headlines in the snapshot.")]));
  const loadNews = el("button", { class: "btn small", type: "button", onclick: async () => {
    loadNews.disabled = true; loadNews.textContent = "Loading…";
    try {
      const n = await api(`/api/stocks/${c.ticker}/live-news`);
      newsList.replaceChildren(...(n.articles.length ? n.articles.map(newsItem) : [el("li", { class: "muted" }, "No recent headlines found.")]));
      loadNews.textContent = `Latest from ${n.provider || "news"}`;
    } catch (e) { loadNews.textContent = e.message; }
  } }, "Load latest headlines");

  const moves = [...d.recent_moves.map((m) => el("li", {}, el("b", { class: cls(m.excess_1d) }, `${pct(m.excess_1d, 1, true)} vs the S&P 500`),
      ` on ${dateStr(m.date)}. `, m.n_with_outcome ? `One of ${m.n_similar} one-day ${m.kind}s this size since ${dateStr(s.history_start, { year: "numeric" })}; of the ${m.n_with_outcome} old enough to judge, it beat the index over the next year after ${m.n_beat_after}.` : "Too few past moves like this to say what usually follows.")),
    ...d.earnings.slice(0, 4).map((e) => el("li", {}, "Earnings release", learnLink("earnings-report"), " ", el("a", { href: e.url, target: "_blank", rel: "noopener" }, dateStr(e.date)),
      `: ${pct(e.reaction, 1, true)} vs the index over two days`, e.excess_next_3m != null ? `, ${pct(e.excess_next_3m, 1, true)} over the next 3 months.` : "."))];

  const asks = [`Walk me through ${c.ticker}'s trend and momentum over the past year: moving averages, RSI, and MACD.`,
    `What are the biggest risks in ${c.name}'s latest annual report?`,
    `Why has ${c.ticker} moved recently, and how unusual was that move for this stock?`];

  root.replaceChildren(
    el("a", { href: "#/screener", class: "back", html: `${BACK}<span>Screener</span>` }),
    el("div", { class: "stock-head", style: { marginTop: "10px" } },
      el("div", {}, el("div", { class: "title" }, el("h1", {}, c.ticker), el("span", { class: "muted", style: { fontSize: "19px" } }, c.name)),
        el("div", { class: "chips", style: { marginTop: "8px" } },
          el("a", { class: "badge", href: `#/screener?sector=${encodeURIComponent(c.sector)}`, title: `Every ${c.sector} company in the Screener`, style: { textDecoration: "none" } }, c.sector),
          el("span", { class: "badge" }, c.sub_industry),
          c.member_since ? el("span", { class: "badge" }, `In the S&P 500 since ${dateStr(c.member_since, { year: "numeric" })}`) : ""),
        c.sector_about ? el("p", { class: "sector-about", style: { margin: "8px 0 0", maxWidth: "52em" } }, el("b", {}, `${c.sector}: `), c.sector_about) : ""),
      el("div", { class: "px" }, el("b", {}, money(s.price)), el("div", { class: cls(s.change_1d) }, `${pct(s.change_1d, 2, true)} last day`),
        el("div", { class: "muted small" }, `as of ${dateStr(s.as_of)} · company value ${big(c.market_cap)}`, learnLink("market-cap")))),
    el("div", { class: "stock-layout" },
      el("div", {},
        el("div", { class: "card" },
          chart,
          el("div", { class: "grid g4 stats-row", style: { marginTop: "14px" } },
            stat("Past year", pct(s.ret_1y, 1, true), cls(s.ret_1y), `S&P 500 ${pct(s.spy_ret_1y, 1, true)}`),
            stat("5 yrs, per year", pct(s.ret_5y_ann, 1, true), cls(s.ret_5y_ann)),
            stat(["From 52-week high", learnLink("52-week-high")], pct(s.dist_52w_high, 1), cls(s.dist_52w_high)),
            stat(["RSI (14 day)", learnLink("rsi")], num(s.rsi14, 0), "", s.rsi14 > 70 ? "often called overbought" : s.rsi14 < 30 ? "often called oversold" : "neutral range"))),
        el("div", { class: "card" }, el("h2", {}, "Finances"), el("p", { class: "muted small", style: { margin: "4px 0 0" } },
            "From the company's SEC filings", learnLink("sec-filings"), ", by fiscal year", learnLink("fiscal-year"), "."),
          el("div", { class: "grid g2" }, el("div", {}, el("h3", { style: { marginTop: "12px" } }, "Revenue", learnLink("revenue")), rev),
            el("div", {}, el("h3", { style: { marginTop: "12px" } }, "Net income", learnLink("net-income")), ni)),
          el("div", { style: { marginTop: "14px" } }, fin)),
        el("div", { class: "card" }, el("h2", {}, "Returns"),
          el("p", { class: "muted small", style: { margin: "4px 0 10px" } }, `${c.ticker} next to the S&P 500 and its sector fund`, learnLink("sector-fund"), ". Dividends included", learnLink("total-return"),
            ". 3- and 5-year figures are per year", learnLink("annualized"), "."),
          returns),
        el("div", { class: "card" }, el("h2", {}, `Analyze ${c.ticker}`),
          el("p", { class: "muted small", style: { margin: "4px 0 12px" } }, "Open any analysis for this stock. You can change the period and settings there, and each one explains how to read it."),
          analyze),
        el("div", { class: "card" }, el("div", { class: "chart-controls" }, el("h2", {}, "Recent moves and news", learnLink("big-move")), loadNews),
          moves.length ? el("ul", { class: "news-list" }, ...moves) : "", newsList,
          el("p", { class: "small", style: { margin: "10px 0 0" } }, el("a", { href: "#/news" }, "See every recent big move on In the news")),
          d.filings.length ? el("details", { class: "method", style: { marginTop: "10px" } }, el("summary", {}, "Recent SEC filings", learnLink("sec-filings")),
            el("ul", { class: "news-list" }, ...d.filings.map((f) => el("li", {}, el("a", { href: f.url, target: "_blank", rel: "noopener" }, `${f.form} · ${dateStr(f.filed)}`),
              f.item_names ? el("small", {}, f.item_names) : "")))) : "")),
      el("aside", {},
        el("div", { class: "card" }, el("h3", {}, "Risk"),
          el("p", { class: "muted small", style: { margin: "4px 0 2px" } }, "Drops are measured over all the price history here."),
          risk,
          el("p", { class: "small", style: { margin: "10px 0 0" } }, "Explore: ", el("a", { href: `#/analyze?t=${c.ticker}&a=drawdown&p=max` }, "drawdowns"), " · ",
            el("a", { href: `#/analyze?t=${c.ticker}&a=volatility&p=1y` }, "volatility"), " · ", el("a", { href: `#/analyze?t=${c.ticker}&a=beta&p=3y` }, "beta"))),
        el("div", { class: "card" }, el("h3", {}, "Ask the research desk"),
          el("div", { class: "examples", style: { marginTop: "10px" } }, ...asks.map((q) => el("button", { type: "button", onclick: () => { location.hash = `#/research?q=${encodeURIComponent(q)}`; } }, q)))),
        d.peers.length ? el("div", { class: "card" }, el("h3", {}, `Largest others in ${c.sector}`),
          el("table", { style: { marginTop: "6px" } }, el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", { class: "r" }, "Value"), el("th", { class: "r" }, "1 year"))),
            el("tbody", {}, ...d.peers.map((p) => el("tr", { class: "link", onclick: () => { location.hash = `#/stock/${p.ticker}`; } },
            el("td", {}, el("a", { class: "tick", href: `#/stock/${p.ticker}` }, p.ticker)), el("td", { class: "r muted small" }, big(p.market_cap)),
            el("td", { class: `r ${cls(p.ret_1y)}` }, pct(p.ret_1y, 0, true))))))) : "",
        el("p", { class: "disclaimer" }, "Educational, not financial advice. Numbers describe the past. They don't predict future returns, and nothing here is a recommendation."))));
}

function stat(label, value, klass = "", sub = "") {
  return el("div", { class: "stat" }, el("span", {}, label), el("b", { class: klass }, value), sub ? el("small", {}, sub) : "");
}

function newsItem(n) {
  return el("li", {}, el("a", { href: n.url, target: "_blank", rel: "noopener" }, n.headline),
    el("small", {}, `${n.source || n.provider || ""} · ${dateStr(n.published)}`));
}
