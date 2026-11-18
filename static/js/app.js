// Shell and router. Pages live in ./pages/*.js and export render(root, params, ctx).
import { api, el, dateStr, toast } from "./api.js";

const ICONS = {
  guide: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18M12 5h6l2.5 2.5L18 10h-6M12 12H6l-2.5 2.5L6 17h6"/></svg>',
  screener: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>',
  analyze: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19h16M5 15l4-5 4 3 6-7"/><circle cx="19" cy="6" r="1.2" fill="currentColor"/></svg>',
  news: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5h11v14H6a1 1 0 0 1-1-1zM16 9h3v9a1 1 0 0 1-1 1h-2M8 9h5M8 13h5"/></svg>',
  research: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/></svg>',
  learn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6l8-3 8 3-8 3zM8 8v5c0 1.5 2 3 4 3s4-1.5 4-3V8"/></svg>',
};
// The mark: a tutor's speech bubble with a rising price line inside.
const LOGO = '<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M16 6h32a12 12 0 0 1 12 12v20a12 12 0 0 1-12 12H30L15 60l2-10.2A12 12 0 0 1 4 38V18A12 12 0 0 1 16 6z" fill="#102a43"/><path d="M14 36l9-9 8 6 9-11" fill="none" stroke="#fff" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="46" cy="16" r="6.5" fill="#f2b632"/></svg>';

// The home page has no tab: the brand links to it. Stock and index pages sit under the Screener.
const ROUTES = [
  ["guide", "How it works", /^#\/(guide|overview|how)/],
  ["screener", "Screener", /^#\/screener/],
  ["analyze", "Analyze", /^#\/(analyze|signals)/],
  ["news", "In the news", /^#\/news/],
  ["research", "Research desk", /^#\/research/],
  ["learn", "Learn", /^#\/learn/],
];

const app = document.getElementById("app");
const ctx = { meta: null, restored: false };
let main, nav, asof;

// Which tab a hash belongs to. Stock and index pages count as the Screener. The home page has none.
function tabOf(hash) {
  if (/^#\/(stock|index)\//.test(hash)) return "screener";
  for (const [id, , re] of ROUTES) if (re.test(hash)) return id;
  return null;
}
// Each tab remembers the last thing it showed, so switching tabs and coming back picks up where you were.
// Clicking the tab you're already on goes to its start.
const lastHash = {};
const scrollPos = new Map();
let restoreScroll = false;

async function boot() {
  try {
    ctx.meta = await api("/api/meta");
  } catch (e) {
    app.replaceChildren(el("div", { class: "page" }, el("h1", {}, "Ticker Tutor isn't ready"), el("p", { class: "err" }, e.message)));
    return;
  }
  nav = el("nav", { class: "nav", "aria-label": "Sections" });
  for (const [id, label] of ROUTES) {
    nav.append(el("a", { href: `#/${id}`, "data-id": id, html: ICONS[id] + `<span>${label}</span>` }));
  }
  asof = el("div", { class: "asof" });
  drawAsOf();
  const rail = el("header", { class: "rail" },
    el("a", { class: "brand", href: "#/", html: LOGO + "<span>Ticker Tutor</span>", "aria-label": "Ticker Tutor home" }), nav, asof);
  main = el("main", { id: "main" });
  const shell = el("div", { class: "shell" }, rail, el("div", {},
    ctx.meta.synthetic ? el("div", { class: "banner", role: "note" }, el("b", {}, "Demo data. "),
      "Every price, filing, and headline here is simulated so the app runs offline. Build real data with scripts/build_data.py.") : "",
    main));
  app.replaceChildren(shell);
  // Coming back to a tab (or using a "back" link) returns to where you had scrolled.
  document.addEventListener("click", (e) => { restoreScroll = Boolean(e.target.closest?.(".nav a, a.back")); }, true);
  window.addEventListener("hashchange", (e) => {
    const old = new URL(e.oldURL).hash || "#/";
    scrollPos.set(old, window.scrollY);
    const tab = tabOf(old);
    if (tab) lastHash[tab] = old;   // also catches pages that update their own address, like Analyze
    route();
  });
  route();
  watchData();
}

function drawAsOf(note) {
  const m = ctx.meta;
  asof.replaceChildren("Prices as of", el("b", {}, dateStr(m.as_of)),
    m.synthetic ? "Synthetic demo data" : `Source: ${String(m.provider || "").replace(/^./, (ch) => ch.toUpperCase())}`,
    note ? el("span", { class: "asof-note" }, note) : "");
}

// Prices are refreshed once a day in the background. While that runs, say so. When it lands, show the new data.
async function watchData() {
  let delay = 20000;
  try {
    const s = await api("/api/data-status");
    if (s.as_of && s.as_of !== ctx.meta.as_of) {
      ctx.meta = await api("/api/meta");
      drawAsOf();
      toast(`Prices updated through ${dateStr(ctx.meta.as_of)}`);
      if (!/^#\/research/.test(location.hash)) route(true);
    } else drawAsOf(s.state === "running" ? "Updating prices…" : s.state === "failed" ? "Couldn't update prices today" : "");
    if (s.state !== "running") delay = 10 * 60000;
    asof.title = s.message || "";
  } catch { delay = 5 * 60000; }
  setTimeout(watchData, delay);
}

async function route(keepScroll = false) {
  const h = location.hash || "#/";
  let id = "home", params = {};
  const m = h.match(/^#\/(stock|index)\/([A-Za-z.\-]+)/);
  if (m) { id = m[1]; params = { ticker: m[2].toUpperCase() }; }
  else for (const [rid, , re] of ROUTES) if (re.test(h)) id = rid;
  const q = h.split("?")[1];
  if (q) for (const [k, v] of new URLSearchParams(q)) params[k] = v;
  const tab = tabOf(h);
  if (tab) lastHash[tab] = h;
  for (const a of nav.querySelectorAll("a")) {
    const here = a.dataset.id === tab;
    if (here) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    a.setAttribute("href", here ? `#/${a.dataset.id}` : lastHash[a.dataset.id] || `#/${a.dataset.id}`);
  }
  const back = restoreScroll && scrollPos.has(h), y = keepScroll ? window.scrollY : back ? scrollPos.get(h) : 0;
  restoreScroll = false;
  ctx.restored = back || keepScroll;
  const page = el("div", { class: `page page-${id}` }, el("p", { class: "loading" }, "Loading…"));
  if (keepScroll) page.style.minHeight = `${main.offsetHeight}px`;
  main.replaceChildren(page);
  if (!keepScroll) window.scrollTo(0, 0);
  try {
    const mod = await import(`./pages/${id}.js`);
    await mod.render(page, params, ctx);
  } catch (e) {
    console.error(e);
    page.replaceChildren(el("h1", {}, "Something went wrong"), el("p", { class: "err" }, e.message),
      el("a", { class: "btn", href: "#/" }, "Back to the home page"));
  }
  if (!page.isConnected) return;   // the visitor already moved on to another page
  page.style.minHeight = "";
  page.append(el("footer", { class: "footer" },
    "Ticker Tutor is an educational tool, not financial advice, and nothing here is a recommendation to buy or sell. ",
    "Past results don't guarantee future returns, and backtests have limits (",
    el("a", { href: "#/learn?section=limits" }, "see Learn"), ")."));
  if (y) window.scrollTo(0, y);
}

boot();
