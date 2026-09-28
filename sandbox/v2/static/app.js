/* Pipeline Lab — core: API, store, router, formatting, palette, shortcuts */
"use strict";

async function api(path, opts = {}) {
  const o = { headers: {}, ...opts };
  if (o.body && typeof o.body !== "string") { o.body = JSON.stringify(o.body); o.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, o);
  let data = null;
  try { data = await r.json(); } catch (e) { data = null; }
  if (!r.ok) { const err = new Error((data && data.error) || `HTTP ${r.status}`); err.status = r.status; err.data = data; throw err; }
  return data;
}

/* ---------- formatting (ใช้ใน template ได้โดยตรง) ---------- */
const isNum = (x) => typeof x === "number" && isFinite(x);
function fmtPct(x, d = 2) { return isNum(x) ? (x * 100).toFixed(d) + "%" : "—"; }
function fmtPctS(x, d = 2) { return isNum(x) ? (x >= 0 ? "+" : "") + (x * 100).toFixed(d) + "%" : "—"; }
function fmtNum(x, d = 2) { return isNum(x) ? x.toFixed(d) : "—"; }
/* label ข่าว manual 5 ระดับ -2..+2 (ข้อความจาก /api/meta) — ค่าหลัก ไม่ยุบเหลือ positive/neutral/negative */
function newsLabels() { return (window.Alpine && Alpine.store("app").meta?.news_labels) || []; }
function newsLabelOf(n) { return isNum(n?.label) ? n.label : ({ positive: 1, neutral: 0, negative: -1 }[n?.sentiment] ?? 0); }
function labelTag(v) { const t = (newsLabels().find((x) => x[0] === v) || [v, ""])[1]; return `${v > 0 ? "+" : ""}${v} ${t}`.trim(); }
function labelCls(v) { return v >= 2 ? "pos strong" : v >= 1 ? "pos" : v <= -2 ? "neg strong" : v <= -1 ? "neg" : "dim"; }
/* badge ของ version/ผลลัพธ์ — badge ที่ไม่ใช่ REAL ต้องมีคำอธิบายเสมอ (hover หรือ (?)) */
const BADGE_INFO = {
  real: ["REAL", ""],
  stub: ["STUB", "STUB = ยังไม่มีผลวิเคราะห์จริง ระบบสุ่มค่าเพื่อทดสอบว่า pipeline เดินได้ครบเท่านั้น ห้ามใช้ตัดสินใจลงทุนจริง"],
  negative: ["NEGATIVE", "NEGATIVE = โมเดลนี้ทดสอบแล้วไม่ผ่าน (negative result) ยังเปิดให้ใช้เพื่อทดสอบระบบ/เปรียบเทียบ ไม่ใช่สัญญาณที่เชื่อถือได้"],
  manual: ["MANUAL", "MANUAL = มาจาก label ที่ผู้ใช้/Claude ระบุไว้ในข่าว manual ไม่ใช่โมเดลที่เทรน (label ณ วันข่าว ไม่รู้ผลราคาล่วงหน้า)"],
  oracle: ["ORACLE", "Oracle test — label รู้ผลราคาจริงล่วงหน้าแล้ว ใช้หาเพดานบนว่า B ที่แม่นสมบูรณ์จะช่วยได้แค่ไหน ผลตอบแทนที่ได้ไม่ใช่สิ่งที่ทำได้จริง ห้ามอ้างเป็นผลจริง"],
  held_out: ["HELD-OUT", "ผลนี้แตะช่วง held-out แล้ว — ห้ามใช้ผลนี้ย้อนไปปรับเงื่อนไข (ธงนี้ถาวร)"],
  survivorship: ["SURVIVORSHIP", "A ปิด → universe = หุ้น S&P 500 ปัจจุบัน (รอดมาถึงวันนี้) ผลจะดีเกินจริง"],
  legacy: ["LEGACY", "ผลนี้บันทึกด้วยกล่องแบบเดิม (มีเกณฑ์กรองในกล่อง) — เปิดดูได้ตามเดิม แต่ Re-run จะใช้ความหมายใหม่"],
};
const SCOPED_A_WARNING = "โหมดทดสอบ: จัดอันดับใหม่เฉพาะในขอบเขตที่เลือก — ไม่ใช่พฤติกรรมจริงของกฎที่ผ่านการทดสอบ (backtest เดิมของ Model A ทดสอบด้วยการจัดอันดับทั้งตลาดเท่านั้น) ผลจากโหมดนี้ใช้ดูกลไกระบบเท่านั้น ห้ามอ้างเป็นผลการทดสอบของ Model A";
/* badge ของผลการทดลอง (experiments_store.badges) — kind "manual" = เปิด toggle รวมข่าว manual */
const RESULT_BADGE_TIPS = {
  held_out: BADGE_INFO.held_out[1], stub: BADGE_INFO.stub[1], negative: BADGE_INFO.negative[1], survivorship: BADGE_INFO.survivorship[1],
  manual: "รวมข่าวที่ผู้ใช้พิมพ์/นำเข้าเอง (source=manual) ผ่าน toggle — ไม่ใช่ output ของโมเดล",
  manual_labels: BADGE_INFO.manual[1], oracle: BADGE_INFO.oracle[1], legacy: BADGE_INFO.legacy[1],
  scoped_a: SCOPED_A_WARNING,
};
function resultBadgeTip(k) { return RESULT_BADGE_TIPS[k] || ""; }
function badgeLabel(b) { return (BADGE_INFO[b] || [String(b || "").toUpperCase()])[0]; }
function badgeTip(b) { return (BADGE_INFO[b] || ["", ""])[1]; }
const LABEL_COLORS = { "-2": "#EF4444", "-1": "#FCA5A5", "0": "#94A3B8", "1": "#86EFAC", "2": "#22C55E" };
function fmtN(x) { return isNum(x) ? Math.round(x).toLocaleString("en-US") : "—"; }
function fmtMoney(x) { return isNum(x) ? (x < 0 ? "−" : "") + Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—"; }
function chipKind(c) {
  const s = String(c);
  if (s.includes("[MANUAL]") || s.startsWith("MANUAL")) return "manual";
  if (s.startsWith("A:")) return "A";
  if (s.startsWith("B:")) return "B";
  if (s.startsWith("C:")) return "C";
  if (s.startsWith("condition")) return "cond";
  if (s.startsWith("system")) return "sys";
  return "";
}
function stockHref(t, date) {
  const r = Alpine.store("app").route;
  let q = `#/stock/${t}`;
  const p = [];
  if (r.name === "results") p.push(`kind=${r.params.kind}`, `id=${r.params.id}`);
  if (date) p.push(`date=${date}`);
  return q + (p.length ? "?" + p.join("&") : "");
}
function thaiDuration(sec) {
  if (!isNum(sec)) return "กำลังประเมินเวลา…";
  sec = Math.max(0, Math.round(sec));
  if (sec < 1) return "ใกล้เสร็จ";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const parts = [];
  if (h) parts.push(`${h} ชั่วโมง`);
  if (m) parts.push(`${m} นาที`);
  if (s && !h) parts.push(`${s} วินาที`);
  return "เหลืออีกประมาณ " + parts.join(" ");
}

/* Plotly theme */
const PL = {
  layout(extra = {}) {
    return Object.assign({
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Plex Thai, system-ui", color: "#A9B4D6", size: 12 },
      margin: { l: 56, r: 16, t: 10, b: 36 },
      xaxis: { gridcolor: "rgba(120,150,220,.10)", zerolinecolor: "rgba(120,150,220,.2)" },
      yaxis: { gridcolor: "rgba(120,150,220,.10)", zerolinecolor: "rgba(120,150,220,.2)" },
      legend: { orientation: "h", y: 1.08, x: 0 }, hovermode: "x unified",
      hoverlabel: { bgcolor: "#111829", bordercolor: "#3a4a78", font: { family: "JB Mono, monospace", color: "#E6ECFF" } },
    }, extra);
  },
  config: { displayModeBar: false, responsive: true },
  ok() { return !window.__noPlotly && window.Plotly; },
};

/* Plotly ที่ render ตอน section ยังซ่อนอยู่จะกว้างผิด → resize ทุกครั้งที่เปลี่ยนหน้า */
window.addEventListener("route", () => setTimeout(() => {
  if (!PL.ok()) return;
  document.querySelectorAll(".js-plotly-plot").forEach((el) => { if (el.offsetParent) Plotly.Plots.resize(el); });
}, 80));

/* ---------- store ---------- */
document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    meta: null,
    registry: null,
    route: { name: "pipeline", params: {}, query: {} },
    job: null,
    toasts: [],
    palette: { open: false, q: "", i: 0 },
    STAGES: { load: "โหลดข้อมูล", A: "Model A", B: "Model B", C: "Model C", condition: "เงื่อนไข", simulate: "จำลองการเทรด", metrics: "Metrics", save: "บันทึก" },

    async init() {
      this.parseRoute();
      window.addEventListener("hashchange", () => this.parseRoute());
      try {
        [this.meta, this.registry] = await Promise.all([api("/api/meta"), api("/api/registry")]);
      } catch (e) { this.toast("โหลดข้อมูลเริ่มต้นไม่ได้: " + e.message, "err"); }
      if (this.meta && !this.meta.vendor.plotly) this.toast("ไม่พบ Plotly — รัน python3 -m sandbox.v2.scripts.fetch_vendor", "err");
      window.dispatchEvent(new CustomEvent("app-ready"));
    },
    parseRoute() {
      const h = location.hash.replace(/^#\/?/, "") || "pipeline";
      const [path, qs] = h.split("?");
      const parts = path.split("/").filter(Boolean);
      const query = Object.fromEntries(new URLSearchParams(qs || ""));
      let name = parts[0] || "pipeline", params = {};
      if (name === "results") params = { kind: parts[1], id: parts[2] };
      if (name === "stock") params = { ticker: (parts[1] || "").toUpperCase() };
      this.route = { name, params, query };
      window.dispatchEvent(new CustomEvent("route", { detail: this.route }));
      window.scrollTo(0, 0);
    },
    async rescan() {
      this.registry = await api("/api/registry/rescan", { method: "POST" });
      const n = this.registry.invalid.length;
      this.toast(`Rescan เสร็จ — valid ${["A", "B", "C"].map((m) => this.registry.models[m].length).reduce((a, b) => a + b)} · invalid ${n}`, n ? "err" : "ok");
      window.dispatchEvent(new CustomEvent("registry-updated"));
    },
    stageLabel(s) { return this.STAGES[s] || s || ""; },
    etaText(s) { return thaiDuration(s); },
    toast(msg, kind = "ok", ms = 3800) {
      const id = Math.random().toString(36).slice(2);
      this.toasts.push({ id, msg, kind });
      setTimeout(() => { this.toasts = this.toasts.filter((t) => t.id !== id); }, ms);
    },
    onKey(e) {
      const tag = (e.target.tagName || "").toLowerCase();
      const typing = ["input", "textarea", "select"].includes(tag) || e.target.isContentEditable || e.target.closest?.(".monaco-editor");
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); this.palette = { open: !this.palette.open, q: "", i: 0 }; return; }
      if (e.key === "Escape") { this.palette.open = false; return; }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "r" || e.key === "R") { e.preventDefault(); location.hash = "#/pipeline"; window.dispatchEvent(new CustomEvent("shortcut-run")); }
      if (e.key === "s" || e.key === "S") { e.preventDefault(); window.dispatchEvent(new CustomEvent("shortcut-save")); }
      if (e.key === "/") { e.preventDefault(); location.hash = "#/stock"; setTimeout(() => window.dispatchEvent(new CustomEvent("focus-search")), 50); }
    },
    palItems() {
      const q = (this.palette.q || "").trim().toLowerCase();
      const cmds = [
        { label: "▶ Run pipeline", hint: "R", act: () => { location.hash = "#/pipeline"; window.dispatchEvent(new CustomEvent("shortcut-run")); } },
        { label: "Pipeline", act: () => (location.hash = "#/pipeline") },
        { label: "ผลการทดลอง (Gallery)", act: () => (location.hash = "#/gallery") },
        { label: "หุ้นรายตัว", hint: "/", act: () => (location.hash = "#/stock") },
        { label: "เพิ่มข่าว", act: () => (location.hash = "#/news") },
        { label: "Registry", act: () => (location.hash = "#/registry") },
        { label: "↻ Rescan registry", act: () => this.rescan() },
        { label: "About / Methodology", act: () => (location.hash = "#/about") },
      ];
      let items = cmds.filter((c) => !q || c.label.toLowerCase().includes(q));
      if (q && this.meta) {
        const hits = searchTickers(q, 6).map((t) => ({ label: `${t.t} — ${t.name}`, hint: t.sector, act: () => (location.hash = `#/stock/${t.t}`) }));
        items = items.concat(hits);
      }
      if (this.palette.i >= items.length) this.palette.i = Math.max(0, items.length - 1);
      return items;
    },
    palRun() {
      const it = this.palItems()[this.palette.i];
      this.palette.open = false;
      if (it) it.act();
    },
  });
  Alpine.store("app").init();
});

/* ค้นหา ticker/ชื่อบริษัทแบบ fuzzy เบา ๆ (prefix > substring > subsequence) */
function searchTickers(q, n = 8) {
  const meta = Alpine.store("app").meta;
  if (!meta) return [];
  q = q.toLowerCase().replace(/^@/, "");
  if (!q) return [];
  const out = [];
  for (const t of meta.tickers) {
    if (t.kind !== "stock" && t.kind !== "etf") continue;
    const tk = t.t.toLowerCase(), nm = (t.name || "").toLowerCase();
    let s = 0;
    if (tk === q) s = 100;
    else if (tk.startsWith(q)) s = 80 - tk.length;
    else if (nm.startsWith(q)) s = 60;
    else if (nm.includes(q)) s = 40;
    else if (tk.includes(q)) s = 35;
    else {
      let i = 0; for (const ch of nm) if (ch === q[i]) i++;
      if (i === q.length && q.length >= 3) s = 10;
    }
    if (s) out.push([s, t]);
  }
  return out.sort((a, b) => b[0] - a[0] || a[1].t.localeCompare(b[1].t)).slice(0, n).map((x) => x[1]);
}

const SECTOR_COLORS = {
  "Information Technology": "#60A5FA", "Communication Services": "#A78BFA", "Consumer Discretionary": "#F472B6",
  "Consumer Staples": "#34D399", "Financials": "#FBBF24", "Health Care": "#2DD4BF", "Industrials": "#94A3B8",
  "Energy": "#F97316", "Materials": "#A3E635", "Real Estate": "#FB7185", "Utilities": "#38BDF8", "Unknown": "#64748B",
};

/* count-up ของตัวเลขใน hero card */
function countUp(el, c) {
  if (!isNum(c.raw) || matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = c.v; return; }
  const t0 = performance.now(), dur = 900;
  const step = (now) => {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = c.fmt(c.raw * e);
    if (p < 1) requestAnimationFrame(step); else el.textContent = c.v;
  };
  requestAnimationFrame(step);
}

function celebrate() {
  if (window.confetti && !matchMedia("(prefers-reduced-motion: reduce)").matches)
    confetti({ particleCount: 90, spread: 70, origin: { y: 0.25 }, colors: ["#10B981", "#06B6D4", "#D946EF", "#F59E0B", "#FDE68A"] });
}

/* ---------- gallery / compare ---------- */
function gallery() {
  return {
    items: [], sel: [],
    init() {
      const load = () => { if (Alpine.store("app").route.name === "gallery") this.load(); };
      window.addEventListener("route", load);
      load();
    },
    async load() { this.items = await api("/api/experiments"); this.sel = this.sel.filter((id) => this.items.some((e) => e.id === id)); },
    toggle(id) { this.sel = this.sel.includes(id) ? this.sel.filter((x) => x !== id) : (this.sel.length >= 3 ? this.sel : [...this.sel, id]); },
    open(e) { location.hash = `#/results/exp/${e.id}`; },
    spark(v) {
      if (!v || v.length < 2) return "";
      const lo = Math.min(...v), hi = Math.max(...v), r = hi - lo || 1;
      return v.map((x, i) => `${i ? "L" : "M"}${(i / (v.length - 1) * 300).toFixed(1)},${(52 - (x - lo) / r * 48).toFixed(1)}`).join("");
    },
  };
}

function compare() {
  return {
    data: null,
    keys: [
      ["total_return", "Total return", fmtPct], ["cagr", "CAGR", fmtPct], ["volatility", "Volatility", fmtPct],
      ["sharpe", "Sharpe", fmtNum], ["sortino", "Sortino", fmtNum], ["max_dd", "Max drawdown", fmtPct], ["calmar", "Calmar", fmtNum],
      ["beta", "Beta vs SPY", fmtNum], ["alpha", "Alpha (ต่อปี)", fmtPct], ["n_trades", "จำนวน trade", fmtN],
      ["win_rate", "Win rate", fmtPct], ["avg_holding_days", "ถือเฉลี่ย (วัน)", (x) => fmtNum(x, 1)],
      ["turnover_annual", "Turnover ต่อปี", (x) => fmtNum(x, 2) + "×"], ["total_cost", "ค่าธรรมเนียมรวม", fmtMoney], ["exposure", "Exposure", fmtPct],
    ],
    init() {
      const load = () => { if (Alpine.store("app").route.name === "compare") this.load(); };
      window.addEventListener("route", load);
      load();
    },
    async load() {
      const ids = Alpine.store("app").route.query.ids || "";
      this.data = await api("/api/compare?ids=" + encodeURIComponent(ids));
      await this.$nextTick();
      if (!PL.ok()) return;
      const colors = ["#FDE68A", "#22D3EE", "#E879F9"];
      const tr = this.data.experiments.filter((e) => e.equity).map((e, i) => ({ x: e.equity.dates, y: e.equity.values, name: e.name, line: { color: colors[i], width: 2 } }));
      Plotly.react(this.$refs.chart, tr, PL.layout({ yaxis: { gridcolor: "rgba(120,150,220,.10)", tickformat: ".2f" } }), PL.config);
      setTimeout(() => Plotly.Plots.resize(this.$refs.chart), 60);
    },
  };
}
