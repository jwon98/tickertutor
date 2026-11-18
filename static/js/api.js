// Shared helpers: fetch, DOM building, number formatting.

export async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers["Content-Type"] = "application/json";
  }
  let res;
  try { res = await fetch(path, init); } catch { throw new Error("Can't reach Ticker Tutor. Check your connection and try again."); }
  let data = {};
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) throw new Error(data.error || (Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail) || `Request failed (${res.status}).`);
  return data;
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "style" && typeof v === "object") {
      for (const [prop, val] of Object.entries(v)) {
        if (prop.startsWith("--")) node.style.setProperty(prop, val);
        else node.style[prop] = val;
      }
    }
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) node.setAttribute(k, v);
  for (const c of children.flat()) if (c) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}

const isNum = (v) => typeof v === "number" && Number.isFinite(v);
export const pct = (v, d = 1, sign = false) => {
  if (!isNum(v)) return "—";
  const s = (v * 100).toFixed(d);
  if (Number(s) === 0) return `${(0).toFixed(d)}%`;   // no "-0%"
  return `${sign && v > 0 ? "+" : ""}${s}%`;
};
export const pts = (v, d = 1) => {
  if (!isNum(v)) return "—";
  const s = (v * 100).toFixed(d);
  return Number(s) === 0 ? `${(0).toFixed(d)} pts` : `${v > 0 ? "+" : ""}${s} pts`;
};
export const num = (v, d = 1) => (isNum(v) ? v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }) : "—");
export const money = (v) => (isNum(v) ? `$${v.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}` : "—");
export function big(v) {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}
export const cls = (v) => (isNum(v) ? (v > 0 ? "up" : v < 0 ? "down" : "") : "");
export function dateStr(iso, opts = { month: "short", day: "numeric", year: "numeric" }) {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, opts);
}

export function toast(message, isError = false) {
  const box = document.getElementById("toasts");
  const t = el("div", { class: "toast" + (isError ? " err" : "") }, message);
  box.append(t);
  setTimeout(() => t.remove(), isError ? 6000 : 3000);
}

export const VERDICT_LABEL = {
  held_up: "Held up", worse: "Did worse", mixed: "Mixed", no_clear_edge: "No clear edge", too_little_data: "Too little data",
};
