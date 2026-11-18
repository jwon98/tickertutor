// Reusable pieces: the evidence meter, the one-year date helper, charts, index cards, fact lists,
// a sector treemap, and a small safe markdown renderer for research reports.
import { api, el, svgEl, pct, pts, num, cls, dateStr, VERDICT_LABEL } from "./api.js";
import { learnLink } from "./glossary.js";

// A tiny line chart with no axes, colored by whether it ended higher than it started.
export function sparkline(values, w = 120, h = 34) {
  const v = (values || []).filter((x) => Number.isFinite(x));
  if (v.length < 2) return el("span");
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const pts_ = v.map((x, i) => `${(i / (v.length - 1)) * (w - 2) + 1},${h - 2 - ((x - lo) / span) * (h - 4)}`).join(" ");
  const up = v[v.length - 1] >= v[0];
  return svgEl("svg", { class: "spark", viewBox: `0 0 ${w} ${h}`, width: w, height: h, preserveAspectRatio: "none", "aria-hidden": "true" },
    svgEl("polyline", { points: pts_, fill: "none", stroke: up ? "var(--up)" : "var(--down)", "stroke-width": 1.6,
      "stroke-linejoin": "round", "stroke-linecap": "round", "vector-effect": "non-scaling-stroke" }));
}

// A search box for companies and indexes with a keyboard-friendly list of matches.
// tickers: [{ticker, name, sector, kind}]. opts.onPick(row) runs when one is chosen. opts.current (a ticker)
// makes the box show the current choice when idle, as on the Analyze tab; without it the box starts empty.
export function picker(tickers, opts = {}) {
  let cur = opts.current || null, options = [], active = -1;
  const listId = opts.id || "picker-options";
  const text = (t) => { const r = tickers.find((x) => x.ticker === t); return r ? `${r.ticker} · ${r.name}` : t || ""; };
  const input = el("input", { type: "search", class: "stock-input", placeholder: opts.placeholder || "Search a company, ticker, or index",
    autocomplete: "off", "aria-label": opts.label || "Company or index", role: "combobox", "aria-expanded": "false", "aria-controls": listId });
  const list = el("ul", { class: "stock-options", id: listId, role: "listbox", hidden: true });
  input.value = text(cur);
  function matches(q) {
    q = q.trim().toLowerCase();
    if (!q) return tickers.slice(0, 8);
    const starts = tickers.filter((r) => r.ticker.toLowerCase().startsWith(q));
    const names = tickers.filter((r) => !starts.includes(r) && r.name.toLowerCase().includes(q));
    return [...starts, ...names].slice(0, 8);
  }
  function show() {
    options = matches(input.value.includes(" · ") ? "" : input.value);
    active = options.length ? 0 : -1;
    list.replaceChildren(...(options.length ? options.map((r, i) => el("li", { role: "option", "aria-selected": String(i === active),
      onmousedown: (e) => { e.preventDefault(); choose(r); } }, el("b", {}, r.ticker), ` ${r.name}`, el("small", {}, r.sector)))
      : [el("li", { class: "none" }, "No match. Ticker Tutor covers current S&P 500 members and four big indexes.")]));
    list.hidden = false; input.setAttribute("aria-expanded", "true");
  }
  function hide() { list.hidden = true; input.setAttribute("aria-expanded", "false"); }
  function choose(r) {
    if (opts.current) { cur = r.ticker; input.value = text(cur); }
    hide(); input.blur();
    opts.onPick?.(r);
  }
  input.addEventListener("focus", () => { input.select(); show(); });
  input.addEventListener("input", show);
  input.addEventListener("blur", () => { setTimeout(hide, 120); if (opts.current) input.value = text(cur); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + options.length) % Math.max(1, options.length);
      [...list.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === active)));
    } else if (e.key === "Enter" && options[active]) { e.preventDefault(); choose(options[active]); }
    else if (e.key === "Escape") { hide(); input.blur(); }
  });
  const box = el("div", { class: "stock-search" }, input, list);
  box.input = input;
  // Pick the best match for whatever is typed (for a button next to the box). Focuses the box if nothing matches.
  box.submit = () => { const m = input.value.trim() ? matches(input.value.includes(" · ") ? input.value.split(" · ")[0] : input.value) : [];
    if (m.length) choose(m[0]); else input.focus(); };
  return box;
}

// Where a company or index lives: companies have a stock page, indexes an index page (both under the Screener).
export const pageHref = (r) => (r.kind === "index" ? `#/index/${r.ticker}` : `#/stock/${r.ticker}`);

// The big indexes as a row of cards: past-year return with a sparkline, and shorter periods underneath.
// Clicking a card opens that index's page; the "?" opens its Learn card.
export function indexCards(list) {
  const mini = (label, v) => el("span", {}, el("small", {}, label), el("b", { class: cls(v) }, pct(v, 1, true)));
  return el("div", { class: "index-strip" }, ...(list || []).map((x) => {
    const href = `#/index/${x.ticker}`;
    const head = el("div", { class: "ic-head" }, el("b", { title: x.name }, x.label || x.name), learnLink(x.id), el("span", { class: "ic-tick" }, x.ticker));
    if (!x.available) {
      return el("div", { class: "card index-card off" }, head, el("p", { class: "small muted", style: { margin: "6px 0 0" } },
        `No prices for ${x.ticker} yet. Rerun the data build to add this index.`));
    }
    return el("div", { class: "card index-card", role: "link", tabindex: "0", "aria-label": `Open the ${x.name} page`,
      onclick: () => { location.hash = href; }, onkeydown: (e) => { if (e.key === "Enter") location.hash = href; } },
      head,
      el("div", { class: "ic-sub" }, x.short),
      el("div", { class: "ic-main" }, el("div", {}, el("b", { class: `ic-ret ${cls(x.ret_1y)}` }, pct(x.ret_1y, 1, true)),
        el("small", {}, "past year")), sparkline(x.spark)),
      el("div", { class: "ic-row" }, mini("1 day", x.change_1d), mini("1 month", x.ret_1m), mini("This year", x.ret_ytd)));
  }));
}

// Label/value rows with a divider between them. Each row: [label, value, { note, term, klass }].
// `term` adds a "?" link to that term's Learn card.
export function facts(rows, opts = {}) {
  return el("dl", { class: `factlist${opts.columns === 2 ? " two" : ""}` }, ...rows.filter(Boolean).map(([label, value, o = {}]) =>
    el("div", { class: "fact" },
      el("dt", {}, el("span", {}, label, o.term ? learnLink(o.term) : ""), o.note ? el("small", {}, o.note) : ""),
      el("dd", { class: o.klass || "" }, value))));
}

export function verdict(v) {
  return el("span", { class: `verdict v-${v || "too_little_data"}` }, VERDICT_LABEL[v] || "Too little data");
}

// How often stocks beat the S&P 500 over the next year: with the signal (filled dot,
// with its 95% range) vs without (hollow dot). The dashed line is a coin flip.
export function meter(card) {
  const lo = 0.3, hi = 0.8;
  const x = (v) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))}%`;
  const wrap = el("div", { class: "meter-wrap" });
  if (!card || card.hit_on == null || card.verdict === "too_little_data") {
    wrap.append(el("p", { class: "muted small" }, "Not enough history to measure this one."));
    return wrap;
  }
  const m = el("div", { class: "meter", role: "img",
    "aria-label": `With the signal, ${pct(card.hit_on, 0)} of stocks beat the S&P 500 over the next year. Without it, ${pct(card.hit_off, 0)}.` },
    el("div", { class: "track" }), el("div", { class: "coin", style: { left: x(0.5) }, title: "50%: a coin flip" }));
  if (card.hit_diff_lo != null && card.hit_diff_hi != null) {
    // Center the band on the filled dot: it's the range for "with the signal", given the gap's uncertainty.
    const base = card.hit_on - (card.hit_diff ?? card.hit_on - card.hit_off);
    const a = base + card.hit_diff_lo, b = base + card.hit_diff_hi;
    m.append(el("div", { class: "ci", style: { left: x(a), width: `calc(${x(b)} - ${x(a)})` }, title: "95% range" }));
  }
  m.append(el("div", { class: "dot off", style: { left: x(card.hit_off) }, title: `Without the signal: ${pct(card.hit_off, 0)}` }));
  m.append(el("div", { class: "dot on", style: { left: x(card.hit_on) }, title: `With the signal: ${pct(card.hit_on, 0)}` }));
  wrap.append(m, el("div", { class: "meter-scale" }, el("span", {}, "30%"), el("span", {}, "coin flip 50%"), el("span", {}, "80%")));
  return wrap;
}

export function signalCard(card, opts = {}) {
  const c = el("article", { class: "card signal-card" });
  c.append(el("div", { class: "family" }, card.family || ""), el("h3", {}, card.label));
  if (!opts.compact) c.append(el("p", { class: "desc" }, card.description));
  c.append(verdict(card.verdict), meter(card));
  if (card.hit_on != null) {
    c.append(el("div", { class: "numbers" },
      el("span", {}, "With it: ", el("b", {}, pct(card.hit_on, 0)), " beat the index"),
      el("span", {}, "Without: ", el("b", {}, pct(card.hit_off, 0))),
      el("span", {}, "Extra return: ", el("b", {}, pts(card.diff)), ` (95% range ${pts(card.diff_lo)} to ${pts(card.diff_hi)})`)));
    if (!opts.compact) {
      c.append(el("div", { class: "numbers" },
        el("span", {}, "Recent held-out years: ", el("b", {}, pts(card.oos_diff))),
        el("span", {}, `${card.n_months} months, ${dateStr(card.period_start, { year: "numeric", month: "short" })}–${dateStr(card.period_end, { year: "numeric", month: "short" })}`)));
    }
  }
  return c;
}

// --- the one-year ring --------------------------------------------------------------------------------
export function longTermDate(purchase) {
  const p = new Date(purchase + "T12:00:00");
  const a = new Date(p);
  a.setFullYear(p.getFullYear() + 1);
  if (a.getMonth() !== p.getMonth()) a.setDate(0); // Feb 29 → Feb 28
  a.setDate(a.getDate() + 1);
  return a;
}

export function yearRing(purchaseIso, todayIso) {
  const box = el("div", { class: "ring-box" });
  const input = el("input", { type: "date", value: purchaseIso, max: todayIso, "aria-label": "Purchase date" });
  const ring = el("div", { class: "ring" });
  const info = el("p", { class: "small muted", style: { margin: "6px 0 0" } });
  function draw() {
    const buy = input.value || todayIso;
    const lt = longTermDate(buy);
    const today = new Date(todayIso + "T12:00:00");
    const total = Math.round((lt - new Date(buy + "T12:00:00")) / 864e5);
    const held = Math.max(0, Math.round((today - new Date(buy + "T12:00:00")) / 864e5));
    const left = Math.max(0, total - held);
    const r = 60, C = 2 * Math.PI * r, frac = Math.min(1, held / total);
    ring.replaceChildren(
      svgEl("svg", { viewBox: "0 0 148 148" },
        svgEl("circle", { cx: 74, cy: 74, r, fill: "none", stroke: "#e9eef4", "stroke-width": 14 }),
        svgEl("circle", { cx: 74, cy: 74, r, fill: "none", stroke: "#e8a317", "stroke-width": 14, "stroke-linecap": "round",
          "stroke-dasharray": `${Math.max(0.001, frac) * C} ${C}` })),
      el("div", { class: "lbl" }, el("b", {}, left ? `${left}` : "✓"), el("span", {}, left ? "days to long-term" : "long-term")));
    info.replaceChildren(left
      ? `Sold on or after ${dateStr(lt.toISOString().slice(0, 10))}, gains count as long-term (in a taxable US account).`
      : `Held more than a year: gains count as long-term (in a taxable US account).`);
  }
  input.addEventListener("change", draw);
  draw();
  box.append(el("label", { class: "small muted" }, "If you bought on ", input), ring, info);
  return box;
}

// --- line chart with hover ------------------------------------------------------------------------------
export function lineChart(points, show = { sma50: false, sma200: false, spy: false }, width = 760) {
  // Drawn at the container's real width so labels stay readable on phones.
  const W = Math.max(300, Math.round(width || 760)), H = W < 560 ? 230 : 300, P = { l: 46, r: 10, t: 12, b: 26 };
  const svg = svgEl("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Price chart" });
  if (!points.length) return svg;
  const keys = [["adj_close", "#102a43", 2], ...(show.sma50 ? [["sma50", "#e8a317", 1.5]] : []),
    ...(show.sma200 ? [["sma200", "#7b8794", 1.5]] : []), ...(show.spy ? [["spy_rebased", "#2457c5", 1.2]] : [])];
  let min = Infinity, max = -Infinity;
  for (const p of points) for (const [k] of keys) if (p[k] != null) { min = Math.min(min, p[k]); max = Math.max(max, p[k]); }
  const pad = (max - min) * 0.06 || 1;
  min -= pad; max += pad;
  const X = (i) => P.l + (i / (points.length - 1 || 1)) * (W - P.l - P.r);
  const Y = (v) => P.t + (1 - (v - min) / (max - min)) * (H - P.t - P.b);
  const grid = svgEl("g", { class: "grid" }), axis = svgEl("g", { class: "axis" });
  for (let i = 0; i <= 4; i++) {
    const v = min + ((max - min) * i) / 4;
    grid.append(svgEl("line", { x1: P.l, x2: W - P.r, y1: Y(v), y2: Y(v) }));
    axis.append(svgEl("text", { x: P.l - 8, y: Y(v) + 4, "text-anchor": "end" }, v >= 1000 ? v.toFixed(0) : v.toFixed(v < 10 ? 2 : 0)));
  }
  const ticks = Math.min(W < 560 ? 3 : 5, points.length - 1 || 1);
  // Up to about seven months, label days ("Aug 10"). Beyond that, months ("Aug 2025").
  const shortSpan = new Date(points[points.length - 1].date) - new Date(points[0].date) < 215 * 864e5;
  for (let i = 0; i <= ticks; i++) {
    const idx = Math.round(((points.length - 1) * i) / ticks);
    axis.append(svgEl("text", { x: X(idx), y: H - 6, "text-anchor": i === 0 ? "start" : i === ticks ? "end" : "middle" },
      dateStr(points[idx].date, shortSpan ? { month: "short", day: "numeric" } : { month: "short", year: "numeric" })));
  }
  svg.append(grid, axis);
  for (const [k, color, w] of keys) {
    let d = "", pen = false;
    points.forEach((p, i) => {
      if (p[k] == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(p[k]).toFixed(1)}`;
      pen = true;
    });
    svg.append(svgEl("path", { d, fill: "none", stroke: color, "stroke-width": w, "stroke-linejoin": "round" }));
  }
  const cross = svgEl("line", { y1: P.t, y2: H - P.b, stroke: "#829ab1", "stroke-dasharray": "3 3", visibility: "hidden" });
  const dot = svgEl("circle", { r: 4, fill: "#102a43", visibility: "hidden" });
  const tip = svgEl("text", { y: P.t + 12, fill: "#102a43", "font-size": 12, "font-family": "Instrument Sans, sans-serif", visibility: "hidden" });
  svg.append(cross, dot, tip);
  svg.addEventListener("mousemove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(points.length - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (points.length - 1))));
    const p = points[i];
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i));
    dot.setAttribute("cx", X(i)); dot.setAttribute("cy", Y(p.adj_close));
    const extra = W < 560 ? "" : (show.sma50 && p.sma50 ? `  · 50-day ${num(p.sma50, 2)}` : "") + (show.sma200 && p.sma200 ? `  · 200-day ${num(p.sma200, 2)}` : "");
    tip.textContent = `${dateStr(p.date)}  ${num(p.adj_close, 2)}${extra}`;
    tip.setAttribute("x", Math.max(P.l, Math.min(X(i) + 8, W - (W < 560 ? 190 : 260 + (extra.length > 24 ? 110 : 0)))));
    for (const n of [cross, dot, tip]) n.setAttribute("visibility", "visible");
  });
  svg.addEventListener("mouseleave", () => { for (const n of [cross, dot, tip]) n.setAttribute("visibility", "hidden"); });
  return svg;
}

// The price chart on stock and index pages: range buttons (1M to Max, plus custom dates), optional lines
// (50-day and 200-day averages, the S&P 500), and the return over whatever window is showing.
// It starts on year-to-date with just the price, and remembers each ticker's settings for the visit.
const CHART_RANGES = [["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["ytd", "YTD"], ["1y", "1Y"], ["3y", "3Y"], ["5y", "5Y"], ["max", "Max"]];
const chartMemory = new Map();
export function priceChart(ticker, opts = {}) {
  if (!chartMemory.has(ticker)) chartMemory.set(ticker, { range: "ytd", start: "", end: "", show: { sma50: false, sma200: false, spy: false } });
  const st = chartMemory.get(ticker), show = st.show;
  const chartBox = el("div", { class: "price-chart-plot" });
  const summary = el("p", { class: "chart-summary small muted" });
  let data = null, loaded = "", drawnWidth = 0, seq = 0;
  async function draw() {
    const want = st.range === "custom" ? `c:${st.start}:${st.end}` : st.range;
    if (loaded !== want) {
      const my = ++seq;
      chartBox.classList.add("loading-dim");
      const q = st.range === "custom" ? `start=${st.start}${st.end ? `&end=${st.end}` : ""}` : `range=${st.range}`;
      try {
        const res = await api(`/api/stocks/${encodeURIComponent(ticker)}/prices?${q}`);
        if (my !== seq) return;
        data = res; loaded = want;
      } catch (e) {
        if (my !== seq) return;
        chartBox.classList.remove("loading-dim");
        chartBox.replaceChildren(el("p", { class: "err" }, e.message));
        summary.replaceChildren();
        return;
      }
      chartBox.classList.remove("loading-dim");
    }
    drawnWidth = chartBox.clientWidth;
    chartBox.replaceChildren(lineChart(data.points, show, drawnWidth));
    const p = data.points, chg = p.length > 1 ? p[p.length - 1].adj_close / p[0].adj_close - 1 : null;
    const spy = p.length > 1 && p[0].spy_rebased ? p[p.length - 1].spy_rebased / p[0].spy_rebased - 1 : null;
    summary.replaceChildren(el("b", { class: cls(chg) }, pct(chg, 1, true)), ` from ${dateStr(data.start)} to ${dateStr(data.end)}, dividends included`,
      show.spy && spy != null ? [". S&P 500: ", el("b", { class: cls(spy) }, pct(spy, 1, true))] : "", ".");
  }
  new ResizeObserver(() => { if (data && Math.abs(chartBox.clientWidth - drawnWidth) > 40) draw(); }).observe(chartBox);

  const fromIn = el("input", { type: "date", "aria-label": "From", value: st.start });
  const toIn = el("input", { type: "date", "aria-label": "To", value: st.end });
  const custom = el("div", { class: "custom-dates", hidden: st.range !== "custom" },
    el("label", {}, "From ", fromIn), el("label", {}, "to ", toIn),
    el("button", { class: "btn small", type: "button", onclick: () => {
      if (!fromIn.value) { fromIn.focus(); return; }
      st.range = "custom"; st.start = fromIn.value; st.end = toIn.value; mark(); draw(); } }, "Apply"));
  const seg = el("div", { class: "seg period-seg", role: "group", "aria-label": "Chart range" },
    ...CHART_RANGES.map(([k, label]) => el("button", { type: "button", "data-k": k, onclick: () => {
      st.range = k; custom.hidden = true; mark(); draw(); } }, label)),
    el("button", { type: "button", "data-k": "custom", onclick: () => {
      custom.hidden = false; mark("custom");
      if (data && !fromIn.value) { fromIn.value = data.start; toIn.value = data.end; }
      fromIn.focus(); } }, "Custom"));
  function mark(force) {
    const on = force || st.range;
    seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.k === on)));
  }
  mark();
  const key = (k, label, color, term) => el("label", {},
    el("input", { type: "checkbox", checked: show[k], onchange: (e) => { show[k] = e.target.checked; draw(); } }),
    el("i", { style: { background: color } }), label, term ? learnLink(term) : "");
  const keys = el("div", { class: "keys" }, key("sma50", "50-day avg", "#e8a317", "moving-average"), key("sma200", "200-day avg", "#7b8794", "moving-average"),
    opts.noSpy ? "" : key("spy", "S&P 500 (same start)", "#2457c5", "beating-the-index"));
  const node = el("div", { class: "price-chart" }, el("div", { class: "chart-controls" }, seg, keys), custom, chartBox, summary);
  draw();
  return node;
}

export function bars(items, fmt) {
  const box = el("div", { class: "bars" });
  const max = Math.max(...items.map((i) => Math.abs(i.value || 0)), 1);
  for (const it of items) {
    const h = Math.max(2, (Math.abs(it.value || 0) / max) * 80);
    box.append(el("div", { class: "bar", title: `${it.label}: ${fmt(it.value)}` },
      el("span", {}, fmt(it.value)), el("i", { class: (it.value || 0) < 0 ? "neg" : "", style: { height: `${h}px` } }), el("span", {}, it.label)));
  }
  return box;
}

// --- treemap (squarified) ---------------------------------------------------------------------------------
function squarify(items, x, y, w, h) {
  const out = [];
  const total = items.reduce((s, i) => s + i.value, 0);
  if (!total) return out;
  let rest = items.slice().sort((a, b) => b.value - a.value);
  const scale = (w * h) / total;
  rest = rest.map((i) => ({ ...i, area: i.value * scale }));
  while (rest.length) {
    const vertical = w < h;
    const side = vertical ? w : h;
    let row = [rest[0]], best = worst(row, side);
    let k = 1;
    while (k < rest.length) {
      const trial = [...row, rest[k]];
      const wr = worst(trial, side);
      if (wr > best) break;
      row = trial; best = wr; k++;
    }
    const sum = row.reduce((s, r) => s + r.area, 0);
    const thick = sum / side;
    let off = 0;
    for (const r of row) {
      const len = r.area / thick;
      out.push(vertical ? { ...r, x: x + off, y, w: len, h: thick } : { ...r, x, y: y + off, w: thick, h: len });
      off += len;
    }
    if (vertical) { y += thick; h -= thick; } else { x += thick; w -= thick; }
    rest = rest.slice(row.length);
  }
  return out;
}
function worst(row, side) {
  const s = row.reduce((a, r) => a + r.area, 0);
  const mx = Math.max(...row.map((r) => r.area)), mn = Math.min(...row.map((r) => r.area));
  return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
}

export function treemap(groups, colorOf, onClick) {
  const box = el("div", { class: "treemap", role: "group", "aria-label": "S&P 500 by sector, sized by company value" });
  const draw = () => {
    box.replaceChildren();
    const W = box.clientWidth || 900, H = box.clientHeight || 440;
    const sect = squarify(groups.map((g) => ({ ...g, value: g.items.reduce((s, i) => s + i.value, 0) })), 0, 0, W, H);
    for (const s of sect) {
      const head = s.w > 90 && s.h > 70 ? 18 : 0;   // a strip for the sector's name, so it never covers a ticker
      const cells = squarify(s.items, s.x, s.y + head, s.w, s.h - head);
      for (const c of cells) {
        const a = el("a", { class: "cell", href: c.href, title: `${c.label}: ${c.title}`,
          style: { left: `${c.x}px`, top: `${c.y}px`, width: `${c.w}px`, height: `${c.h}px`, background: colorOf(c) } });
        if (c.w > 44 && c.h > 26) a.append(el("b", {}, c.label), c.w > 70 && c.h > 40 ? c.sub : "");
        if (onClick) a.addEventListener("click", (e) => onClick(e, c));
        box.append(a);
      }
      if (head) box.append(el("div", { class: "sector-label", style: { left: `${s.x}px`, top: `${s.y}px`, width: `${s.w}px`, height: `${head}px` } }, s.label));
    }
  };
  requestAnimationFrame(draw);
  new ResizeObserver(() => draw()).observe(box);
  return box;
}

// --- markdown (escaped first; supports headings, bold, italics, lists, links, code) -------------------------
export function markdown(md) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|\s)_([^_]+)_(?=\s|$|[.,;])/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\[([^\]]+)\]\((#\/[\w\-/?=&;.%~]*)\)/g, '<a class="inapp" href="$2">$1</a>')   // links to Ticker Tutor's own pages
    .replace(/\[(\d+)\]/g, '<sup><a class="cite" data-src="$1" href="" role="button">[$1]</a></sup>');
  const lines = md.split("\n");
  let html = "", list = null;
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if (!line.trim()) { close(); continue; }
    if ((m = line.match(/^(#{1,4})\s+(.*)/))) { close(); html += `<h3>${inline(m[2])}</h3>`; continue; }
    if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; continue; }
    if ((m = line.match(/^\s*(\d+)\.\s+(.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[2])}</li>`; continue; }
    close();
    html += `<p>${inline(line)}</p>`;
  }
  close();
  return html;
}
