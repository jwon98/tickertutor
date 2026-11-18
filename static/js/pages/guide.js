// How it works: a five-step walkthrough of Ticker Tutor, with a place to start at each step.
import { api, el } from "../api.js";
import { picker, pageHref } from "../components.js";
import { learnLink } from "../glossary.js";

export async function render(root, params, ctx) {
  const [data, cat, tk] = await Promise.all([api("/api/overview"), api("/api/analyses"), api("/api/tickers")]);
  const search = picker(tk.tickers, { id: "guide-options", placeholder: "Try Apple, KO, or Nasdaq",
    onPick: (r) => { location.hash = pageHref(r); } });
  const groups = cat.groups.map((g) => [g, cat.analyses.filter((a) => a.group === g)]).filter(([, items]) => items.length);

  root.replaceChildren(
    el("div", { class: "section-head" }, el("div", {}, el("h1", {}, "How it works"),
      el("p", { class: "lede", style: { fontSize: "17px", maxWidth: "44em" } },
        "Five steps take you from a company name to understanding a chart. Each one has a place to start."))),

    el("ol", { class: "walk" },
      stage(1, "Find a company or index",
        [`Ticker Tutor covers the ${data.n} companies in the S&P 500 and four big market indexes. Search for one here, or browse the Screener, `
          + "where companies are grouped by sector and sized by how much they're worth."],
        el("div", { class: "walk-try" }, search, el("a", { class: "btn", href: "#/screener" }, "Browse the Screener"))),
      stage(2, "Look around its page",
        ["Every company has a page with its price chart, its finances from SEC filings, its returns next to the S&P 500 and its sector, how rough "
          + "the ride has been, and recent news. The chart starts on this year so far. Switch it from one month to all of its history, or add the "
          + "50-day and 200-day averages."],
        el("div", { class: "chips" }, ...data.examples.slice(0, 4).map((x) => el("a", { class: "chip", href: `#/stock/${x.ticker}` }, `${x.ticker} · ${x.name}`))),
        el("p", { class: "qtip" }, el("b", {}, "Not sure what a word means? "), "Look for the small question mark next to it, like this one for P/E",
          learnLink("pe"), ". Click it and the Learn tab opens on that exact term. Every tab keeps your place, so clicking back takes you to the page you left.")),
      stage(3, "Run an analysis",
        [`The Analyze tab has ${cat.analyses.length} of the analyses people use most. Pick a stock or index, then an analysis, choose any time `
          + "period, and adjust the settings if you're curious what changes."],
        el("div", { class: "try-grid" }, ...data.examples.map((x) =>
          el("a", { href: `#/analyze?t=${x.ticker}&a=${x.analysis}&p=1y` }, el("small", {}, x.label), el("b", {}, x.ticker), el("span", {}, x.name)))),
        el("p", { class: "fine-note" }, "Examples are the largest companies in a few sectors, not suggestions.")),
      stage(4, "Read what it means",
        ["Under every chart there are four short notes: what the statistic is, how it's calculated, how to read it, and what to watch out for. "
          + "For well-known signals like the golden cross, you can also see how often they've actually worked across S&P 500 stocks."],
        el("div", { class: "chips" }, el("a", { class: "chip", href: "#/learn?section=words" }, "Open the glossary"),
          el("a", { class: "chip", href: "#/learn?section=method" }, "How signals are tested"))),
      stage(5, "Ask a bigger question",
        ["On the Research desk, a team of AI agents looks through prices, SEC filings, and news at the same time, then writes a short answer "
          + "that cites every number. Ask it things like \"why is Nvidia down so much?\" and it pairs the headlines with how big and how unusual "
          + "the move was. It explains what the data shows and never tells you what to buy."],
        el("div", { class: "chips" }, el("a", { class: "chip", href: "#/research" }, "Open the Research desk"),
          el("a", { class: "chip", href: "#/news" }, "See what moved lately")))),

    el("section", { class: "section" },
      el("div", { class: "section-head" }, el("div", {}, el("h2", {}, "What you can analyze"),
        el("p", {}, "Each one opens on the Analyze tab, where you can change the stock, the period, and the settings."))),
      el("div", { class: "grid g3" }, ...groups.map(([g, items]) => el("div", { class: "card" },
        el("h3", {}, g),
        el("ul", { class: "plain-list" }, ...items.map((a) => el("li", {},
          el("a", { href: `#/analyze?a=${a.id}` }, a.name), el("div", { class: "small muted" }, a.short)))))))),

    el("section", { class: "section" },
      el("div", { class: "section-head" }, el("h2", {}, "Good to know")),
      el("div", { class: "grid g3 know" },
        el("div", {}, el("h3", {}, "It teaches, it doesn't advise"),
          el("p", {}, "Everything here describes what has happened and how to measure it. Nothing is a recommendation, and past results don't guarantee future ones.")),
        el("div", {}, el("h3", {}, "Returns include dividends"),
          el("p", {}, "Prices are adjusted for splits and dividends, so a stock's return here can be a little higher than its price change alone.")),
        el("div", {}, el("h3", {}, "The data has limits"),
          el("p", {}, "Prices are daily closes, updated after each trading day, not live quotes. Only current S&P 500 members have pages. ",
            el("a", { href: "#/learn?section=limits" }, "What the data can't tell you"))))));
}

function stage(n, title, text, ...actions) {
  return el("li", {}, el("span", { class: "n", "aria-hidden": "true" }, String(n)),
    el("div", {}, el("h2", {}, title), el("p", {}, ...text), ...actions));
}
