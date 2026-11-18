// Charts for the Analyze page: stacked panels that share a date axis (price + indicator),
// a histogram with a bell curve, and a scatter plot with a best-fit line. Plain SVG, drawn at
// the container's real width so text stays readable on phones.
import { el, svgEl, dateStr } from "./api.js";

const COLORS = { ink: "#102a43", gold: "#e8a317", grey: "#7b8794", blue: "#2457c5", up: "#17795a", down: "#c2492f",
  violet: "#7a4fb0", faint: "#bcccdc" };
const color = (c) => COLORS[c] || c || COLORS.ink;

export function fmt(v, kind, compact = false) {
  if (v == null || !Number.isFinite(v)) return "—";
  switch (kind) {
    case "money": return `$${Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(compact ? 0 : 2)}`;
    case "pct": return `${(v * 100).toFixed(compact ? 0 : Math.abs(v) < 0.1 ? 2 : 1)}%`;
    case "num0": return v.toFixed(0);
    case "big": return Math.abs(v) >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M`
      : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : v.toFixed(0);
    default: return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
  }
}

function niceTicks(min, max, count = 4) {
  const span = max - min || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count + 1) || raw;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-12; v += step) out.push(+v.toFixed(12));
  return out;
}

function linePath(vals, X, Y) {
  let d = "", pen = false;
  vals.forEach((v, i) => {
    if (v == null) { pen = false; return; }
    d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}

// --- stacked time-series panels ---------------------------------------------------------------------------
export function panelChart(res, width) {
  const { dates, data, panels } = res;
  const n = dates.length;
  const W = Math.max(300, Math.round(width || 760));
  const P = { l: W < 520 ? 44 : 56, r: 12, t: 8, b: 6 };
  const X = (i) => P.l + (i / Math.max(1, n - 1)) * (W - P.l - P.r);
  const wrap = el("div", { class: "pchart" });
  const tip = el("div", { class: "ptip", hidden: true });
  const overlays = [];
  const markerIdx = (iso) => {
    let lo = 0, hi = n - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (dates[mid] < iso) lo = mid + 1; else hi = mid; }
    return lo;
  };

  panels.forEach((p, pi) => {
    const last = pi === panels.length - 1;
    const H = Math.round((p.height || 200) * (W < 520 ? 0.8 : 1)) + (last ? 22 : 0);
    const plotB = H - P.b - (last ? 22 : 0);
    const keys = p.series.map((s) => s.key).concat(p.band ? [p.band.lo, p.band.hi] : []);
    let min = Infinity, max = -Infinity;
    for (const k of keys) for (const v of data[k] || []) if (v != null) { if (v < min) min = v; if (v > max) max = v; }
    for (const h of p.hlines || []) { if (h.style !== "faint") { min = Math.min(min, h.y); max = Math.max(max, h.y); } }
    if (p.y?.zero) { min = Math.min(min, 0); max = Math.max(max, 0); }
    if (!Number.isFinite(min)) { min = 0; max = 1; }
    const pad = (max - min) * 0.06 || Math.abs(max) * 0.05 || 1;
    min = p.y?.min ?? min - pad; max = p.y?.max ?? max + pad;
    if (p.y?.max === 0) max = Math.max(0, max);
    const Y = (v) => P.t + (1 - (v - min) / (max - min || 1)) * (plotB - P.t);
    const svg = svgEl("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": p.title });
    const g = svgEl("g", { class: "grid" }), ax = svgEl("g", { class: "axis" });
    for (const v of niceTicks(min, max, H < 170 ? 3 : 4)) {
      if (v < min || v > max) continue;
      g.append(svgEl("line", { x1: P.l, x2: W - P.r, y1: Y(v), y2: Y(v) }));
      ax.append(svgEl("text", { x: P.l - 6, y: Y(v) + 4, "text-anchor": "end" }, fmt(v, p.y?.fmt, true)));
    }
    svg.append(g, ax);
    if (p.band && data[p.band.lo]) {
      const lo = data[p.band.lo], hi = data[p.band.hi];
      let d = "";
      const idx = lo.map((v, i) => (v != null && hi[i] != null ? i : -1)).filter((i) => i >= 0);
      if (idx.length) {
        d = idx.map((i, j) => `${j ? "L" : "M"}${X(i).toFixed(1)},${Y(hi[i]).toFixed(1)}`).join("")
          + idx.slice().reverse().map((i) => `L${X(i).toFixed(1)},${Y(lo[i]).toFixed(1)}`).join("") + "Z";
        svg.append(svgEl("path", { d, fill: "rgba(36,87,197,.09)", stroke: "rgba(36,87,197,.25)", "stroke-width": 1 }));
      }
    }
    for (const h of p.hlines || []) {
      if (h.y < min || h.y > max) continue;
      svg.append(svgEl("line", { x1: P.l, x2: W - P.r, y1: Y(h.y), y2: Y(h.y), stroke: h.style === "faint" ? "#d9e2ec" : "#829ab1",
        "stroke-dasharray": "4 4", "stroke-width": 1 }));
      if (h.label) svg.append(svgEl("text", { x: W - P.r - 4, y: Y(h.y) - 4, "text-anchor": "end", class: "hlabel" }, h.label));
    }
    const base = Y(Math.max(min, Math.min(max, 0)));
    for (const s of p.series) {
      const vals = data[s.key] || [];
      if (s.style === "bar") {
        const bw = Math.max(1, (W - P.l - P.r) / Math.max(1, n) * 0.8);
        const bars = svgEl("g", {});
        vals.forEach((v, i) => {
          if (v == null) return;
          const y = Y(v);
          const fill = s.key === "hist" ? (v >= 0 ? "rgba(23,121,90,.45)" : "rgba(194,73,47,.45)") : "rgba(130,154,177,.55)";
          bars.append(svgEl("rect", { x: X(i) - bw / 2, y: Math.min(y, base), width: bw, height: Math.max(0.5, Math.abs(base - y)), fill }));
        });
        svg.append(bars);
      } else if (s.style === "area") {
        const d = linePath(vals, X, Y);
        const first = vals.findIndex((v) => v != null);
        const lastI = vals.length - 1 - [...vals].reverse().findIndex((v) => v != null);
        if (first >= 0) svg.append(svgEl("path", { d: `${d}L${X(lastI)},${base}L${X(first)},${base}Z`, fill: "rgba(194,73,47,.14)" }));
        svg.append(svgEl("path", { d, fill: "none", stroke: color(s.color), "stroke-width": 1.6 }));
      } else {
        svg.append(svgEl("path", { d: linePath(vals, X, Y), fill: "none", stroke: color(s.color),
          "stroke-width": s.color === "ink" ? 1.9 : 1.5, "stroke-dasharray": s.style === "dash" ? "5 4" : null,
          "stroke-linejoin": "round" }));
      }
    }
    for (const m of (res.markers || []).filter((m) => (m.panel || 0) === pi)) {
      const i = markerIdx(m.date);
      const x = X(i);
      const up = m.kind === "up";
      const y = up ? plotB - 2 : P.t + 2;
      const tri = up ? `M${x},${y - 9}L${x - 5},${y}L${x + 5},${y}Z` : `M${x},${y + 9}L${x - 5},${y}L${x + 5},${y}Z`;
      svg.append(svgEl("line", { x1: x, x2: x, y1: P.t, y2: plotB, stroke: up ? "rgba(23,121,90,.35)" : "rgba(194,73,47,.35)",
        "stroke-dasharray": "2 3" }));
      svg.append(svgEl("path", { d: tri, fill: up ? COLORS.up : COLORS.down }, svgEl("title", {}, `${m.label}: ${dateStr(m.date)}`)));
    }
    if (last) {
      const count = W < 520 ? 3 : 6;
      for (let k = 0; k <= count; k++) {
        const i = Math.round((k / count) * (n - 1));
        const span = (new Date(dates[n - 1]) - new Date(dates[0])) / 864e5;
        const opts = span > 400 ? { month: "short", year: "numeric" } : { month: "short", day: "numeric" };
        ax.append(svgEl("text", { x: X(i), y: H - 6, "text-anchor": k === 0 ? "start" : k === count ? "end" : "middle" },
          dateStr(dates[i], opts)));
      }
    }
    const hover = svgEl("g", { class: "hover", visibility: "hidden" });
    const vline = svgEl("line", { y1: P.t, y2: plotB, stroke: "#486581", "stroke-width": 1 });
    hover.append(vline);
    const dotsG = p.series.filter((s) => s.style !== "bar").map((s) => {
      const c = svgEl("circle", { r: 3.5, fill: color(s.color), stroke: "#fff", "stroke-width": 1.5 });
      hover.append(c);
      return [s, c];
    });
    svg.append(hover);
    overlays.push({ show(i) {
      hover.setAttribute("visibility", "visible");
      vline.setAttribute("x1", X(i)); vline.setAttribute("x2", X(i));
      for (const [s, c] of dotsG) {
        const v = data[s.key]?.[i];
        if (v == null) { c.setAttribute("visibility", "hidden"); continue; }
        c.setAttribute("visibility", "visible"); c.setAttribute("cx", X(i)); c.setAttribute("cy", Y(v));
      }
    }, hide() { hover.setAttribute("visibility", "hidden"); } });
    const legend = el("div", { class: "plegend" }, el("b", {}, p.title),
      ...p.series.map((s) => el("span", {}, el("i", { class: `sw ${s.style || "line"}`, style: { "--c": color(s.color) } }), s.label)),
      p.band ? el("span", {}, el("i", { class: "sw band" }), p.band.label) : "");
    const box = el("div", { class: "ppanel" }, legend, svg);
    const move = (ev) => {
      const rect = svg.getBoundingClientRect();
      const x = ((ev.clientX - rect.left) / rect.width) * W;
      const i = Math.max(0, Math.min(n - 1, Math.round(((x - P.l) / (W - P.l - P.r)) * (n - 1))));
      overlays.forEach((o) => o.show(i));
      tip.hidden = false;
      tip.replaceChildren(el("b", {}, dateStr(dates[i])), ...panels.flatMap((pp) => pp.series.map((s) => {
        const v = data[s.key]?.[i];
        return v == null ? "" : el("div", {}, el("i", { class: "sw line", style: { "--c": color(s.color) } }), `${s.label}: `,
          el("b", {}, fmt(v, pp.y?.fmt)));
      })));
      const wrapRect = wrap.getBoundingClientRect();
      const left = ev.clientX - wrapRect.left;
      tip.style.left = `${left > wrapRect.width / 2 ? left - tip.offsetWidth - 14 : left + 14}px`;
      tip.style.top = `${ev.clientY - wrapRect.top + 12}px`;
    };
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerdown", move);
    svg.addEventListener("pointerleave", () => { overlays.forEach((o) => o.hide()); tip.hidden = true; });
    wrap.append(box);
  });
  wrap.append(tip);
  return wrap;
}

// --- histogram with a bell curve -----------------------------------------------------------------------------
export function histogramChart(ex, width) {
  const W = Math.max(300, Math.round(width || 760)), H = W < 520 ? 240 : 300;
  const P = { l: W < 520 ? 40 : 52, r: 12, t: 12, b: 34 };
  const lo = ex.bins[0][0], hi = ex.bins[ex.bins.length - 1][1];
  const maxC = Math.max(...ex.bins.map((b) => b[2]), ...ex.normal.map((p) => p[1]));
  const X = (v) => P.l + ((v - lo) / (hi - lo || 1)) * (W - P.l - P.r);
  const Y = (c) => P.t + (1 - c / (maxC * 1.08 || 1)) * (H - P.t - P.b);
  const svg = svgEl("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": ex.title });
  const g = svgEl("g", { class: "grid" }), ax = svgEl("g", { class: "axis" });
  for (const c of niceTicks(0, maxC * 1.08, 4)) {
    g.append(svgEl("line", { x1: P.l, x2: W - P.r, y1: Y(c), y2: Y(c) }));
    ax.append(svgEl("text", { x: P.l - 6, y: Y(c) + 4, "text-anchor": "end" }, c.toFixed(0)));
  }
  for (const v of niceTicks(lo, hi, W < 520 ? 4 : 7)) {
    if (v < lo || v > hi) continue;
    ax.append(svgEl("text", { x: X(v), y: H - P.b + 16, "text-anchor": "middle" }, fmt(v, ex.fmt, true)));
  }
  ax.append(svgEl("text", { x: (P.l + W - P.r) / 2, y: H - 2, "text-anchor": "middle" }, "return"));
  svg.append(g, ax);
  for (const [a, b, c] of ex.bins) {
    svg.append(svgEl("rect", { x: X(a) + 0.5, y: Y(c), width: Math.max(1, X(b) - X(a) - 1), height: Math.max(0, Y(0) - Y(c)),
      fill: a + b < 0 ? "rgba(194,73,47,.55)" : "rgba(23,121,90,.55)" },
      svgEl("title", {}, `${fmt(a, ex.fmt)} to ${fmt(b, ex.fmt)}: ${c} time${c === 1 ? "" : "s"}`)));
  }
  svg.append(svgEl("path", { d: linePath(ex.normal.map((p) => p[1]), (i) => X(ex.normal[i][0]), Y), fill: "none",
    stroke: COLORS.ink, "stroke-width": 1.8 }));
  svg.append(svgEl("line", { x1: X(ex.mean), x2: X(ex.mean), y1: P.t, y2: Y(0), stroke: COLORS.gold, "stroke-dasharray": "5 4",
    "stroke-width": 1.5 }));
  for (const k of [-3, 3]) {
    const v = ex.mean + k * ex.sd;
    if (v > lo && v < hi) svg.append(svgEl("line", { x1: X(v), x2: X(v), y1: P.t, y2: Y(0), stroke: "#829ab1", "stroke-dasharray": "2 4" }));
  }
  return el("div", { class: "pchart" }, el("div", { class: "plegend" }, el("b", {}, ex.title),
    el("span", {}, el("i", { class: "sw bar" , style: { "--c": "rgba(23,121,90,.55)" } }), "Actual (count)"),
    el("span", {}, el("i", { class: "sw line", style: { "--c": COLORS.ink } }), "Bell curve, same average and spread"),
    el("span", {}, el("i", { class: "sw dash", style: { "--c": COLORS.gold } }), "Average"),
    el("span", {}, el("i", { class: "sw dash", style: { "--c": "#829ab1" } }), "±3 standard deviations")), svg);
}

// --- scatter with best-fit line ----------------------------------------------------------------------------
export function scatterChart(ex, width) {
  const W = Math.max(300, Math.round(width || 760)), H = Math.min(420, Math.round(W * 0.62));
  const P = { l: W < 520 ? 44 : 56, r: 14, t: 12, b: 38 };
  const xs = ex.points.map((p) => p[0]), ys = ex.points.map((p) => p[1]);
  const q = (arr, f) => { const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.max(0, Math.floor(f * (s.length - 1))))]; };
  // Zoom to the middle 99.4% so a couple of extreme days don't squash the rest (they're still counted in beta).
  const xr = Math.max(Math.abs(q(xs, 0.003)), Math.abs(q(xs, 0.997))) * 1.1 || 0.02;
  const yr = Math.max(Math.abs(q(ys, 0.003)), Math.abs(q(ys, 0.997))) * 1.1 || 0.02;
  const X = (v) => P.l + ((v + xr) / (2 * xr)) * (W - P.l - P.r);
  const Y = (v) => P.t + (1 - (v + yr) / (2 * yr)) * (H - P.t - P.b);
  const svg = svgEl("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": ex.title });
  const g = svgEl("g", { class: "grid" }), ax = svgEl("g", { class: "axis" });
  for (const v of niceTicks(-yr, yr, 4)) {
    g.append(svgEl("line", { x1: P.l, x2: W - P.r, y1: Y(v), y2: Y(v) }));
    ax.append(svgEl("text", { x: P.l - 6, y: Y(v) + 4, "text-anchor": "end" }, fmt(v, "pct", true)));
  }
  for (const v of niceTicks(-xr, xr, W < 520 ? 4 : 6)) {
    g.append(svgEl("line", { x1: X(v), x2: X(v), y1: P.t, y2: H - P.b }));
    ax.append(svgEl("text", { x: X(v), y: H - P.b + 15, "text-anchor": "middle" }, fmt(v, "pct", true)));
  }
  ax.append(svgEl("text", { x: (P.l + W - P.r) / 2, y: H - 3, "text-anchor": "middle" }, ex.x_label));
  svg.append(g, ax);
  svg.append(svgEl("line", { x1: X(0), x2: X(0), y1: P.t, y2: H - P.b, stroke: "#829ab1" }));
  svg.append(svgEl("line", { x1: P.l, x2: W - P.r, y1: Y(0), y2: Y(0), stroke: "#829ab1" }));
  const dotsG = svgEl("g", {});
  for (const [x, y] of ex.points) {
    if (Math.abs(x) > xr || Math.abs(y) > yr) continue;
    dotsG.append(svgEl("circle", { cx: X(x).toFixed(1), cy: Y(y).toFixed(1), r: 2.4, fill: "rgba(36,87,197,.32)" }));
  }
  svg.append(dotsG);
  const { slope, intercept } = ex.fit;
  const x1 = -xr, x2 = xr;
  svg.append(svgEl("line", { x1: X(x1), y1: Y(intercept + slope * x1), x2: X(x2), y2: Y(intercept + slope * x2),
    stroke: COLORS.gold, "stroke-width": 2.2 }));
  svg.append(svgEl("line", { x1: X(x1), y1: Y(x1), x2: X(x2), y2: Y(x2), stroke: "#829ab1", "stroke-dasharray": "5 4" }));
  return el("div", { class: "pchart" }, el("div", { class: "plegend" }, el("b", {}, `${ex.title} (${ex.y_label} vs ${ex.x_label})`),
    el("span", {}, el("i", { class: "sw line", style: { "--c": COLORS.gold } }), `Best-fit line: slope = beta ${fmt(slope)}`),
    el("span", {}, el("i", { class: "sw dash", style: { "--c": "#829ab1" } }), "Slope 1 (moves one-for-one)")), svg);
}
