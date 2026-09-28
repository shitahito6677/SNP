/* News page: @mention, auto-detect (ข้อเสนอให้ยืนยัน), แนะนำข่าว C, วันตลาดปิด, mini chart, CSV drag-and-drop */
"use strict";

const NEWS = { charts: {} };  // chart object นอก Alpine reactive state

function news() {
  return {
    headline: "", body: "", date: "", label: 0, labelMethod: "unknown", csvMethod: "unknown", methods: null, csvResult: null, tickers: [], ignored: [], sectors: [], macroOn: false,
    det: null, dateInfo: null, mq: null, mStart: 0, mi: 0, list: [], csv: null, csvErr: "", csvText: "", csvName: "", dragOver: false, _t: null,

    init() {
      const go = () => { if (Alpine.store("app").route.name === "news") this.load(); };
      window.addEventListener("route", go);
      if (Alpine.store("app").meta) go(); else window.addEventListener("app-ready", go, { once: true });
    },
    async load() {
      if (!this.date) this.date = Alpine.store("app").meta.config.default_end;
      await this.refresh();
    },
    async refresh() { [this.list, this.methods] = await Promise.all([api("/api/news"), api("/api/news/methods")]); },
    methodList() { return this.methods?.methods || [["hindsight", "hindsight"], ["real_time", "real-time"], ["unknown", "ยังไม่ระบุ"]]; },
    /* ---------- ข่าวซ้ำ: ซ้ำเป๊ะ = ข้ามเงียบ ๆ · ticker+วันที่ตรงแต่หัวข่าวต่าง = ให้ผู้ใช้เลือก ---------- */
    csvVisibleRows() { return (this.csv?.rows || []).filter((r) => r.dup?.status !== "exact"); },
    dupCounts() {
      const rows = this.csv?.rows || [];
      return { newRows: rows.filter((r) => r.dup?.status === "new" && r.include).length, exact: rows.filter((r) => r.dup?.status === "exact").length,
        review: rows.filter((r) => r.dup?.status === "review").length, reviewOpen: rows.filter((r) => r.dup?.status === "review" && !r.dup_action).length,
        invalid: rows.filter((r) => r.skip_reasons.length).length };
    },
    setDupAction(r, a) { r.dup_action = a || null; r.include = a === "replace" || a === "keep_both"; },
    setCsvMethod(m) { this.csvMethod = m; if (this.csv) this.csv.rows.forEach((r) => { r.label_method = m; }); },
    async setBatchMethod(b, m) {
      const what = m === "hindsight" ? "hindsight — label ตั้งตอนรู้ผลราคาแล้ว (ใช้ได้แค่ Oracle test)" : "real-time — label จากเนื้อข่าว ณ วันข่าว ไม่รู้ผลล่วงหน้า";
      if (!confirm(`ระบุวิธี label ของ ${b.n} ข่าวในชุด "${b.batch}" เป็น\n${what}\n\nยืนยัน?`)) return;
      const r = await api("/api/news/label_method", { method: "POST", body: { ids: b.ids, method: m } });
      Alpine.store("app").toast(`ระบุวิธี label แล้ว ${r.updated} ข่าว`);
      await this.refresh();
    },
    get mHits() { return this.mq === null ? [] : searchTickers(this.mq || "", 8); },
    secColor(s) { return SECTOR_COLORS[s] || "#94A3B8"; },
    info(t) { return (Alpine.store("app").meta.tickers.find((x) => x.t === t)) || { sector: "Unknown", name: t }; },
    etfs() { return Object.values(Alpine.store("app").meta.sector_etfs); },

    /* ---------- @mention ---------- */
    onType(e) {
      const el = e.target, pos = el.selectionStart, before = el.value.slice(0, pos);
      const m = before.match(/@([A-Za-z0-9.\-]{0,12})$/);
      if (m) { this.mq = m[1]; this.mStart = pos - m[0].length; this.mi = 0; } else this.mq = null;
      clearTimeout(this._t); this._t = setTimeout(() => this.detectNow(), 350);
    },
    onKey(e) {
      if (this.mq === null || !this.mHits.length) return;
      if (e.key === "ArrowDown") { e.preventDefault(); this.mi = Math.min(this.mi + 1, this.mHits.length - 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); this.mi = Math.max(this.mi - 1, 0); }
      else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); this.pick(this.mHits[this.mi]); }
      else if (e.key === "Escape") this.mq = null;
    },
    pick(h) {
      const el = this.$refs.hl, pos = el.selectionStart;
      this.headline = this.headline.slice(0, this.mStart) + "@" + h.t + " " + this.headline.slice(pos);
      this.mq = null;
      this.addT(h.t);
      this.$nextTick(() => { const p = this.mStart + h.t.length + 2; el.focus(); el.setSelectionRange(p, p); });
      this.detectNow();
    },
    addT(t) { if (!this.tickers.includes(t)) { this.tickers.push(t); this.$nextTick(() => this.minis()); } },
    removeT(t) { this.tickers = this.tickers.filter((x) => x !== t); this.ignored.push(t); },

    /* ---------- auto-detect (เป็นข้อเสนอเท่านั้น) ---------- */
    async detectNow() {
      const text = `${this.headline}\n${this.body}`;
      this.det = await api("/api/news/detect", { method: "POST", body: { text, date: this.date } });
      this.dateInfo = this.det.date_info || null;
      this.$nextTick(() => this.minis());
    },
    suggestions() { return (this.det?.mentions || []).filter((m) => !this.tickers.includes(m.ticker) && !this.ignored.includes(m.ticker) && m.how !== "@mention"); },
    accept(m) { this.addT(m.ticker); },
    ignore(m) { this.ignored.push(m.ticker); },
    confirmMacro(which) { this.macroOn = true; this.sectors = which === "all" ? this.etfs() : [...this.det.macro.sectors]; },

    /* ---------- mini charts ---------- */
    async minis() {
      if (!window.LightweightCharts || !this.date) return;
      const d = new Date(this.date), iso = (x) => x.toISOString().slice(0, 10);
      const start = iso(new Date(d - 45 * 864e5)), end = iso(new Date(+d + 45 * 864e5));
      for (const t of this.tickers.slice(0, 4)) {
        const el = document.querySelector(`[data-mini="${t}"]`);
        if (!el || el.dataset.key === `${t}|${this.date}`) continue;
        el.dataset.key = `${t}|${this.date}`;
        if (NEWS.charts[t]) { NEWS.charts[t].remove(); delete NEWS.charts[t]; }
        el.innerHTML = "";
        let data;
        try { data = await api(`/api/stock/${t}?start=${start}&end=${end}`); } catch (e) { el.innerHTML = `<span class="dim">${e.message}</span>`; continue; }
        const ch = LightweightCharts.createChart(el, { height: 130, width: el.clientWidth, layout: { background: { type: "solid", color: "rgba(0,0,0,0)" }, textColor: "#6F7BA3", fontSize: 10 },
          grid: { vertLines: { visible: false }, horzLines: { color: "rgba(120,150,220,.07)" } }, timeScale: { visible: true, borderVisible: false }, rightPriceScale: { borderVisible: false }, handleScroll: false, handleScale: false });
        const s = ch.addAreaSeries({ lineColor: "#22D3EE", topColor: "rgba(34,211,238,.25)", bottomColor: "rgba(34,211,238,0)", lineWidth: 1.5, priceLineVisible: false });
        s.setData(data.bars.map((b) => ({ time: b.time, value: b.close })));
        const at = data.bars.find((b) => b.time >= (this.dateInfo?.next_trading_day || this.date));
        if (at) s.setMarkers([{ time: at.time, position: "aboveBar", color: "#38BDF8", shape: "arrowDown", text: "ข่าว" }]);
        if (!data.bars.length) el.innerHTML = `<span class="dim">ไม่มีราคาในช่วงนี้ (อาจเป็นช่วง held-out ที่ล็อกไว้)</span>`;
        ch.timeScale().fitContent();
        NEWS.charts[t] = ch;
      }
    },

    async save() {
      try {
        await api("/api/news", { method: "POST", body: {
          headline: this.headline, body: this.body, date: this.date, effective_date: this.dateInfo?.next_trading_day,
          tickers: this.tickers, sectors: this.macroOn ? this.sectors : [], label: this.label, label_method: this.labelMethod,
          detected_by: Object.fromEntries((this.det?.mentions || []).filter((m) => this.tickers.includes(m.ticker)).map((m) => [m.ticker, m.how])) } });
        Alpine.store("app").toast("บันทึกข่าวแล้ว (source = manual)");
        Object.assign(this, { headline: "", body: "", tickers: [], ignored: [], sectors: [], macroOn: false, det: null, label: 0 });
        await this.refresh();
      } catch (e) { Alpine.store("app").toast(e.message, "err", 6000); }
    },
    async del(n) {
      if (!confirm(`ลบข่าวนี้?\n${n.headline}`)) return;
      await api(`/api/news/${n.id}`, { method: "DELETE" });
      await this.refresh();
    },

    /* ---------- CSV ---------- */
    drop(e) { this.dragOver = false; const f = e.dataTransfer.files[0]; if (f) this.file(f); },
    file(f) {
      if (!f) return;
      const rd = new FileReader();
      rd.onload = async () => {
        this.csvErr = ""; this.csv = null;
        // UTF-8 ก่อน (ตัด BOM ที่ server) — ไม่ใช่ UTF-8 จริง ๆ → ลอง Windows-874 (ไฟล์ภาษาไทยจาก Excel รุ่นเก่า)
        let text;
        try { text = new TextDecoder("utf-8", { fatal: true }).decode(rd.result); }
        catch (e) { text = new TextDecoder("windows-874").decode(rd.result); }
        this.csvText = text; this.csvName = f.name;
        await this.previewCsv(null);
      };
      rd.onerror = () => { this.csvErr = "อ่านไฟล์ไม่ได้: เบราว์เซอร์เปิดไฟล์นี้ไม่ได้"; };
      rd.readAsArrayBuffer(f);
    },
    async previewCsv(mapping) {
      try {
        this.csv = await api("/api/news/csv/preview", { method: "POST", body: { text: this.csvText, mapping } }); this.csvErr = ""; this.csvResult = null;
        this.csv.rows.forEach((r) => { r.label_method = this.csvMethod; });
      }
      catch (e) { this.csvErr = e.message; }
    },
    remap(field, col) { this.previewCsv({ ...this.csv.mapping, [field]: col || null }); },
    async commitCsv() {
      const batch = `${this.csvName} @ ${new Date().toISOString().slice(0, 16).replace("T", " ")}`;
      const rows = this.csv.rows.map((r) => ({ ...r, import_batch: batch, sectors: !r.tickers.length && r.macro.suggest ? this.etfs() : [] }));
      try {
        const res = await api("/api/news/csv/commit", { method: "POST", body: { rows } });
        this.csvResult = res;
        Alpine.store("app").toast(`นำเข้าใหม่ ${res.saved} แถว · ข้ามอัตโนมัติเพราะซ้ำเป๊ะ ${res.skipped_exact} แถว`
          + (res.review_pending ? ` · ยังไม่ได้ตรวจ ${res.review_pending} แถว (ไม่ได้บันทึก)` : "") + (res.errors.length ? ` · ผิดพลาด ${res.errors.length}` : ""),
          res.errors.length ? "err" : "ok", 7000);
        if (res.errors.length) this.csvErr = res.errors.map((x) => `แถว ${x.row}: ${x.error}`).join(" · ");
        else this.csv = null;
      } catch (e) { this.csvErr = "บันทึกไม่สำเร็จ: " + e.message; }
      await this.refresh();
    },
  };
}
