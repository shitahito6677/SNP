/* Stock page: candlestick + ลูกศรซื้อ/ขาย + layers (A ช่วงที่เลือก, B, C, manual, SMA/EMA/RSI/volume) */
"use strict";

function sma(v, n) { const o = []; let s = 0; for (let i = 0; i < v.length; i++) { s += v[i]; if (i >= n) s -= v[i - n]; o.push(i >= n - 1 ? s / n : null); } return o; }
function ema(v, n) { const o = [], k = 2 / (n + 1); let e = null; v.forEach((x, i) => { e = e === null ? x : x * k + e * (1 - k); o.push(i >= n - 1 ? e : null); }); return o; }
function rsi(v, n = 14) {
  const o = [null]; let g = 0, l = 0;
  for (let i = 1; i < v.length; i++) {
    const d = v[i] - v[i - 1], up = Math.max(d, 0), dn = Math.max(-d, 0);
    if (i <= n) { g += up / n; l += dn / n; o.push(i === n ? 100 - 100 / (1 + g / (l || 1e-9)) : null); }
    else { g = (g * (n - 1) + up) / n; l = (l * (n - 1) + dn) / n; o.push(100 - 100 / (1 + g / (l || 1e-9))); }
  }
  return o;
}

// chart object อยู่นอก Alpine (ห้ามถูกห่อด้วย reactive proxy)
const STK = { chart: null, rsi: null };

function stock() {
  return {
    d: null, err: "", q: "", hi: 0, hover: "", hoverItems: [], ctxLabel: "",
    gallery: null, gErr: "", gSectors: [], gSort: "ticker", logoOk: {},
    layers: { trades: true, A: true, B: true, C: true, manual: true, sma: false, ema: false, vol: true, rsi: false },
    layerList: [["trades", "Trades ▲▼", "cond"], ["A", "ช่วงที่ A เลือก", "A"], ["B", "สัญญาณ B", "B"], ["C", "เหตุการณ์ C", "C"], ["manual", "ข่าว manual", "manual"],
      ["sma", "SMA 20/50", ""], ["ema", "EMA 20", ""], ["vol", "Volume", ""], ["rsi", "RSI 14", ""]],
    _key: null, _focus: null, _inflight: null,

    get hits() { return searchTickers(this.q, 8); },
    init() {
      const go = () => { const rt = Alpine.store("app").route; if (rt.name === "stock") this.load(rt); };
      window.addEventListener("route", go);
      window.addEventListener("focus-search", () => this.$refs.search && this.$refs.search.focus());
      window.addEventListener("resize", () => this.resize());
      window.addEventListener("news-changed", () => { this._key = null; this.gallery = null; });  // ข่าวเปลี่ยน → โหลดใหม่ครั้งถัดไป
      if (Alpine.store("app").meta) go(); else window.addEventListener("app-ready", go, { once: true });
    },
    go(t) { this.q = ""; const rt = Alpine.store("app").route; const keep = rt.query.kind ? `?kind=${rt.query.kind}&id=${rt.query.id}` : ""; location.hash = `#/stock/${t}${keep}`; },
    /* ---------- gallery (ยังไม่เลือกหุ้น) ---------- */
    async loadGallery() {
      if (this.gallery) return;
      try { this.gallery = await api("/api/stocks/gallery"); this.gErr = ""; } catch (e) { this.gErr = e.message; }
    },
    get gSectorList() {
      const c = {};
      for (const x of this.gallery?.tickers || []) c[x.sector] = (c[x.sector] || 0) + 1;
      return Object.entries(c).sort((a, b) => a[0].localeCompare(b[0]));
    },
    get gItems() {
      let xs = this.gallery?.tickers || [];
      if (this.gSectors.length) xs = xs.filter((x) => this.gSectors.includes(x.sector));
      const by = { ticker: (a, b) => a.t.localeCompare(b.t), name: (a, b) => a.name.localeCompare(b.name), news: (a, b) => b.news - a.news || a.t.localeCompare(b.t) }[this.gSort];
      return [...xs].sort(by);
    },
    toggleGSector(s) { this.gSectors = this.gSectors.includes(s) ? this.gSectors.filter((x) => x !== s) : [...this.gSectors, s]; },
    initials(t) { return t.replace(/[^A-Z]/g, "").slice(0, 2) || t.slice(0, 2); },
    avatarStyle(x) { const c = SECTOR_COLORS[x.sector] || SECTOR_COLORS.Unknown; return `background:linear-gradient(135deg, ${c}, ${c}99);box-shadow:0 0 16px -4px ${c}`; },
    logoSrc(x) { return `/static/logos/${x.t}.png`; },

    async load(rt) {
      const t = rt.params.ticker;
      if (!t) { this.d = null; this.err = ""; this._key = null; this.loadGallery(); return; }
      const qs = new URLSearchParams();
      if (rt.query.kind) { qs.set("kind", rt.query.kind); qs.set("id", rt.query.id); }
      const key = t + "?" + qs;
      this._focus = rt.query.date || null;
      if (key === this._key && this.d) { this.$nextTick(() => { this.render(); if (this._focus) this.focus(this._focus); }); return; }
      if (key === this._inflight) return;  // navigation เดียวยิง event "route" 2 ครั้ง → ไม่โหลด/วาดซ้ำ
      this._key = key; this.err = ""; this._inflight = key;
      try {
        if (!rt.query.kind) { qs.set("A", "A:A1_r001_Q_LOWACC_overall"); qs.set("C", "C:rulebase-exp03"); }
        this.d = await api(`/api/stock/${t}?${qs}`);
        this.ctxLabel = rt.query.kind ? `จากการทดลอง ${rt.query.id}` + (this.d.held_out_visible ? " · แสดงช่วง held-out" : "") : "ไม่ได้เลือกการทดลอง — แสดง layer ของ A1 + C rulebase (ถ้ามี)";
        await this.$nextTick();
        this.render();
        if (this._focus) this.focus(this._focus);
      } catch (e) { this.err = e.message; this.d = null; }
      finally { this._inflight = null; }
    },
    snap(dates, t) {  // วันที่ที่ไม่ใช่วันทำการ → วันทำการถัดไป
      let lo = 0, hi = dates.length - 1;
      if (t > dates[hi]) return null;
      while (lo < hi) { const m = (lo + hi) >> 1; if (dates[m] < t) lo = m + 1; else hi = m; }
      return dates[lo];
    },
    render() {
      const d = this.d;
      if (!d || !window.LightweightCharts) return;
      const el = this.$refs.chart;
      if (STK.chart) { STK.chart.remove(); STK.chart = null; }
      if (STK.rsi) { STK.rsi.remove(); STK.rsi = null; }
      const opts = {
        layout: { background: { type: "solid", color: "rgba(0,0,0,0)" }, textColor: "#A9B4D6", fontFamily: "JB Mono, monospace" },
        grid: { vertLines: { color: "rgba(120,150,220,.07)" }, horzLines: { color: "rgba(120,150,220,.07)" } },
        rightPriceScale: { borderColor: "rgba(120,150,220,.2)" }, timeScale: { borderColor: "rgba(120,150,220,.2)" },
        crosshair: { mode: 0 }, width: el.clientWidth, height: el.clientHeight,
      };
      const ch = LightweightCharts.createChart(el, opts);
      STK.chart = ch;
      const dates = d.bars.map((b) => b.time);
      if (this.layers.A && d.layers.A.length) {
        const band = ch.addHistogramSeries({ priceScaleId: "band", lastValueVisible: false, priceLineVisible: false });
        ch.priceScale("band").applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
        const set = [];
        for (const p of d.layers.A) {
          if (p.class !== "selected") continue;
          for (const t of dates) if (t >= p.from && t < p.to) set.push({ time: t, value: 1, color: "rgba(16,185,129,.07)" });
        }
        band.setData(set);
      }
      if (this.layers.C && d.layers.C.length) {
        const cl = ch.addHistogramSeries({ priceScaleId: "cline", lastValueVisible: false, priceLineVisible: false });
        ch.priceScale("cline").applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
        const col = { positive: "rgba(52,211,153,.45)", negative: "rgba(248,113,113,.5)", neutral: "rgba(249,115,22,.35)" };
        const m = new Map();
        for (const e of d.layers.C) { const t = this.snap(dates, e.time); if (t) m.set(t, { time: t, value: 1, color: col[e.class] }); }
        cl.setData([...m.values()].sort((a, b) => (a.time < b.time ? -1 : 1)));
      }
      const candle = ch.addCandlestickSeries({ upColor: "#34D399", downColor: "#F87171", borderVisible: false, wickUpColor: "#34D399", wickDownColor: "#F87171" });
      candle.setData(d.bars.map((b) => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close })));
      if (this.layers.vol) {
        const v = ch.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
        ch.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
        v.setData(d.bars.map((b) => ({ time: b.time, value: b.volume || 0, color: b.close >= b.open ? "rgba(52,211,153,.35)" : "rgba(248,113,113,.35)" })));
      }
      const closes = d.bars.map((b) => b.close);
      const line = (vals, color, w = 1.4) => { const s = ch.addLineSeries({ color, lineWidth: w, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }); s.setData(vals.map((v, i) => (v === null ? null : { time: dates[i], value: v })).filter(Boolean)); };
      if (this.layers.sma) { line(sma(closes, 20), "#FDE68A"); line(sma(closes, 50), "#60A5FA"); }
      if (this.layers.ema) line(ema(closes, 20), "#E879F9");
      const mk = [];
      if (this.layers.trades) for (const t of d.trades) { const tm = this.snap(dates, t.date); if (!tm) continue;
        mk.push(t.side === "buy" ? { time: tm, position: "belowBar", color: "#34D399", shape: "arrowUp", text: "BUY" } : { time: tm, position: "aboveBar", color: "#F87171", shape: "arrowDown", text: "SELL" }); }
      if (this.layers.B) for (const b of d.layers.B) { const tm = this.snap(dates, b.time); if (tm) mk.push({ time: tm, position: "belowBar", color: { positive: "#C084FC", negative: "#F472B6", neutral: "#8B8FB0" }[b.class], shape: "circle", text: "B" + (b.class === "negative" ? "−" : b.class === "positive" ? "+" : "") }); }
      if (this.layers.C) for (const c of d.layers.C) { const tm = this.snap(dates, c.time); if (tm) mk.push({ time: tm, position: "aboveBar", color: { positive: "#34D399", negative: "#FB923C", neutral: "#FBBF24" }[c.class], shape: "square", text: "C" }); }
      if (this.layers.manual) for (const n of d.layers.manual) { const tm = this.snap(dates, n.time); if (tm) mk.push({ time: tm, position: "aboveBar", color: LABEL_COLORS[String(n.label)] || "#38BDF8", shape: "circle", text: "M" + (n.label > 0 ? "+" : "") + n.label }); }
      mk.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
      if (mk.length > 60) for (const x of mk) if (x.text === "BUY" || x.text === "SELL" || x.text.startsWith("B")) x.text = "";  // เยอะเกิน → เหลือแค่สัญลักษณ์
      candle.setMarkers(mk);
      ch.timeScale().fitContent();
      ch.subscribeCrosshairMove((p) => { if (p && p.time) this.setHover(typeof p.time === "string" ? p.time : `${p.time.year}-${String(p.time.month).padStart(2, "0")}-${String(p.time.day).padStart(2, "0")}`); });
      if (this.layers.rsi) {
        const r = LightweightCharts.createChart(this.$refs.rsi, { ...opts, height: this.$refs.rsi.clientHeight || 130, width: this.$refs.rsi.clientWidth });
        STK.rsi = r;
        const s = r.addLineSeries({ color: "#E879F9", lineWidth: 1.4, priceLineVisible: false });
        const rv = rsi(closes); s.setData(rv.map((v, i) => (v === null ? null : { time: dates[i], value: v })).filter(Boolean));
        s.createPriceLine({ price: 70, color: "rgba(248,113,113,.5)", lineStyle: 2 }); s.createPriceLine({ price: 30, color: "rgba(52,211,153,.5)", lineStyle: 2 });
        ch.timeScale().subscribeVisibleLogicalRangeChange((rg) => rg && r.timeScale().setVisibleLogicalRange(rg));
        r.timeScale().fitContent();
      }
    },
    resize() { if (STK.chart && this.$refs.chart) STK.chart.applyOptions({ width: this.$refs.chart.clientWidth }); if (STK.rsi) STK.rsi.applyOptions({ width: this.$refs.rsi.clientWidth }); },
    setHover(t) {
      if (t === this.hover) return;
      this.hover = t;
      const d = this.d, items = [];
      for (const x of d.trades) if (x.date === t) items.push({ title: `${x.side === "buy" ? "▲ ซื้อ" : "▼ ขาย"} ${fmtMoney(x.notional)} @ ${fmtNum(x.price_close)} (ตัดสินใจ ${x.decision_date})`, cls: x.side === "buy" ? "pos" : "neg", reasons: x.reasons });
      for (const p of d.layers.A) if (t >= p.from && t < p.to) items.push({ title: `A ${d.labels.A?.short_label || ""}: ${p.class} (score ${fmtNum(p.score, 1)}) · รอบ ${p.rebalance}`, cls: p.class === "selected" ? "pos" : "", reasons: p.reasons.map((r) => "A: " + r) });
      for (const b of d.layers.B) if (b.time === t) items.push({ title: `B ${d.labels.B?.short_label || ""}: ${b.class}`, cls: "", reasons: b.reasons.map((r) => "B: " + r) });
      for (const c of d.layers.C) if (c.time === t) items.push({ title: `C ${d.labels.C?.short_label || ""} ${d.etf}: ${c.class} (${fmtNum(c.score)})`, cls: "", reasons: c.reasons.map((r) => "C: " + r) });
      for (const n of d.layers.manual) if (n.time === t) items.push({ title: `ข่าว manual · label ${labelTag(n.label)}${n.label_method === "hindsight" ? " · hindsight (Oracle)" : n.label_method === "real_time" ? " · real-time" : " · วิธี label ไม่ระบุ"}`, cls: labelCls(n.label), reasons: [`MANUAL [${labelTag(n.label)}] ${n.headline}`] });
      this.hoverItems = items;
    },
    focus(date) {
      if (!STK.chart) return;
      const t = new Date(date), a = new Date(t - 75 * 864e5), b = new Date(+t + 75 * 864e5);
      const iso = (x) => x.toISOString().slice(0, 10);
      try { STK.chart.timeScale().setVisibleRange({ from: iso(a), to: iso(b) }); } catch (e) { /* ช่วงนอกข้อมูล */ }
      this.setHover(this.snap(this.d.bars.map((x) => x.time), date) || date);
    },
  };
}
