// Learn: the big indexes, sectors, a glossary, how signals are tested, taxes and the one-year mark, the limits,
// and the data sources. Other pages link here with #/learn?term=<id> (a "?" next to a term) or ?section=<id>.
import { el, dateStr, num } from "../api.js";
import { yearRing } from "../components.js";
import { GLOSSARY, TERM_COUNT } from "../glossary.js";

export async function render(root, params, ctx) {
  const meta = ctx.meta || {};
  const cov = meta.coverage || {};
  const today = meta.as_of || new Date().toISOString().slice(0, 10);

  const info = meta.sector_info || {};
  const sections = [["indexes", "Market indexes"], ["sectors", "Sectors"], ["words", "Words you'll see"], ["method", "How signals are tested"],
    ["taxes", "Taxes and the one-year mark"], ["limits", "What the data can't tell you"], ["data", "Where the data comes from"]];
  const jump = el("div", { class: "chips", style: { marginBottom: "20px" } }, ...sections.map(([id, label]) =>
    el("button", { class: "chip", type: "button", onclick: () => document.getElementById(`learn-${id}`)?.scrollIntoView({ behavior: "smooth" }) }, label)));
  const head = (id, title, sub) => el("div", { class: "section-head", id: `learn-${id}`, style: { scrollMarginTop: "16px" } },
    el("div", {}, el("h2", {}, title), sub ? el("p", {}, sub) : ""));

  // The glossary, with a box that narrows it down as you type.
  const groups = GLOSSARY.map(([group, terms], i) => {
    const cards = terms.map(([id, t, d]) => {
      const card = el("div", { class: "card term", id: `term-${id}` }, el("h3", {}, t), el("p", {}, d));
      card.dataset.text = `${t} ${d}`.toLowerCase();
      return card;
    });
    return { head: el("h3", { class: "term-group", id: `term-group-${i}`, style: { scrollMarginTop: "16px" } }, group), box: el("div", { class: "terms" }, ...cards), cards };
  });
  const none = el("p", { class: "empty", hidden: true }, "No term matches that. Try a shorter word.");
  const find = el("input", { type: "search", class: "term-find", placeholder: "Find a term, like P/E or drawdown", "aria-label": "Find a term",
    oninput: () => {
      const q = find.value.trim().toLowerCase();
      let shown = 0;
      for (const g of groups) {
        let any = false;
        for (const c of g.cards) { const hit = !q || c.dataset.text.includes(q); c.hidden = !hit; any ||= hit; shown += hit ? 1 : 0; }
        g.head.hidden = !any; g.box.hidden = !any;
      }
      none.hidden = shown > 0;
    } });

  root.replaceChildren(
    el("div", { class: "section-head" }, el("div", {},
      el("h1", {}, "Learn the basics"),
      el("p", { class: "lede", style: { fontSize: "17px", maxWidth: "46em" } }, "The ideas behind every number in Ticker Tutor: how the market is organized, what the terms mean, how signals are tested, and what the data can't tell you."))),
    jump,

    head("indexes", "Market indexes", "An index tracks a slice of the market with one number. These four are the ones you'll hear about most. Ticker Tutor follows each through a large fund that tracks it, so returns include dividends."),
    el("div", { class: "grid g2", style: { marginBottom: "14px" } }, ...(meta.indexes || []).map(indexCard)),
    el("div", { class: "callout", style: { marginBottom: "26px" } },
      el("p", { style: { margin: 0 } }, el("b", {}, "Why fund prices? "), "An index is a list and a formula, so it can't be bought, and its quoted level ",
        "(the number on the news) leaves out dividends. Each fund's price is a fraction of its index's level, but their percentage moves nearly ",
        "match, minus a small yearly fee."),
      el("p", { style: { margin: "8px 0 0" } }, el("b", {}, "Other indexes you may hear about: "), "the Nasdaq Composite (every stock on the Nasdaq), ",
        "the S&P MidCap 400 (medium-sized companies), total-market indexes like the CRSP US Total Market and the Wilshire 5000, ",
        "and MSCI indexes for stocks outside the US.")),

    head("sectors", "Sectors", "S&P Dow Jones Indices and MSCI sort every company into one of 11 sectors under the Global Industry Classification Standard (GICS). Sectors often move differently, so comparing a stock with its sector helps separate company news from industry trends."),
    el("div", { class: "terms", style: { marginBottom: "26px" } }, ...Object.entries(info).map(([name, x]) =>
      el("a", { class: "card term", href: `#/screener?sector=${encodeURIComponent(name)}`, style: { textDecoration: "none", color: "inherit" } },
        el("h3", {}, name), el("p", {}, x.about), el("p", { class: "small", style: { marginTop: "6px" } }, el("b", {}, "For example: "), x.examples)))),

    head("words", "Words you'll see", `${TERM_COUNT} terms in plain language. A ? next to a word anywhere in Ticker Tutor opens its card here.`),
    el("div", { class: "term-tools" }, find, el("div", { class: "chips" }, ...GLOSSARY.map(([group], i) =>
      el("button", { class: "chip", type: "button", onclick: () => document.getElementById(`term-group-${i}`)?.scrollIntoView({ behavior: "smooth" }) }, group)))),
    none,
    ...groups.flatMap((g) => [g.head, g.box]),
    el("div", { style: { height: "26px" } }),

    head("method", "How Ticker Tutor tests whether a signal predicts anything", "Behind the \"What history shows\" panels on the Analyze tab. The same recipe for all 15 signals."),
    el("div", { class: "grid g2", style: { marginBottom: "18px" } },
      step(1, "Rebuild each month", `For every month from ${dateStr(cov.backtest_start, { month: "short", year: "numeric" })} on, take the companies that were in the S&P 500 at that time, not just today's members.`),
      step(2, "Only use what was known", "Compute each signal from prices up to that day and financial statements already filed with the SEC by then (by filing date, so no peeking at numbers that came out later)."),
      step(3, "Score the next year", "For each stock, measure its return over the following 12 months, dividends included, minus the S&P 500's return. Did it beat the index, and by how much?"),
      step(4, "Compare with vs without", "Each month, compare stocks with the signal on against those with it off. Then average across all months, so calm and crazy years each count once."),
      step(5, "Measure the uncertainty", "One-year windows that start a month apart overlap, so months aren't independent. We resample whole 12-month blocks 2,000 times (a block bootstrap) to get an honest 95% range."),
      step(6, "Hold some back", "The most recent third of months is set aside. A signal only gets \"held up\" if the edge is clearly positive overall and still positive in that held-back stretch.")),
    el("div", { class: "card", style: { marginBottom: "26px" } },
      el("h3", {}, "What the verdicts mean"),
      el("dl", { class: "kv", style: { gridTemplateColumns: "auto 1fr", marginTop: "8px" } },
        ...[["Held up", "The 95% range for the extra return is above zero and the recent held-back years agree."],
          ["Mixed", "It looked good overall but faded or flipped in the recent years."],
          ["No clear edge", "The range includes zero, or the gap is under 1 point a year. Can't tell it from luck."],
          ["Did worse", "Stocks with the signal clearly lagged."],
          ["Too little data", "Fewer than 24 months with enough stocks on both sides to compare."]].flatMap(([k, v]) => [el("dt", { style: { fontWeight: 700, color: "var(--ink)" } }, k), el("dd", { style: { textAlign: "left", fontFamily: "inherit", fontWeight: 400 } }, v)]))),

    head("taxes", "Taxes and the one-year mark", "One practical detail worth knowing before you ever sell a stock."),
    el("div", { class: "card tax-card", style: { marginBottom: "26px" } },
      el("div", {},
        el("p", { style: { marginTop: 0 } }, "In the US, when you sell a stock for a profit in a regular (taxable) brokerage account, the tax depends on how long you held it."),
        el("ul", {},
          el("li", {}, el("b", {}, "One year or less: "), "a short-term gain, taxed like ordinary income (up to 37% federally)."),
          el("li", {}, el("b", {}, "More than one year: "), "a long-term gain, taxed at 0%, 15%, or 20% federally for most people, depending on income.")),
        el("p", {}, "Example: on a $1,000 gain, someone in the 22% bracket would owe about $220 selling at 11 months, and about $150 selling after a year."),
        el("p", {}, "\"More than one year\" means selling on or after the day after your purchase anniversary: buy on March 3, 2026, and the first long-term day is March 4, 2027."),
        el("p", { class: "small muted", style: { marginBottom: 0 } }, "Retirement accounts like IRAs and 401(k)s work differently. State taxes vary. This is general education, not tax advice. See IRS Publication 550 or a tax professional.")),
      el("div", { class: "ring-demo" }, el("h3", {}, "Date calculator"), el("p", { class: "small muted", style: { margin: 0 } }, "Pick a purchase date."), yearRing(today, today))),

    head("limits", "What the data can't tell you"),
    el("div", { class: "grid", style: { gap: "10px", marginBottom: "26px" } },
      limit("The future", "Every number here describes the past. Markets change, and a pattern that worked can stop working, especially once everyone knows about it. Nobody, including this app, can tell you what a stock will do next year."),
      limit("Companies that disappeared", `We include ${cov.former_members ?? "some"} former S&P 500 members where price data exists, but companies that went bankrupt or were bought out are often missing from free data sources. Results can look a bit better than reality (survivorship bias).`),
      limit("Financial data before 2009", "Company financials come from the SEC's machine-readable XBRL filings, which start around 2009–2011. Some companies label items differently, so a few figures show as unknown rather than guessed."),
      limit("Testing many ideas", "With 15 signals, one could look good by chance. Holding back recent years and showing ranges, not just averages, guards against fooling ourselves, but doesn't eliminate it."),
      limit("Costs, taxes, and your situation", "Analyses and track records ignore taxes, trading costs, and whether a stock fits your goals, timeline, and other holdings. Those matter more than any signal."),
      limit("Your chosen dates", "Most analyses change, sometimes a lot, with the start and end dates. Try several periods before drawing a conclusion, and be wary of any chart that only looks convincing for one window."),
      limit("News", "Headlines explain why something moved. Ticker Tutor doesn't score news as good or bad, and the base rates show big moves are usually not reliable predictors of the next year.")),

    head("data", "Where the data comes from", meta.synthetic ? "This deployment is running on simulated demo data. A real build pulls from:" : `Prices as of ${dateStr(meta.as_of)}, built ${dateStr(meta.built_at)}. Prices are daily closes, updated after each trading day. Company financials and index membership are refreshed about once a week.`),
    el("div", { class: "card", style: { marginBottom: "26px" } }, el("ul", { class: "news-list" },
      src("S&P 500 members and changes", "Wikipedia's list of S&P 500 companies, including the table of additions and removals, used to rebuild who was in the index each month.", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
      src(`Daily prices (${meta.provider || "Alpaca, Tiingo, or Stooq"})`, "Split- and dividend-adjusted closing prices for every member, the four index funds (SPY, QQQ, DIA, IWM), and the 11 SPDR sector funds.", meta.provider === "tiingo" ? "https://www.tiingo.com/" : meta.provider === "stooq" ? "https://stooq.com/" : "https://alpaca.markets/"),
      src("Company financials and filings", "SEC EDGAR: XBRL company facts (revenue, profit, debt, dividends), the filing index (10-K, 10-Q, 8-K), and the text of annual reports for risk factors.", "https://www.sec.gov/edgar/sec-api-documentation"),
      src("News", "Finnhub company and market news, with GDELT as a backup.", "https://finnhub.io/docs/api/company-news"),
      src("Market context", "FRED (Federal Reserve Bank of St. Louis): the VIX and the 10-year Treasury yield.", "https://fred.stlouisfed.org/"),
      cov.current_members ? el("li", { class: "small muted" }, `Coverage: ${cov.with_prices}/${cov.current_members} current members with prices, ${cov.with_fundamentals} with financials, ${num(cov.evaluable_rows, 0)} stock-months with a full year of outcomes for backtesting.`) : "")),

    el("div", { class: "callout" }, el("h3", {}, "The fine print"),
      el("p", { style: { margin: "6px 0 0" } }, "Ticker Tutor is an educational project. It is not a registered investment adviser and nothing here is a recommendation to buy or sell any security. ",
        "Any stock, even a large, well-known one, can lose a lot of value, and past results don't guarantee future returns. Consider talking to a licensed professional before investing money you can't afford to lose.")));

  // Arriving from a "?" link: bring that card into view and highlight it for a moment.
  const target = params.term ? document.getElementById(`term-${params.term}`)
    : params.section ? document.getElementById(`learn-${params.section}`) : null;
  if (target && !ctx.restored) {   // coming back to this tab keeps your place instead
    setTimeout(() => {
      target.scrollIntoView({ block: params.term ? "center" : "start" });
      if (params.term) {
        target.classList.add("flash");
        setTimeout(() => target.classList.remove("flash"), 2600);
      }
    }, 30);
  }
}

function indexCard(x) {
  return el("div", { class: "card term index-learn", id: `term-${x.id}` },
    el("div", { class: "ic-head" }, el("h3", { style: { margin: 0 } }, x.name), el("span", { class: "ic-tick" }, x.ticker)),
    el("p", { style: { marginTop: "6px" } }, x.about),
    el("p", { class: "ix-facts" }, el("span", {}, "Started ", el("b", {}, x.started)), el("span", {}, el("b", {}, x.members), " companies"),
      el("span", {}, "Weighted ", el("b", {}, x.weighting.charAt(0).toLowerCase() + x.weighting.slice(1)))),
    el("p", { class: "watch" }, el("b", {}, "Keep in mind: "), x.watch),
    el("div", { class: "actions" }, x.available
      ? [el("a", { href: `#/index/${x.ticker}` }, `Open the ${x.label} page`),
        el("a", { href: `#/analyze?t=${x.ticker}&a=relative&p=1y` }, "Compare it with the others")]
      : el("span", { class: "muted small" }, `Fund: ${x.fund}. Rerun the data build to add its prices.`)));
}

function step(n, title, text) {
  return el("div", { class: "card", style: { display: "grid", gridTemplateColumns: "34px 1fr", gap: "10px" } },
    el("span", { class: "stepnum" }, String(n)), el("div", {}, el("h3", {}, title), el("p", { class: "muted", style: { margin: "4px 0 0", fontSize: "15px" } }, text)));
}
function limit(title, text) {
  return el("details", { class: "method" }, el("summary", {}, title), el("p", {}, text));
}
function src(title, text, url) {
  return el("li", {}, el("a", { href: url, target: "_blank", rel: "noopener" }, title), el("small", {}, text));
}
