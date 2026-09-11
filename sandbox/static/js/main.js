// main.js — shared JS for all sandbox dashboard pages.
// Wires up whichever page is active based on which DOM elements exist
// (window.__PAGE__ set per-template, used only for readability/debug).

function classColor(cls) {
  if (cls === "positive") return "#26a69a";
  if (cls === "negative") return "#ef5350";
  return "#9aa0a6";
}

// --------------------------------------------------------------------------
// Dashboard page
// --------------------------------------------------------------------------

function initDashboard() {
  const tickerSelect = document.getElementById("ticker-select");
  const startInput = document.getElementById("date-start");
  const endInput = document.getElementById("date-end");
  const reloadBtn = document.getElementById("reload-btn");
  const statusEl = document.getElementById("chart-status");
  const chartDiv = document.getElementById("candlestick-chart");
  const popup = document.getElementById("event-popup");
  const popupBody = document.getElementById("event-popup-body");
  const popupClose = document.getElementById("event-popup-close");

  popupClose.addEventListener("click", () => {
    popup.hidden = true;
  });
  document.addEventListener("click", (e) => {
    if (!popup.hidden && !popup.contains(e.target) && !chartDiv.contains(e.target)) {
      popup.hidden = true;
    }
  });

  function showPopup(e, mouseEvent) {
    const sourceBadge = e.is_stub
      ? '<span class="stub-tag">STUB</span>'
      : '<span class="real-tag">REAL</span>';
    const sourceLabel = e.source === "real_historical" ? "real historical data" : (e.source || "manual");
    popupBody.innerHTML = `
      <div><strong>Date:</strong> ${e.date}</div>
      <div><strong>Class:</strong> ${e.class} ${sourceBadge}</div>
      <div><strong>Score:</strong> ${e.score}</div>
      <div><strong>Source:</strong> ${sourceLabel}</div>
      <div><strong>Headline:</strong> ${e.headline || "-"}</div>
    `;
    popup.hidden = false;
    const x = mouseEvent ? mouseEvent.pageX + 12 : 100;
    const y = mouseEvent ? mouseEvent.pageY + 12 : 100;
    popup.style.left = Math.min(x, window.innerWidth - 340) + "px";
    popup.style.top = Math.min(y, window.innerHeight - 160) + "px";
  }

  // subplot ที่เปิดได้ ในลำดับที่จะวางจากบนลงล่าง (ใต้กราฟราคาหลัก) — Volume ใกล้ราคาสุด,
  // MACD ล่างสุด ตามธรรมเนียมของ trading platform ทั่วไป
  const SUBPLOT_ORDER = [
    { key: "volume", checkboxId: "ind-volume", title: "Volume" },
    { key: "rsi", checkboxId: "ind-rsi", title: "RSI(14)" },
    { key: "macd", checkboxId: "ind-macd", title: "MACD(12,26,9)" },
  ];

  function activeSubplots() {
    return SUBPLOT_ORDER.filter((p) => document.getElementById(p.checkboxId).checked);
  }

  // คำนวณ y-axis domain ของแต่ละ panel (main + subplot ที่เปิดอยู่) แบบ stack จากบนลงล่าง
  // เติมเต็มพอดี [0,1] เสมอไม่ว่าจะเปิดกี่ panel (ไม่เหลือช่องว่างล่างสุด)
  function computeDomains(nExtra) {
    if (nExtra === 0) return { main: [0, 1] };
    const gap = 0.03;
    const mainHeight = { 1: 0.62, 2: 0.5, 3: 0.42 }[nExtra] || 0.42;
    const remaining = 1 - mainHeight - gap; // gap ระหว่าง main กับ subplot แรก
    const slotHeight = (remaining - gap * (nExtra - 1)) / nExtra; // เผื่อ gap ระหว่าง subplot ด้วยกัน

    const domains = { main: [1 - mainHeight, 1] };
    let top = domains.main[0] - gap;
    for (let i = 0; i < nExtra; i++) {
      const bottom = Math.max(top - slotHeight, 0);
      domains["slot" + i] = [bottom, top];
      top = bottom - gap;
    }
    return domains;
  }

  async function render() {
    const ticker = tickerSelect.value;
    statusEl.textContent = "Loading " + ticker + " ...";

    const params = new URLSearchParams();
    if (startInput.value) params.set("start", startInput.value);
    if (endInput.value) params.set("end", endInput.value);

    const showSma20 = document.getElementById("ind-sma20").checked;
    const showSma50 = document.getElementById("ind-sma50").checked;
    const subplots = activeSubplots(); // ordered list of active {key, title}
    const needIndicators = showSma20 || showSma50 || subplots.some((p) => p.key !== "volume");

    let price, events, ind;
    try {
      const fetches = [
        fetch("/api/prices/" + ticker + "?" + params.toString()),
        fetch("/api/events?ticker=" + ticker + "&" + params.toString()),
      ];
      if (needIndicators) fetches.push(fetch("/api/indicators/" + ticker + "?" + params.toString()));
      const responses = await Promise.all(fetches);
      price = await responses[0].json();
      events = await responses[1].json();
      ind = needIndicators ? await responses[2].json() : null;
    } catch (err) {
      statusEl.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
      return;
    }

    if (price.error) {
      statusEl.textContent = "Error: " + price.error;
      return;
    }
    if (ind && ind.error) {
      statusEl.textContent = "Error (indicators): " + ind.error;
      return;
    }
    if (!price.dates.length) {
      statusEl.textContent = "ไม่มีข้อมูลราคาในช่วงวันที่ที่เลือก";
      Plotly.purge(chartDiv);
      return;
    }

    // ตั้งค่า default date range จากช่วงข้อมูลจริงตอนโหลดครั้งแรก (ถ้ายังไม่ได้เลือกเอง)
    if (!startInput.value) startInput.value = price.dates[Math.max(0, price.dates.length - 300)];
    if (!endInput.value) endInput.value = price.dates[price.dates.length - 1];

    const traces = [];
    const shapes = [];

    const candlestick = {
      x: price.dates,
      open: price.open,
      high: price.high,
      low: price.low,
      close: price.close,
      type: "candlestick",
      name: ticker,
      xaxis: "x",
      yaxis: "y",
      increasing: { line: { color: "#26a69a" } },
      decreasing: { line: { color: "#ef5350" } },
    };
    traces.push(candlestick);

    if (showSma20 && ind) {
      traces.push({
        x: ind.dates, y: ind.sma20, type: "scatter", mode: "lines", name: "SMA20",
        xaxis: "x", yaxis: "y", line: { color: "#f5c518", width: 1.3 },
      });
    }
    if (showSma50 && ind) {
      traces.push({
        x: ind.dates, y: ind.sma50, type: "scatter", mode: "lines", name: "SMA50",
        xaxis: "x", yaxis: "y", line: { color: "#4f8cff", width: 1.3 },
      });
    }

    const maxHigh = Math.max(...price.high);
    traces.push({
      x: events.c.map((e) => e.date),
      y: events.c.map(() => maxHigh * 1.03),
      mode: "markers", type: "scatter", name: "Macro event (C)",
      xaxis: "x", yaxis: "y",
      marker: {
        symbol: "triangle-down", size: 11,
        color: events.c.map((e) => classColor(e.class)),
        line: { color: "#0e1117", width: 1 },
      },
      customdata: events.c,
      hovertemplate: "%{x}<extra></extra>",
    });

    const dateIndex = {};
    price.dates.forEach((d, i) => {
      dateIndex[d] = i;
    });
    traces.push({
      x: events.b.map((e) => e.date),
      y: events.b.map((e) => {
        const i = dateIndex[e.date];
        return i !== undefined ? price.close[i] : null;
      }),
      mode: "markers", type: "scatter", name: "Company news (B)",
      xaxis: "x", yaxis: "y",
      marker: {
        symbol: "circle", size: 10,
        color: events.b.map((e) => classColor(e.class)),
        line: { color: "#fff", width: 1 },
      },
      customdata: events.b,
      hovertemplate: "%{x}<extra></extra>",
    });

    shapes.push(
      ...events.c.map((e) => ({
        type: "line", xref: "x", yref: "y domain",
        x0: e.date, x1: e.date, y0: 0, y1: 1,
        line: { color: classColor(e.class), dash: "dash", width: 1 },
        opacity: 0.6,
      }))
    );

    // --- subplots (Volume / RSI / MACD) ---
    const domains = computeDomains(subplots.length);
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#d1d4dc" },
      margin: { t: 20, r: 20, l: 55, b: 40 },
      xaxis: { gridcolor: "#262b36", rangeslider: { visible: false }, domain: [0, 1] },
      yaxis: { gridcolor: "#262b36", title: "Price (USD)", domain: domains.main },
      shapes: shapes,
      showlegend: true,
      legend: { orientation: "h", y: -0.08, font: { color: "#d1d4dc" } },
      hovermode: "closest",
    };

    subplots.forEach((panel, i) => {
      const n = i + 2; // axis suffix: main = x/y, first subplot = x2/y2, ...
      const domain = domains["slot" + i];
      layout["xaxis" + n] = { gridcolor: "#262b36", matches: "x", domain: [0, 1], anchor: "y" + n };
      layout["yaxis" + n] = { gridcolor: "#262b36", title: panel.title, domain: domain, anchor: "x" + n };

      if (panel.key === "volume") {
        traces.push({
          x: price.dates, y: price.volume, type: "bar", name: "Volume",
          xaxis: "x" + n, yaxis: "y" + n, showlegend: false,
          marker: {
            color: price.close.map((c, idx) => (c >= price.open[idx] ? "#26a69a" : "#ef5350")),
          },
        });
      } else if (panel.key === "rsi" && ind) {
        traces.push({
          x: ind.dates, y: ind.rsi14, type: "scatter", mode: "lines", name: "RSI(14)",
          xaxis: "x" + n, yaxis: "y" + n, showlegend: false, line: { color: "#4f8cff", width: 1.3 },
        });
        shapes.push(
          { type: "line", xref: "x", yref: "y" + n, x0: price.dates[0], x1: price.dates[price.dates.length - 1], y0: 70, y1: 70, line: { color: "#ef5350", dash: "dot", width: 1 } },
          { type: "line", xref: "x", yref: "y" + n, x0: price.dates[0], x1: price.dates[price.dates.length - 1], y0: 30, y1: 30, line: { color: "#26a69a", dash: "dot", width: 1 } }
        );
        layout["yaxis" + n].range = [0, 100];
      } else if (panel.key === "macd" && ind) {
        traces.push(
          {
            x: ind.dates, y: ind.macd_hist, type: "bar", name: "MACD hist",
            xaxis: "x" + n, yaxis: "y" + n, showlegend: false,
            marker: { color: ind.macd_hist.map((v) => (v >= 0 ? "#26a69a" : "#ef5350")) },
          },
          {
            x: ind.dates, y: ind.macd, type: "scatter", mode: "lines", name: "MACD",
            xaxis: "x" + n, yaxis: "y" + n, showlegend: false, line: { color: "#4f8cff", width: 1.3 },
          },
          {
            x: ind.dates, y: ind.macd_signal, type: "scatter", mode: "lines", name: "MACD signal",
            xaxis: "x" + n, yaxis: "y" + n, showlegend: false, line: { color: "#f5c518", width: 1.3 },
          }
        );
      }
    });

    layout.shapes = shapes;
    chartDiv.style.height = (420 + subplots.length * 160) + "px";

    Plotly.newPlot(chartDiv, traces, layout, {
      responsive: true,
      displaylogo: false,
    });

    chartDiv.on("plotly_click", (evt) => {
      const pt = evt.points && evt.points[0];
      if (!pt || !pt.customdata) return;
      showPopup(pt.customdata, evt.event);
    });

    statusEl.textContent =
      ticker +
      ": " +
      price.dates.length +
      " trading days (" +
      price.dates[0] +
      " → " +
      price.dates[price.dates.length - 1] +
      ") | macro (C) events: " +
      events.c.length +
      " | company (B) events: " +
      events.b.length;
  }

  ["ind-sma20", "ind-sma50", "ind-volume", "ind-rsi", "ind-macd"].forEach((id) => {
    document.getElementById(id).addEventListener("change", render);
  });

  tickerSelect.addEventListener("change", render);
  reloadBtn.addEventListener("click", render);
  render();
}

// --------------------------------------------------------------------------
// Events (manual event injection) page
// --------------------------------------------------------------------------

function renderEventResult(data) {
  const rows = data.rows
    .map((r) => {
      const stubBadge = r.is_stub ? '<span class="stub-tag">STUB</span>' : "";
      return `<div><strong>${r.ticker}</strong>: ${r.class} (${r.score}) ${stubBadge}</div>`;
    })
    .join("");
  const label = data.kind === "b" ? "B (company — 1 ticker)" : "C (macro — ทุก ticker)";
  return `Injected <strong>${label}</strong> event — ${data.rows.length} row(s) written to
    <code>sandbox/data/manual_events.csv</code>:${rows}`;
}

function initEvents() {
  const tickerSelect = document.getElementById("event-ticker");
  const kindSelect = document.getElementById("event-kind");
  const bOption = kindSelect.querySelector('option[value="b"]');
  const bHint = document.getElementById("b-disabled-hint");
  const form = document.getElementById("event-form");
  const errorEl = document.getElementById("event-error");
  const resultEl = document.getElementById("event-result");
  const tickersWithCompanyNews = window.__TICKERS_WITH_COMPANY_NEWS__ || [];

  // Phase 3 rule: ถ้า ticker ไม่มี company-level news ที่เกี่ยวข้อง ต้อง disable ปุ่ม/option B
  // อัตโนมัติ (เผื่ออนาคต — ตอนนี้ทุก ticker รองรับหมดเพราะ Model B ยังเป็น stub)
  function syncBAvailability() {
    const ticker = tickerSelect.value;
    const available = tickersWithCompanyNews.includes(ticker);
    bOption.disabled = !available;
    bHint.hidden = available;
    if (!available && kindSelect.value === "b") kindSelect.value = "c";
  }
  tickerSelect.addEventListener("change", syncBAvailability);
  syncBAvailability();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    resultEl.hidden = true;
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;

    const payload = {
      kind: kindSelect.value,
      date: document.getElementById("event-date").value,
      headline: document.getElementById("event-headline").value,
      ticker: tickerSelect.value,
    };

    try {
      const res = await fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        errorEl.textContent = data.error || "เกิดข้อผิดพลาด";
        errorEl.hidden = false;
        return;
      }
      resultEl.innerHTML = renderEventResult(data);
      resultEl.hidden = false;
      document.getElementById("event-headline").value = "";
    } catch (err) {
      errorEl.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
      errorEl.hidden = false;
    } finally {
      submitBtn.disabled = false;
    }
  });

  initBulkUpload();
}

function initBulkUpload() {
  const fileInput = document.getElementById("bulk-file");
  const previewBtn = document.getElementById("bulk-preview-btn");
  const confirmBtn = document.getElementById("bulk-confirm-btn");
  const errorEl = document.getElementById("bulk-error");
  const previewSection = document.getElementById("bulk-preview-section");
  const summaryEl = document.getElementById("bulk-summary");
  const tableBody = document.querySelector("#bulk-preview-table tbody");
  const commitResultEl = document.getElementById("bulk-commit-result");

  if (!fileInput) return; // หน้านี้ไม่มี bulk upload section

  function renderPreviewTable(rows) {
    tableBody.innerHTML = rows
      .map(
        (r) => `
        <tr class="${r.valid ? "" : "signal-sell"}">
          <td>${r.row_num}</td>
          <td>${r.date}</td>
          <td>${r.ticker || "-"}</td>
          <td>${r.type ? r.type.toUpperCase() : "-"}</td>
          <td class="headline-cell" title="${(r.headline || "").replace(/"/g, "&quot;")}">${(r.headline || "").slice(0, 50)}</td>
          <td>${r.valid ? '<span class="real-tag">OK</span>' : `<span class="stub-tag">ERROR</span> ${r.error}`}</td>
        </tr>`
      )
      .join("");
  }

  previewBtn.addEventListener("click", async () => {
    errorEl.hidden = true;
    previewSection.hidden = true;
    commitResultEl.hidden = true;

    const file = fileInput.files[0];
    if (!file) {
      errorEl.textContent = "เลือกไฟล์ CSV ก่อน";
      errorEl.hidden = false;
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/events/bulk/preview", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok || data.file_error) {
        errorEl.textContent = data.error || data.file_error || "เกิดข้อผิดพลาด";
        errorEl.hidden = false;
        return;
      }
      summaryEl.textContent = `${data.rows.length} แถวทั้งหมด — valid: ${data.valid_count}, error: ${data.error_count}`;
      renderPreviewTable(data.rows);
      previewSection.hidden = false;
      confirmBtn.disabled = data.valid_count === 0;
    } catch (err) {
      errorEl.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
      errorEl.hidden = false;
    }
  });

  confirmBtn.addEventListener("click", async () => {
    errorEl.hidden = true;
    commitResultEl.hidden = true;
    confirmBtn.disabled = true;

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/events/bulk/commit", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok || data.file_error) {
        errorEl.textContent = data.error || data.file_error || "เกิดข้อผิดพลาด";
        errorEl.hidden = false;
        return;
      }
      commitResultEl.innerHTML = `Imported: <strong>${data.success.length}</strong> row(s) succeeded,
        <strong>${data.failed.length}</strong> row(s) skipped.
        ${data.failed.length ? "<br>Skipped: " + data.failed.map((f) => `#${f.row_num} (${f.error})`).join(", ") : ""}`;
      commitResultEl.hidden = false;
      previewSection.hidden = true;
      fileInput.value = "";
    } catch (err) {
      errorEl.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
      errorEl.hidden = false;
    } finally {
      confirmBtn.disabled = false;
    }
  });
}

// --------------------------------------------------------------------------
// Rules (editable rule table + versioning) page
// --------------------------------------------------------------------------

function initRules() {
  const form = document.getElementById("rules-form");
  const errorEl = document.getElementById("rules-error");
  const resultEl = document.getElementById("rules-result");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    resultEl.hidden = true;
    const submitBtn = document.getElementById("save-version-btn");
    submitBtn.disabled = true;

    const table = Array.from(document.querySelectorAll(".decision-select")).map((sel) => ({
      a: sel.dataset.a,
      b: sel.dataset.b,
      c: sel.dataset.c,
      decision: sel.value,
    }));
    const description = document.getElementById("rules-description").value;

    try {
      const res = await fetch("/api/rules/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ table, description }),
      });
      const data = await res.json();
      if (!res.ok) {
        errorEl.textContent = data.error || "เกิดข้อผิดพลาด";
        errorEl.hidden = false;
        return;
      }
      resultEl.innerHTML = `Saved <strong>${data.version}</strong> → <code>${data.path}</code>.
        <a href="/rules?version=${data.version.replace("v", "")}">เปิดดู version นี้</a>`;
      resultEl.hidden = false;
    } catch (err) {
      errorEl.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
      errorEl.hidden = false;
    } finally {
      submitBtn.disabled = false;
    }
  });
}

// --------------------------------------------------------------------------
// Experiments page (Phase 5: run + diff)
// --------------------------------------------------------------------------

function initExperiments() {
  const runForm = document.getElementById("run-experiment-form");
  const runError = document.getElementById("run-error");
  const runResult = document.getElementById("run-result");

  if (runForm) {
    runForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      runError.hidden = true;
      runResult.hidden = true;
      const submitBtn = runForm.querySelector("button[type=submit]");
      submitBtn.disabled = true;

      const tickerSet = Array.from(document.querySelectorAll(".exp-ticker-checkbox:checked")).map(
        (el) => el.value
      );
      const payload = {
        rule_version: document.getElementById("exp-rule-version").value,
        ticker_set: tickerSet,
        start: document.getElementById("exp-date-start").value,
        end: document.getElementById("exp-date-end").value,
        notes: document.getElementById("exp-notes").value,
      };

      try {
        const res = await fetch("/api/experiments/runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
          runError.textContent = data.error || "เกิดข้อผิดพลาด";
          runError.hidden = false;
          return;
        }
        runResult.innerHTML = `Saved experiment <strong>${data.experiment_id}</strong> — ${data.decisions.length} decision(s). Reload the page to see it in the list below.`;
        runResult.hidden = false;
      } catch (err) {
        runError.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
        runError.hidden = false;
      } finally {
        submitBtn.disabled = false;
      }
    });
  }

  const diffBtn = document.getElementById("diff-btn");
  const diffError = document.getElementById("diff-error");
  const diffResult = document.getElementById("diff-result");

  if (diffBtn) {
    diffBtn.addEventListener("click", async () => {
      diffError.hidden = true;
      diffResult.hidden = true;

      const selected = Array.from(document.querySelectorAll(".diff-checkbox:checked")).map(
        (el) => el.value
      );
      if (selected.length !== 2) {
        diffError.textContent = "เลือกให้ครบ 2 experiment เพื่อ diff";
        diffError.hidden = false;
        return;
      }

      try {
        const res = await fetch(`/api/experiments/diff?a=${selected[0]}&b=${selected[1]}`);
        const data = await res.json();
        if (!res.ok) {
          diffError.textContent = data.error || "เกิดข้อผิดพลาด";
          diffError.hidden = false;
          return;
        }
        diffResult.innerHTML = renderDiff(data);
        diffResult.hidden = false;
      } catch (err) {
        diffError.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
        diffError.hidden = false;
      }
    });
  }
}

function renderDiff(data) {
  const header = `<strong>${data.experiment_a.rule_version}</strong> (${data.experiment_a.experiment_id.slice(0, 8)}…)
    vs <strong>${data.experiment_b.rule_version}</strong> (${data.experiment_b.experiment_id.slice(0, 8)}…)`;

  if (!data.differs.length) {
    return `${header}<br><br>ไม่มี (ticker, date) ไหน decision ต่างกันเลย
      (same: ${data.same.length}, only in A: ${data.only_in_a.length}, only in B: ${data.only_in_b.length})`;
  }

  const rows = data.differs
    .map(
      (d) =>
        `<tr><td>${d.ticker}</td><td>${d.date}</td><td>${d.decision_a}</td><td>${d.decision_b}</td></tr>`
    )
    .join("");

  return `${header}<br><br>
    <strong>${data.differs.length}</strong> (ticker, date) ที่ decision ต่างกัน
    (same: ${data.same.length}, only in A: ${data.only_in_a.length}, only in B: ${data.only_in_b.length})
    <table class="data-table" style="margin-top:10px">
      <thead><tr><th>Ticker</th><th>Date</th><th>Decision A</th><th>Decision B</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// --------------------------------------------------------------------------
// Dispatch on page load
// --------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("candlestick-chart")) initDashboard();
  if (document.getElementById("event-form")) initEvents();
  if (document.getElementById("rules-form")) initRules();
  if (window.__PAGE__ === "experiments") initExperiments();
});
