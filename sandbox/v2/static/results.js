/* Results page: hero metrics, equity/drawdown/heatmap/sector/sankey, trade log, save / re-run / delete */
"use strict";

function results() {
  return {
    kind: null, id: null, r: null, loading: false, err: "", saveName: "",
    trades: { total: 0, offset: 0, rows: [] }, tq: "", tside: "",
    rerunning: false, rerunDiff: null,

    init() {
      const go = () => { const rt = Alpine.store("app").route; if (rt.name === "results") this.load(rt.params.kind, rt.params.id); };
      window.addEventListener("route", go);
      window.addEventListener("shortcut-save", () => { if (Alpine.store("app").route.name === "results" && this.kind === "run") this.save(); });
      if (Alpine.store("app").meta) go(); else window.addEventListener("app-ready", go, { once: true });
    },
    async load(kind, id) {
      if (this.kind === kind && this.id === id && this.r) { this.$nextTick(() => this.renderCharts()); return; }
      this.kind = kind; this.id = id; this.r = null; this.err = ""; this.loading = true; this.rerunDiff = null;
      try {
        this.r = await api(`/api/results/${kind}/${id}`);
        this.saveName = this.r.config?.name || "";
        this.loading = false;
        await this.$nextTick();
        this.renderCharts();
        if (this.r.has_artifacts) this.loadTrades(0);
      } catch (e) { this.err = e.message; this.loading = false; }
    },
    title() {
      if (!this.r) return "";
      if (this.kind === "run") return "ผลการรัน (ยังไม่บันทึก)";
      return this.r.name || this.r.config?.name || this.id;
    },
    badgeText(b) {
      return {
        held_out: "ผลนี้แตะช่วง held-out แล้ว — ห้ามใช้ผลนี้ย้อนไปปรับเงื่อนไข (ธงนี้ถาวร)",
        stub: "สัญญาณจาก STUB (สุ่ม deterministic) — ตัวเลขไม่มีความหมายทางการลงทุน",
        negative: "โมเดลนี้ผลทดสอบเป็น negative result (exp_03: 0/216 cells ผ่าน) — ใช้เพื่อทดสอบระบบ",
        survivorship: "A ไม่ได้กรอง → universe = หุ้น S&P 500 ปัจจุบัน (รอดมาถึงวันนี้) ผลจะดีเกินจริง",
        manual: "รวมข่าวที่ผู้ใช้พิมพ์เอง (source=manual) ไม่ใช่ output ของโมเดล",
      }[b.kind] || "";
    },
    ewLabel() { const sc = this.r?.metrics?.scope; return sc ? `EW ขอบเขต (${sc.ew_names} ตัว)` : "EW universe"; },
    scopeText() {
      const sc = this.r.config.scope, m = this.r.metrics.scope || {};
      const what = sc.mode === "sectors" ? `sector ${sc.sectors.join(", ")}` : `หุ้น ${sc.tickers.join(", ")}`;
      return `${what} — ${m.n_members ?? (sc.members || []).length} ตัวในขอบเขต (มีราคา ${m.n_priced ?? "?"} ตัว) · อันดับ A มาจากทั้ง universe แล้วค่อยกรอง · EW = EW ของหุ้นในขอบเขต · SPY = ตลาดรวม`;
    },
    heroCards() {
      const m = this.r?.metrics?.full;
      if (!m) return [];
      const s = m.strategy, spy = m.spy, ew = m.ew;
      const d = (a, b) => (isNum(a) && isNum(b) ? a - b : null);
      const card = (k, key, fmt, fmtD, good = 1) => {
        const raw = s[key];
        const dSpy = key in spy ? d(raw, spy[key]) : null, dEw = key in ew ? d(raw, ew[key]) : null;
        return { k, raw, fmt, v: fmt(raw), cls: good && isNum(raw) ? (raw * good >= 0 ? "pos" : "neg") : "",
          dSpy: dSpy === null ? null : dSpy * good, dEw: dEw === null ? null : dEw * good, dSpyTxt: fmtD(dSpy), dEwTxt: fmtD(dEw) };
      };
      return [
        card("Total return", "total_return", fmtPct, fmtPctS),
        card("CAGR", "cagr", fmtPct, fmtPctS),
        card("Sharpe", "sharpe", (x) => fmtNum(x), (x) => (isNum(x) ? (x >= 0 ? "+" : "") + x.toFixed(2) : "—")),
        card("Max drawdown", "max_dd", fmtPct, fmtPctS, 1),
        { k: "Win rate", raw: s.win_rate, fmt: fmtPct, v: fmtPct(s.win_rate), cls: "", dSpy: null, dEw: null },
        { k: "Trades", raw: s.n_trades, fmt: fmtN, v: fmtN(s.n_trades), cls: "", dSpy: null, dEw: null },
      ];
    },
    metricRows() {
      const m = this.r?.metrics?.full;
      if (!m) return [];
      const rows = [["total_return", "Total return", fmtPct], ["cagr", "CAGR", fmtPct], ["volatility", "Volatility", fmtPct], ["sharpe", "Sharpe", fmtNum],
        ["sortino", "Sortino", fmtNum], ["max_dd", "Max drawdown", fmtPct], ["peak", "DD peak", (x) => x || "—"], ["trough", "DD trough", (x) => x || "—"],
        ["recovery", "DD recovery", (x) => x || "ยังไม่ฟื้น"], ["calmar", "Calmar", fmtNum], ["beta", "Beta vs SPY", fmtNum], ["alpha", "Alpha ต่อปี", fmtPct],
        ["win_rate", "Win rate (round trip)", fmtPct], ["n_trades", "จำนวน trade", fmtN], ["n_round_trips", "round trip ที่ปิดแล้ว", fmtN],
        ["avg_holding_days", "ถือเฉลี่ย (วัน)", (x) => fmtNum(x, 1)], ["turnover_annual", "Turnover ต่อปี", (x) => (isNum(x) ? x.toFixed(2) + "×" : "—")],
        ["total_cost", "ค่าธรรมเนียมรวม", fmtMoney], ["exposure", "Exposure เฉลี่ย", fmtPct], ["avg_holdings", "จำนวนหุ้นถือเฉลี่ย", (x) => fmtNum(x, 1)]];
      return rows.map(([k, l, f]) => [l, f(m.strategy[k]), k in (m.spy || {}) ? f(m.spy[k]) : "", k in (m.ew || {}) ? f(m.ew[k]) : ""]);
    },
    heldOutShape() {
      const ho = Alpine.store("app").meta.config.held_out_start, end = this.r.config.end;
      if (end < ho) return [];
      return [{ type: "rect", xref: "x", yref: "paper", x0: ho, x1: end, y0: 0, y1: 1, fillcolor: "rgba(239,68,68,.12)", line: { width: 0 }, layer: "below" }];
    },
    renderCharts() {
      if (!this.r || !this.r.has_artifacts || !PL.ok()) return;
      const eq = this.r.equity, x = eq.map((e) => e.date);
      const annot = this.heldOutShape().length ? [{ x: Alpine.store("app").meta.config.held_out_start, y: 1, yref: "paper", text: "HELD-OUT", showarrow: false, font: { color: "#FCA5A5", size: 11 }, xanchor: "left" }] : [];
      Plotly.react(this.$refs.eq, [
        { x, y: eq.map((e) => e.spy), name: "SPY buy & hold", line: { color: "#60A5FA", width: 1.5 } },
        { x, y: eq.map((e) => e.ew), name: this.ewLabel(), line: { color: "#A78BFA", width: 1.5, dash: "dot" } },
        { x, y: eq.map((e) => e.strategy), name: "Strategy", line: { color: "#FDE68A", width: 2.4 } },
      ], PL.layout({ shapes: this.heldOutShape(), annotations: annot, yaxis: { gridcolor: "rgba(120,150,220,.10)", tickformat: ",.0f" } }), PL.config);
      Plotly.react(this.$refs.dd, [
        { x, y: eq.map((e) => e.dd_strategy), name: "Strategy", fill: "tozeroy", line: { color: "#F87171", width: 1.2 }, fillcolor: "rgba(248,113,113,.25)" },
        { x, y: eq.map((e) => e.dd_spy), name: "SPY", line: { color: "#60A5FA", width: 1 } },
      ], PL.layout({ shapes: this.heldOutShape(), yaxis: { tickformat: ".0%", gridcolor: "rgba(120,150,220,.10)" } }), PL.config);
      // heatmap รายเดือน
      const mr = this.r.metrics.monthly_returns || {};
      const years = [...new Set(Object.keys(mr).map((k) => k.slice(0, 4)))];
      const z = years.map((y) => Array.from({ length: 12 }, (_, i) => { const v = mr[`${y}-${String(i + 1).padStart(2, "0")}`]; return isNum(v) ? v : null; }));
      Plotly.react(this.$refs.heat, [{ type: "heatmap", z, x: ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."], y: years,
        zmid: 0, colorscale: [[0, "#B91C1C"], [0.5, "#111829"], [1, "#059669"]], text: z.map((r) => r.map((v) => (isNum(v) ? (v * 100).toFixed(1) + "%" : ""))),
        texttemplate: "%{text}", hovertemplate: "%{y} %{x}: %{text}<extra></extra>", showscale: false, xgap: 2, ygap: 2 }],
      PL.layout({ margin: { l: 44, r: 8, t: 6, b: 26 }, xaxis: { showgrid: false }, yaxis: { type: "category", autorange: "reversed", showgrid: false } }), PL.config);
      // sector stacked area
      const se = this.r.sector_exposure;
      Plotly.react(this.$refs.sector, Object.entries(se.series).map(([k, v]) => ({ x: se.dates, y: v, name: k, stackgroup: "one", line: { width: 0.5, color: SECTOR_COLORS[k] || "#64748B" } })),
        PL.layout({ yaxis: { tickformat: ".0%", gridcolor: "rgba(120,150,220,.10)" }, legend: { orientation: "h", y: -0.18, font: { size: 10.5 } }, margin: { l: 50, r: 10, t: 6, b: 60 } }), PL.config);
      this.renderSankey();
      setTimeout(() => [this.$refs.eq, this.$refs.dd, this.$refs.heat, this.$refs.sector, this.$refs.sankey].forEach((el) => el && el.offsetParent && Plotly.Plots.resize(el)), 60);
    },
    renderSankey() {
      // เฉพาะกล่องที่เปิด — กล่องที่ปิด (bypass) ไม่แสดงเป็น node
      const f = this.r.metrics.funnel_avg || {}, st = this.r.config.stages;
      const U = f.universe || 0, sc = this.r.config.scope;
      const first = !sc || sc.mode === "all" ? "ทั้งตลาด" : (sc.mode === "sectors" ? `ขอบเขต ${sc.sectors.join(" ")}` : `ขอบเขต ${sc.tickers.slice(0, 3).join(" ")}${sc.tickers.length > 3 ? "…" : ""}`);
      const seq = [[first, U, "#94A3B8", null]];
      const colors = { A: ["#10B981", "rgba(16,185,129,.45)"], B: ["#A855F7", "rgba(168,85,247,.45)"], C: ["#F97316", "rgba(249,115,22,.45)"] };
      for (const m of ["A", "B", "C"]) if (st[m].mode !== "off") seq.push([`ผ่าน ${m}${st[m].mode === "score-only" ? " (แนบคะแนน)" : ""}`, f["after_" + m], colors[m][0], colors[m][1], m]);
      const lastN = seq[seq.length - 1][1];
      const H = Math.min(f.held ?? 0, lastN);
      seq.push(["ถือจริง", H, "#EAB308", "rgba(234,179,8,.55)"]);
      const labels = [], nc = [], src = [], tgt = [], val = [], lc = [];
      seq.forEach((n) => { labels.push(`${n[0]} ${fmtN(n[1])}`); nc.push(n[2]); });
      for (let i = 1; i < seq.length; i++) {
        src.push(i - 1); tgt.push(i); val.push(Math.max(seq[i][1], 0.0001)); lc.push(seq[i][3]);
        const drop = seq[i - 1][1] - seq[i][1];
        if (drop > 0.5) {
          labels.push(i === seq.length - 1 ? `เงื่อนไขไม่ถือ ${fmtN(drop)}` : `ตัดโดย ${seq[i][4]} ${fmtN(drop)}`); nc.push("#334155");
          src.push(i - 1); tgt.push(labels.length - 1); val.push(drop); lc.push("rgba(100,116,139,.25)");
        }
      }
      Plotly.react(this.$refs.sankey, [{ type: "sankey", arrangement: "snap", node: { label: labels, pad: 16, thickness: 14, color: nc, line: { width: 0 } },
        link: { source: src, target: tgt, value: val, color: lc } }], PL.layout({ margin: { l: 6, r: 6, t: 6, b: 6 }, font: { size: 11.5, color: "#E6ECFF" } }), PL.config);
    },
    async loadTrades(offset) {
      if (!this.r?.has_artifacts) return;
      const q = new URLSearchParams({ q: this.tq, side: this.tside, offset: Math.max(0, offset), limit: 200 });
      this.trades = await api(`/api/results/${this.kind}/${this.id}/trades?${q}`);
    },
    async save() {
      try {
        const r = await api("/api/experiments", { method: "POST", body: { job_id: this.id, name: this.saveName } });
        celebrate();
        Alpine.store("app").toast("บันทึกการทดลองแล้ว ✓");
        this.r = null; this.kind = null;
        location.hash = `#/results/exp/${r.id}`;
      } catch (e) { Alpine.store("app").toast(e.message, "err"); }
    },
    async rerun() {
      this.rerunning = true; this.rerunDiff = null;
      try {
        const { job_id } = await api(`/api/experiments/${this.id}/rerun`, { method: "POST" });
        Alpine.store("app").toast("กำลังรันซ้ำด้วย config + snapshot เดิม…");
        for (;;) {
          await new Promise((res) => setTimeout(res, 800));
          const j = await api(`/api/jobs/${job_id}`);
          Alpine.store("app").job = j;
          if (j.status === "done") break;
          if (!["queued", "running"].includes(j.status)) throw new Error(j.error || j.status);
        }
        this.rerunDiff = await api(`/api/experiments/${this.id}/rerun/${job_id}`);
      } catch (e) { Alpine.store("app").toast("re-run ล้มเหลว: " + e.message, "err", 6000); }
      this.rerunning = false;
    },
    async del() {
      const typed = prompt(`ลบการทดลองนี้ถาวร — พิมพ์ exp_id เพื่อยืนยัน:\n${this.id}`);
      if (typed !== this.id) { if (typed !== null) Alpine.store("app").toast("exp_id ไม่ตรง — ไม่ได้ลบ", "err"); return; }
      await api(`/api/experiments/${this.id}?confirm=${encodeURIComponent(typed)}`, { method: "DELETE" });
      Alpine.store("app").toast("ลบแล้ว");
      this.r = null; this.kind = null;
      location.hash = "#/gallery";
    },
  };
}
