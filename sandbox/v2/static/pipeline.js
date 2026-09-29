/* Pipeline page: กล่อง A→B→C→เงื่อนไข, เส้น flow + อนุภาค, Monaco, preflight, RUN + SSE progress */
"use strict";

// object ที่ไม่ควรถูก Alpine ทำ reactive proxy (Monaco จะค้างถ้าถูกห่อ) เก็บไว้นอก component
const LAB = { editor: null, es: null };

const STEP_LIST = [["load", "โหลดข้อมูล"], ["A", "A"], ["B", "B"], ["C", "C"], ["condition", "เงื่อนไข"], ["simulate", "จำลอง"], ["metrics", "metrics"]];
const WIRE_COLORS = ["#10B981", "#A855F7", "#F59E0B"];

function pipeline() {
  return {
    stages: {
      A: { mode: "on", version: null, ranking: "global", n: null, nTouched: false },
      B: { mode: "off", version: null },
      C: { mode: "off", version: null },
    },
    scope: { mode: "all", sectors: [], tickers: [] }, scopeQ: "", scopeHi: 0, scopeInfo: null, boxStats: null, warmup: null, effective: null, stale: false,
    condId: "equal_weight_A", condDesc: "", source: "", dirty: false,
    run: { start: "", end: "", capital: 1000000, costPct: 0.1, heldOut: false, confirm: "", includeManual: false, name: "" },
    warnings: [], error: "", validation: null, validating: false,
    job: null, logs: [], running: false, funnel: null,
    wires: [], particles: [], activeStage: null, stepList: STEP_LIST,
    _ignore: false, _pf: null, _raf: null, _cycle: null,

    init() {
      const ready = () => this.setup();
      if (Alpine.store("app").registry) ready(); else window.addEventListener("app-ready", ready, { once: true });
      window.addEventListener("resize", () => this.drawWires());
      window.addEventListener("route", (e) => { if (e.detail.name === "pipeline") setTimeout(() => { this.drawWires(); LAB.editor && LAB.editor.layout(); }, 30); });
      window.addEventListener("shortcut-run", () => this.runNow());
      window.addEventListener("registry-updated", () => this.fixVersions());
    },
    async setup() {
      const meta = Alpine.store("app").meta;
      this.run.start = meta.config.decision_start; this.run.end = meta.config.default_end;  // เริ่มซื้อขายที่รอบ rebalance ของ A
      this.run.capital = meta.config.capital; this.run.costPct = meta.config.cost * 100;
      this.fixVersions();
      await this.loadCondition();
      this.initEditor();
      await this.$nextTick();
      this.drawWires();
      this.preflight();
      const last = localStorage.getItem("v2.lastJob");
      if (last) {
        try {
          const j = await api(`/api/jobs/${last}`);
          this.job = j; this.logs = j.logs || [];
          Alpine.store("app").job = j;
          if (["queued", "running"].includes(j.status)) this.follow(last);
          else if (j.status === "done") this.loadFunnel(last);
        } catch (e) { localStorage.removeItem("v2.lastJob"); }
      }
    },
    fixVersions() {
      const reg = Alpine.store("app").registry;
      const pref = { A: "A:A1_r001_Q_LOWACC_overall", B: "B:stub", C: "C:rulebase-exp03" };
      for (const m of ["A", "B", "C"]) {
        const vs = reg.models[m] || [];
        if (!vs.some((v) => v.id === this.stages[m].version)) this.stages[m].version = (vs.find((v) => v.id === pref[m]) || vs[0] || {}).id || null;
      }
    },
    versions(m) { return (Alpine.store("app").registry?.models?.[m]) || []; },
    vmeta(m) { return this.versions(m).find((v) => v.id === this.stages[m].version) || null; },
    setMode(m, mode) { this.stages[m].mode = mode; this.changed(); this.$nextTick(() => this.drawWires()); },
    changed() { clearTimeout(this._pf); this._pf = setTimeout(() => this.preflight(), 350); },

    statusOf(m) {
      const v = this.vmeta(m);
      if (this.stages[m].mode === "off") return { cls: "stub", text: "ปิด (bypass) — ส่งหุ้นทั้งหมดต่อ" };
      if (!v) return { cls: "none", text: "ไม่มีข้อมูล — ไม่พบ version ใน registry" };
      const s = new Date(this.run.start), e = new Date(this.run.end);
      if (!v.coverage.start) return { cls: "none", text: "ยังไม่มีข้อมูล (version นี้ว่าง)" };
      const cs = new Date(v.coverage.start), ce = new Date(v.coverage.valid_through || v.coverage.end);
      const cov = `coverage ${v.coverage.start} → ${v.coverage.valid_through || v.coverage.end}`;
      if (ce < s || cs > e) return { cls: "none", text: `ไม่มีข้อมูลในช่วงที่เลือก (${cov})` };
      if (v.result_badge === "stub") return { cls: "stub", text: `STUB · ${cov}` };
      const gaps = [];
      if (cs > s) gaps.push(`ขาด ${this.run.start} → ${v.coverage.start}`);
      if (ce < e) gaps.push(`ขาด ${v.coverage.valid_through || v.coverage.end} → ${this.run.end}`);
      if (gaps.length) return { cls: "partial", text: `coverage บางส่วน: ${gaps.join(", ")}` };
      return { cls: "ready", text: `พร้อม · ${cov}` };
    },

    config() {
      const src = LAB.editor ? LAB.editor.getValue() : this.source;
      return {
        name: this.run.name, start: this.run.start, end: this.run.end, capital: this.run.capital, cost: this.run.costPct / 100,
        held_out: { enabled: this.run.heldOut, confirm: this.run.confirm }, include_manual: this.run.includeManual,
        scope: { mode: this.scope.mode, sectors: [...this.scope.sectors], tickers: [...this.scope.tickers] },
        stages: {
          A: { mode: this.stages.A.mode, version: this.stages.A.version,
               ...(this.stages.A.ranking !== "global" ? { ranking: this.stages.A.ranking } : {}),
               ...(this.stages.A.ranking === "scoped_fixed_n" ? { n: this.fixedN() } : {}) },
          B: { mode: this.stages.B.mode, version: this.stages.B.version },
          C: { mode: this.stages.C.mode, version: this.stages.C.version },
        },
        condition: this.dirty ? { id: null, source: src } : { id: this.condId },
      };
    },
    async preflight() {
      const body = this.config();
      if (this.touchesHeldOut() && !(this.run.heldOut && this.run.confirm.trim() === Alpine.store("app").meta.config.confirm_text)) {
        body.end = Alpine.store("app").meta.config.default_end;  // ตรวจส่วนอื่นก่อน — held-out จะถูกเช็คจริงตอน RUN
      }
      try {
        const r = await api("/api/preflight", { method: "POST", body });
        this.warnings = r.warnings; this.error = ""; this.scopeInfo = r.scope; this.boxStats = r.box_stats || null; this.warmup = r.warmup || null;
        this.effective = r.effective || null;
      } catch (e) { this.error = e.message; this.scopeInfo = null; this.boxStats = null; this.effective = null; if (e.data?.kind === "stale_page") this.stale = true; }
    },
    /* ตัวเลขบนกล่อง: หลังรัน = เฉลี่ยต่อวันจาก funnel · ก่อนรัน = ณ วันสุดท้ายของช่วง (จาก preflight) — ไว้ดู ไม่ใช่ไว้กด */
    passText(m) {
      if (this.funnel) return `ผ่าน ${fmtN(this.funnel["after_" + m])} ตัว (เฉลี่ยต่อวัน)`;
      const s = this.boxStats?.[m];
      return s ? `ผ่าน ${fmtN(s.pass)} ตัว · ณ ${this.boxStats.date}` : "";
    },
    distText(m) {
      const d = this.boxStats?.[m]?.dist;
      if (!d) return "";
      const lab = m === "C" ? "sector ของหุ้น: " : "";
      return lab + `positive ${d.positive} · neutral ${d.neutral} · negative ${d.negative} · ไม่มีข้อมูล ${d.none}`;
    },

    /* ---------- ขอบเขตการลงทุน (ก่อนกล่อง A) ---------- */
    setScope(mode) { this.scope.mode = mode; this.changed(); },
    sectorList() {
      const meta = Alpine.store("app").meta, cnt = {};
      if (!meta) return [];
      for (const t of meta.tickers) if (t.kind === "stock") { const e = meta.sector_etfs[t.sector]; if (e) cnt[e] = (cnt[e] || 0) + 1; }
      return ["XLK", "XLC", "XLY", "XLP", "XLF", "XLV", "XLI", "XLE", "XLB", "XLRE", "XLU"].map((e) => ({
        e, n: cnt[e] || 0, name: Object.keys(meta.sector_etfs).find((k) => meta.sector_etfs[k] === e) || e }));
    },
    toggleSector(e) {
      const s = this.scope.sectors;
      this.scope.sectors = s.includes(e) ? s.filter((x) => x !== e) : [...s, e].sort();
      this.changed();
    },
    get scopeHits() { return searchTickers(this.scopeQ || "", 8).filter((h) => h.kind === "stock" && !this.scope.tickers.includes(h.t)); },
    addScopeTicker(h) { if (h && !this.scope.tickers.includes(h.t)) this.scope.tickers = [...this.scope.tickers, h.t]; this.scopeQ = ""; this.scopeHi = 0; this.changed(); },
    removeScopeTicker(t) { this.scope.tickers = this.scope.tickers.filter((x) => x !== t); this.changed(); },
    scopeKey(e) {
      const hits = this.scopeHits;
      if (e.key === "ArrowDown") { e.preventDefault(); this.scopeHi = Math.min(this.scopeHi + 1, hits.length - 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); this.scopeHi = Math.max(this.scopeHi - 1, 0); }
      else if ((e.key === "Enter" || e.key === "Tab") && hits.length && this.scopeQ) { e.preventDefault(); this.addScopeTicker(hits[this.scopeHi]); }
      else if (e.key === "Backspace" && !this.scopeQ && this.scope.tickers.length) this.removeScopeTicker(this.scope.tickers[this.scope.tickers.length - 1]);
    },
    scopeProblem() {
      if (this.scope.mode === "sectors" && !this.scope.sectors.length) return "เลือกอย่างน้อย 1 sector";
      if (this.scope.mode === "tickers" && !this.scope.tickers.length) return "เลือกหุ้นอย่างน้อย 1 ตัว (พิมพ์ @ หรือชื่อบริษัท)";
      return "";
    },
    scopeSummary() {
      if (this.scopeProblem()) return this.scopeProblem();
      const i = this.scopeInfo;
      if (this.scope.mode === "all") return "ทั้งตลาด — หุ้นทุกตัวใน universe";
      return i && i.n_members ? `${i.label} → ${i.n_members} ตัว` : "กำลังตรวจ…";
    },
    warnTag(w) {
      if (w.startsWith("SURVIVORSHIP")) return "SURVIVORSHIP";
      if (w.startsWith("SCOPED-A")) return "โหมดทดสอบ";
      if (/(^|: )ORACLE:/.test(w)) return "ORACLE";
      if (w.startsWith("LEGACY")) return "LEGACY";
      if (/(^|: )MANUAL:/.test(w)) return "MANUAL";
      if (/STUB/.test(w)) return "STUB";
      if (/NEGATIVE|0\/216/.test(w)) return "NEGATIVE";
      if (/ไม่มีข้อมูล|เหตุการณ์แรก|เหตุการณ์สุดท้าย|รอบแรก/.test(w)) return "COVERAGE";
      if (/test set|look-ahead/.test(w)) return "CAVEAT";
      return "NOTE";
    },
    warnClass(w) { return { STUB: "gray", NEGATIVE: "orange", CAVEAT: "orange", COVERAGE: "", SURVIVORSHIP: "", NOTE: "gray", ORACLE: "oracle", LEGACY: "orange", MANUAL: "gray", "โหมดทดสอบ": "scoped" }[this.warnTag(w)]; },
    scopedA() { return this.stages.A.mode === "on" && this.stages.A.ranking !== "global"; },
    defaultN() { return Math.max(1, Math.round(this.vmeta("A")?.coverage?.avg_selected || 20)); },  // จำนวนที่กฎเลือกจริงต่อรอบ
    fixedN() { return isNum(this.stages.A.n) && this.stages.A.n >= 1 ? Math.round(this.stages.A.n) : this.defaultN(); },
    setRanking(v) { this.stages.A.ranking = v; if (v === "scoped_fixed_n" && !this.stages.A.nTouched) this.stages.A.n = this.defaultN(); this.changed(); },
    versionChanged(m) {  // N เริ่มต้นตามจำนวนที่กฎของ version ใหม่เลือกจริง — ถ้าผู้ใช้ยังไม่ได้แก้ N เอง
      if (m === "A" && this.stages.A.ranking === "scoped_fixed_n" && !this.stages.A.nTouched) this.stages.A.n = this.defaultN();
      this.changed();
    },
    effectiveText() {  // สิ่งที่ server รับไปแล้วจะรันจริง (จาก preflight) — ไม่ใช่สิ่งที่หน้าเว็บคิดว่าตั้งไว้
      const e = this.effective;
      if (!e) return "";
      const rk = { global: "ทั้งตลาด", scoped: "จัดอันดับใน scope (คงสัดส่วน · ทดสอบ)", scoped_fixed_n: `Top-${e.n} คงที่ใน scope (ทดสอบ)` }[e.ranking] || "—";
      const sc = e.scope === "all" ? "ทั้งตลาด" : (e.scope === "sectors" ? "sector " + e.sectors.join(" ") : "หุ้น " + e.tickers.slice(0, 6).join(" ") + (e.tickers.length > 6 ? " …" : ""));
      return `จะรัน: A ${e.A || "ปิด"}${e.A ? " · การจัดอันดับ " + rk : ""} · ขอบเขต ${sc} · B ${e.B || "ปิด"} · C ${e.C || "ปิด"} · เงื่อนไข ${e.condition}`;
    },

    /* ---------- condition / editor ---------- */
    async loadCondition() {
      const c = (Alpine.store("app").registry.conditions || []).find((x) => x.id === this.condId);
      this.condDesc = c ? c.description : "";
      const r = await api(`/api/conditions/${this.condId}`);
      this.source = r.source; this.dirty = false; this.validation = null;
      if (LAB.editor) { this._ignore = true; LAB.editor.setValue(r.source); this._ignore = false; }
    },
    initEditor() {
      if (!Alpine.store("app").meta.vendor.monaco || LAB.editor) return;
      const s = document.createElement("script");
      s.src = "/static/vendor/monaco/vs/loader.js";
      s.onload = () => {
        window.require.config({ paths: { vs: "/static/vendor/monaco/vs" } });
        window.require(["vs/editor/editor.main"], () => {
          monaco.editor.defineTheme("lab", { base: "vs-dark", inherit: true, rules: [{ token: "comment", foreground: "6F7BA3" }, { token: "string", foreground: "FDE68A" }, { token: "keyword", foreground: "C084FC" }],
            colors: { "editor.background": "#0A0F1D", "editorLineNumber.foreground": "#3A4668", "editor.lineHighlightBackground": "#121A30" } });
          LAB.editor = monaco.editor.create(this.$refs.editor, { value: this.source, language: "python", theme: "lab", fontFamily: "JB Mono, monospace", fontSize: 13, minimap: { enabled: false }, automaticLayout: true, scrollBeyondLastLine: false, tabSize: 4 });
          LAB.editor.onDidChangeModelContent(() => { if (!this._ignore) { this.dirty = true; } });
          const items = [
            ["date", "วันที่ตัดสินใจ 'YYYY-MM-DD'"], ["universe", "list ticker ที่ผ่านกล่องที่เปิดทั้งหมด"], ["a", "dict ticker → สัญญาณ A {class, score, weight, reasons, date}"],
            ["b", "dict ticker → สัญญาณ B ล่าสุด (ภายในอายุ) · ข่าว manual มี label -2..+2 (ความแรง) + class 3 กลุ่ม"], ["c", "dict sector ETF/GICS → สัญญาณ C"], ["c_for(ticker)", "สัญญาณ C ของ sector ของหุ้น"],
            ["sector_of(ticker)", "GICS sector"], ["etf_of(ticker)", "sector ETF"], ["price(ticker)", "Adj Close ล่าสุด ≤ วันนี้"],
            ["history(ticker, lookback_days=60, field='adj')", "pd.Series ราคาย้อนหลัง (ห้ามเกิน ctx.date)"], ["portfolio", "{value, cash, cash_weight, weights, units}"],
            ["state", "dict จำค่าข้ามวัน"], ["stage_enabled", "{A,B,C: bool}"], ["note(ticker, text)", "แนบเหตุผลเข้า trade"],
          ];
          monaco.languages.registerCompletionItemProvider("python", {
            triggerCharacters: ["."],
            provideCompletionItems: (model, pos) => {
              const line = model.getLineContent(pos.lineNumber).slice(0, pos.column - 1);
              if (!/ctx\.\w*$/.test(line)) return { suggestions: [] };
              const w = model.getWordUntilPosition(pos);
              const range = { startLineNumber: pos.lineNumber, endLineNumber: pos.lineNumber, startColumn: w.startColumn, endColumn: w.endColumn };
              return { suggestions: items.map(([k, d]) => ({ label: k, kind: monaco.languages.CompletionItemKind.Property, insertText: k.split("(")[0] + (k.includes("(") ? "(" : ""), detail: d, range })) };
            },
          });
        });
      };
      document.head.appendChild(s);
    },
    async validate() {
      this.validating = true; this.validation = null;
      try {
        const body = { config: { ...this.config(), condition: { id: this.dirty ? null : this.condId, source: LAB.editor ? LAB.editor.getValue() : this.source } }, date: this.run.end };
        if (this.touchesHeldOut() && !this.run.heldOut) body.date = Alpine.store("app").meta.config.default_end, body.config.end = body.date;
        this.validation = await api("/api/validate", { method: "POST", body });
        if (this.validation.ok && this.validation.funnel) this.funnel = { ...this.validation.funnel, held: this.validation.weights ? Object.keys(this.validation.weights).length : 0 };
        this.drawWires();
      } catch (e) { this.validation = { ok: false, error: e.message }; }
      this.validating = false;
    },
    async saveAsNew() {
      const id = prompt("ชื่อไฟล์ condition ใหม่ (a-z, 0-9, _) — ห้ามซ้ำกับของเดิม", this.condId + "_v2");
      if (!id) return;
      try {
        await api("/api/conditions", { method: "POST", body: { id, source: LAB.editor ? LAB.editor.getValue() : this.source } });
        await Alpine.store("app").rescan();
        this.condId = id; await this.loadCondition();
        Alpine.store("app").toast(`บันทึก condition ${id} แล้ว`);
      } catch (e) { Alpine.store("app").toast(e.message, "err", 6000); }
    },

    /* ---------- timeline ---------- */
    tlPos(d) {
      const m = Alpine.store("app").meta;
      if (!m || !d) return 0;
      const a = +new Date(m.config.data_start), b = +new Date(m.latest_trading_day);
      return Math.max(0, Math.min(100, (+new Date(d) - a) / (b - a) * 100));
    },
    tlYears() {
      const m = Alpine.store("app").meta;
      if (!m) return [];
      const y0 = +m.config.data_start.slice(0, 4) + 1, y1 = +m.latest_trading_day.slice(0, 4);
      const out = []; for (let y = y0; y <= y1; y++) out.push(y); return out;
    },
    startText() {
      const w = this.warmup, sd = Alpine.store("app").meta?.config?.start_dates;
      const trade = `เริ่มซื้อขายจริง: ${this.run.start}` + (sd && this.run.start === sd.decision_start ? ` (รอบ rebalance ของ ${sd.anchor.split("_")[0]})` : "");
      if (!w) return trade;
      return (w.days ? `ราคาเริ่มมี: ${w.start} (warm-up indicator ${w.days} วันทำการ — ไม่ซื้อขาย ไม่นับในผล) · ` : "ไม่มี warm-up · ") + trade;
    },
    touchesHeldOut() { const m = Alpine.store("app").meta; return m && this.run.end >= m.config.held_out_start; },

    /* ---------- run ---------- */
    async runNow() {
      if (this.running) return;
      if (this.scopeProblem()) { this.error = "ขอบเขต: " + this.scopeProblem(); Alpine.store("app").toast(this.error, "err", 5000); return; }
      try {
        const r = await api("/api/jobs", { method: "POST", body: this.config() });
        this.warnings = r.warnings; this.error = ""; this.effective = r.effective || this.effective;
        this.logs = []; this.funnel = null;
        this.job = { id: r.id, status: "queued", stage: "load", pct: 0 };
        localStorage.setItem("v2.lastJob", r.id);
        this.follow(r.id);
      } catch (e) {
        this.error = e.message;
        if (e.data?.kind === "stale_page") this.stale = true;
        Alpine.store("app").toast(e.status === 403 ? "held-out: ต้องเปิด toggle + พิมพ์ยืนยัน" : e.message, "err", 6000);
      }
    },
    follow(id) {
      this.running = true; this.startParticles();
      if (LAB.es) LAB.es.close();
      const es = new EventSource(`/api/jobs/${id}/stream`);
      LAB.es = es;
      es.onmessage = (ev) => {
        const d = JSON.parse(ev.data);
        const newLogs = d.logs || []; delete d.logs;
        this.job = d; Alpine.store("app").job = d;
        if (newLogs.length) { this.logs = this.logs.concat(newLogs).slice(-400); this.$nextTick(() => { const el = this.$refs.log; if (el) el.scrollTop = el.scrollHeight; }); }
        if (!["queued", "running"].includes(d.status)) this.finish(d);
      };
      es.onerror = () => { es.close(); setTimeout(async () => { const d = await api(`/api/jobs/${id}`); if (["queued", "running"].includes(d.status)) this.follow(id); else { this.job = d; this.finish(d); } }, 1000); };
    },
    finish(d) {
      if (LAB.es) LAB.es.close();
      this.running = false; this.stopParticles(); Alpine.store("app").job = d;
      if (d.status === "done") { Alpine.store("app").toast("รันเสร็จ — ดูผลลัพธ์ได้แล้ว"); this.loadFunnel(d.id); }
      else if (d.status === "failed") Alpine.store("app").toast("รันไม่สำเร็จ: " + (d.error || ""), "err", 7000);
    },
    async loadFunnel(id) {
      try {
        const r = await api(`/api/results/run/${id}`);
        this.funnel = r.metrics.funnel_avg;
        this.drawWires();
      } catch (e) { /* ignore */ }
    },
    async cancel() { if (this.job) await api(`/api/jobs/${this.job.id}/cancel`, { method: "POST" }); },
    stepClass(s) {
      if (!this.job) return "";
      const idx = STEP_LIST.findIndex((x) => x[0] === s), cur = STEP_LIST.findIndex((x) => x[0] === this.job.stage);
      if (this.job.status === "done" || idx < cur || (this.job.stage === "save" && idx <= STEP_LIST.length)) return "done";
      return idx === cur ? "now" : "";
    },
    stepIcon(s) { const c = this.stepClass(s); return c === "done" ? "✓" : c === "now" ? "◉" : "○"; },

    /* ---------- wires + particles ---------- */
    drawWires() {
      const cv = this.$refs.canvas;
      if (!cv || !cv.offsetWidth) return;
      const base = cv.getBoundingClientRect();
      const box = (k) => cv.querySelector(`[data-box="${k}"]`)?.getBoundingClientRect();
      const seq = ["A", "B", "C", "G"], out = [];
      const f = this.funnel;
      const labels = f ? [fmtN(f.after_A), fmtN(f.after_B), fmtN(f.after_C)] : ["", "", ""];
      for (let i = 0; i < 3; i++) {
        const a = box(seq[i]), b = box(seq[i + 1]);
        if (!a || !b) continue;
        const x1 = a.right - base.left, y1 = a.top - base.top + a.height * 0.42, x2 = b.left - base.left, y2 = b.top - base.top + b.height * 0.42;
        const dx = (x2 - x1) * 0.55;
        out.push({ id: i, d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`, mx: (x1 + x2) / 2, my: (y1 + y2) / 2, label: labels[i] });
      }
      this.wires = out;
      const aBox = box("A");
      if (f && aBox) this.wires.push({ id: 9, d: "", mx: aBox.left - base.left + aBox.width / 2, my: aBox.top - base.top - 2,
        label: `${f.market !== undefined ? "ขอบเขต" : "universe"} ${fmtN(f.universe)} →` });
    },
    wireSvg() {
      const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
      return this.wires.map((w) => (w.d ? `<path class="wire${this.running ? " live" : ""}" d="${w.d}"></path>` : "")
        + (w.label ? `<text x="${w.mx}" y="${w.my - 10}" text-anchor="middle">${esc(w.label)}</text>` : "")).join("");
    },
    particleSvg() {
      return this.particles.map((p) => `<circle class="particle" r="3.2" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" fill="${p.color}" style="color:${p.color}"></circle>`).join("");
    },
    startParticles() {
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const N = 7;
      this._parts = [];
      for (let w = 0; w < 3; w++) for (let k = 0; k < N; k++) this._parts.push({ id: `${w}-${k}`, w, t: k / N, color: WIRE_COLORS[w] });
      const tick = () => {
        const paths = this.$refs.svg ? this.$refs.svg.querySelectorAll("path.wire") : [];
        const ps = [];
        for (const p of this._parts) {
          p.t = (p.t + 0.006) % 1;
          const el = paths[p.w];
          if (!el) continue;
          const L = el.getTotalLength(), pt = el.getPointAtLength(p.t * L);
          ps.push({ id: p.id, x: pt.x, y: pt.y, color: p.color });
        }
        this.particles = ps;
        this._raf = requestAnimationFrame(tick);
      };
      this._raf = requestAnimationFrame(tick);
      const order = ["A", "B", "C", "condition"]; let i = 0;
      this._cycle = setInterval(() => {
        const st = this.job?.stage;
        this.activeStage = st === "simulate" ? order[i++ % 4] : (["A", "B", "C"].includes(st) ? st : (st === "condition" ? "condition" : null));
      }, 420);
    },
    stopParticles() { cancelAnimationFrame(this._raf); clearInterval(this._cycle); this.particles = []; this.activeStage = null; },
  };
}
