// Home: what Ticker Tutor is, in one screen. A real chart with a tutor's notes on it, a search box, and three steps.
import { api, el, svgEl, pct, dateStr } from "../api.js";
import { picker, pageHref } from "../components.js";
import { TERM_COUNT } from "../glossary.js";

let played = false;   // the chart draws itself once per visit, not on every return to the home page

export async function render(root, params, ctx) {
  const [tk, px, cat] = await Promise.all([api("/api/tickers"),
    api("/api/stocks/SPY/prices?range=1y").catch(() => ({ points: [] })), api("/api/analyses")]);
  const tickers = tk.tickers;
  const search = picker(tickers, { id: "home-options", placeholder: "Search a company or index",
    onPick: (r) => { location.hash = pageHref(r); } });
  const tries = ["AAPL", "KO", "NVDA", "SPY"].map((t) => tickers.find((r) => r.ticker === t)).filter(Boolean);
  const short = (r) => (r.kind === "index" ? r.name : r.name.replace(/^The /, "").replace(/,? (Inc\.?|Corporation|Company|Corp\.?)$/i, ""));

  const chartBox = el("div", { class: "marked-plot" });
  const points = px.points || [];
  let drawn = 0;
  const draw = () => { drawn = chartBox.clientWidth; chartBox.replaceChildren(...markedChart(points, drawn, !played)); played = true; };
  if (points.length > 30) {
    new ResizeObserver(() => { if (Math.abs(chartBox.clientWidth - drawn) > 24) draw(); }).observe(chartBox);
  }

  root.replaceChildren(
    el("section", { class: "home-hero" },
      el("div", { class: "home-pitch" },
        el("h1", {}, "Learn to read the stock market, one chart at a time."),
        el("p", { class: "lede" }, "Ticker Tutor is a practice space for curious beginners. Look up any S&P 500 company or market index, "
          + "run the analyses investors use most, and read in plain English what every number means."),
        el("div", { class: "home-search" }, search,
          el("button", { class: "btn primary", type: "button", onclick: () => search.submit() }, "Explore")),
        tries.length ? el("div", { class: "home-tries" }, el("span", {}, "Or start with"),
          ...tries.map((r) => el("a", { class: "chip", href: pageHref(r) }, short(r)))) : ""),
      points.length > 30 ? el("figure", { class: "marked" },
        el("figcaption", {}, el("b", {}, "The S&P 500 over the past year"),
          el("span", {}, `through ${dateStr(points[points.length - 1].date)}`)),
        chartBox,
        el("p", { class: "marked-foot" }, "This is what every chart here looks like: the numbers, with notes on how to read them. Click a note to open that analysis.")) : ""),

    el("section", { class: "section" },
      el("div", { class: "section-head" }, el("h2", {}, "How it works"), el("a", { href: "#/guide" }, "See the full walkthrough")),
      el("ol", { class: "steps3" },
        step(1, "Pick a company or index", "Search by name, or browse the Screener: the big indexes up top, then every S&P 500 company grouped by sector.",
          "#/screener", "Open the Screener"),
        step(2, "Run an analysis", `Choose from ${cat.analyses.length} common ones, like moving averages, RSI, volatility, and drawdowns, over any time period you like.`,
          "#/analyze", "Open Analyze"),
        step(3, "Read what it means", "Every chart explains what the number is, how it's calculated, how to read it, and what to watch out for.",
          "#/learn", "Browse the glossary"))),

    el("section", { class: "section" },
      el("div", { class: "section-head" }, el("h2", {}, "Also inside")),
      el("div", { class: "doors" },
        door("#/news", "In the news", "What moved lately, the headlines behind it, and what has usually followed moves like it."),
        door("#/research", "Research desk", "Ask a bigger question and watch a team of AI agents research it, with every number cited."),
        door("#/learn", "Learn", `The big indexes, the 11 sectors, and ${TERM_COUNT} terms explained without jargon.`))));
  if (points.length > 30) draw();
}

function step(n, title, text, href, link) {
  return el("li", {}, el("span", { class: "n", "aria-hidden": "true" }, String(n)), el("h3", {}, title), el("p", {}, text), el("a", { href }, link));
}

function door(href, title, text) {
  return el("a", { class: "door", href }, el("b", {}, title), el("span", {}, text));
}

// A curved pen stroke from (x1, y1) to (x2, y2) with a small arrowhead at the end.
function arrow(x1, y1, x2, y2, bend = 0.22) {
  const mx = (x1 + x2) / 2 - (y2 - y1) * bend, my = (y1 + y2) / 2 + (x2 - x1) * bend;
  const a = Math.atan2(y2 - my, x2 - mx), h = 8;
  const head = [a + 2.6, a - 2.6].map((t) => `M${x2.toFixed(1)},${y2.toFixed(1)}l${(Math.cos(t) * h).toFixed(1)},${(Math.sin(t) * h).toFixed(1)}`).join("");
  return `M${x1.toFixed(1)},${y1.toFixed(1)}Q${mx.toFixed(1)},${my.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}${head}`;
}

// One year of the S&P 500 fund with three handwritten notes: the 50-day average, the biggest dip, and the year's return.
function markedChart(points, width, animate) {
  const W = Math.max(280, Math.round(width)), narrow = W < 430;
  const H = narrow ? 330 : 380, M = { l: 10, r: 26, t: narrow ? 70 : 84, b: 88 };
  const n = points.length;
  const vals = points.flatMap((p) => [p.adj_close, p.sma50]).filter((v) => v != null);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const X = (i) => M.l + (i / (n - 1)) * (W - M.l - M.r);
  const Y = (v) => M.t + (1 - (v - lo) / (hi - lo || 1)) * (H - M.t - M.b);
  const path = (key) => points.reduce((d, p, i) => (p[key] == null ? d : `${d}${d ? "L" : "M"}${X(i).toFixed(1)},${Y(p[key]).toFixed(1)}`), "");

  // The biggest fall from a high inside this year.
  let peak = -Infinity, dip = 0, dipAt = 0;
  points.forEach((p, i) => { peak = Math.max(peak, p.adj_close); const d = p.adj_close / peak - 1; if (d < dip) { dip = d; dipAt = i; } });
  const total = points[n - 1].adj_close / points[0].adj_close - 1;
  // Point at the average where it sits furthest above the price, so the arrow reaches it without crossing the price line.
  let avgAt = Math.round(n * 0.24), gap = -Infinity;
  for (let i = Math.round(n * 0.12); i < Math.round(n * 0.5); i++) {
    const g = points[i].sma50 != null ? points[i].sma50 - points[i].adj_close : -Infinity;
    if (g > gap) { gap = g; avgAt = i; }
  }
  const hasAvg = points[avgAt].sma50 != null;

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
    "aria-label": `The S&P 500 fund over the past year: ${pct(total, 1, true)} with dividends, with a biggest dip of ${pct(dip, 1)}.` });
  if (hasAvg) svg.append(svgEl("path", { class: "avg", d: path("sma50"), pathLength: 1 }));
  svg.append(svgEl("path", { class: "line", d: path("adj_close"), pathLength: 1 }),
    svgEl("circle", { class: "end", cx: X(n - 1), cy: Y(points[n - 1].adj_close), r: 5 }),
    svgEl("text", { class: "when", x: M.l, y: H - 8 }, dateStr(points[0].date, { month: "short", year: "numeric" })),
    svgEl("text", { class: "when", x: W - M.r, y: H - 8, "text-anchor": "end" }, dateStr(points[n - 1].date, { month: "short", year: "numeric" })));

  const notes = [];
  const note = (cls, href, text, style, d, extra) => {
    svg.append(svgEl("path", { class: `pen ${cls}`, d }));
    if (extra) svg.append(extra);
    notes.push(el("a", { class: `note ${cls}`, href, style }, text));
  };
  // Top right: the year's return, pointing at the last price.
  const ex = X(n - 1), ey = Y(points[n - 1].adj_close);
  note("n3", "#/index/SPY", `${pct(total, 1, true)} over the year, dividends included`,
    { right: `${M.r + 26}px`, top: "6px", textAlign: "right", maxWidth: narrow ? "150px" : "200px" },
    arrow(W - M.r - 18, narrow ? 52 : 40, ex + 1, ey - 12, -0.3));
  // Top left: the moving average.
  if (hasAvg && !narrow) {
    const ax = X(avgAt), ay = Y(points[avgAt].sma50);
    // The note sits above the spot it points at (as far as the other note leaves room), so the arrow drops straight down.
    const nw = 210, left = Math.max(M.l + 4, Math.min(ax - nw / 2, W - M.r - 242 - nw));
    const fromX = Math.max(left + 24, Math.min(ax - 8, left + nw - 24));
    note("n1", "#/analyze?t=SPY&a=moving_averages&p=1y", "the 50-day average smooths out the daily noise",
      { left: `${left}px`, top: "6px", width: `${nw}px` }, arrow(fromX, 78, ax, ay - 8, 0.12));
  }
  // Bottom: the biggest dip, circled.
  if (dip < -0.01) {
    const dx = X(dipAt), dy = Y(points[dipAt].adj_close);
    const boxW = narrow ? 170 : 220, left = Math.max(M.l + 4, Math.min(dx - boxW / 2 + 40, W - M.r - boxW));
    const fromX = Math.max(left + 24, Math.min(dx + 34, left + boxW - 24));
    const circle = svgEl("path", { class: "pen n2 loop",
      d: `M${dx - 15},${dy + 2}c-2,-15 26,-19 30,-3c3,14 -24,21 -31,6c-2,-5 2,-12 8,-14` });
    note("n2", "#/analyze?t=SPY&a=drawdown&p=1y", `biggest dip of the year: ${pct(dip, 1)}`,
      { left: `${left}px`, top: `${H - 64}px`, width: `${boxW}px` }, arrow(fromX, H - 66, dx + 6, dy + 20, 0.18), circle);
  }
  const wrap = el("div", { class: `marked-inner${animate ? " animate" : ""}`, style: { height: `${H}px` } }, svg, ...notes);
  return [wrap];
}
