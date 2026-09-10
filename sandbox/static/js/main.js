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
    const stubBadge = e.is_stub ? '<span class="stub-tag">STUB</span>' : "";
    popupBody.innerHTML = `
      <div><strong>Date:</strong> ${e.date}</div>
      <div><strong>Class:</strong> ${e.class} ${stubBadge}</div>
      <div><strong>Score:</strong> ${e.score}</div>
      <div><strong>Headline:</strong> ${e.headline || "-"}</div>
    `;
    popup.hidden = false;
    const x = mouseEvent ? mouseEvent.pageX + 12 : 100;
    const y = mouseEvent ? mouseEvent.pageY + 12 : 100;
    popup.style.left = Math.min(x, window.innerWidth - 340) + "px";
    popup.style.top = Math.min(y, window.innerHeight - 160) + "px";
  }

  async function render() {
    const ticker = tickerSelect.value;
    statusEl.textContent = "Loading " + ticker + " ...";

    const params = new URLSearchParams();
    if (startInput.value) params.set("start", startInput.value);
    if (endInput.value) params.set("end", endInput.value);

    let price, events;
    try {
      const [priceRes, eventsRes] = await Promise.all([
        fetch("/api/prices/" + ticker + "?" + params.toString()),
        fetch("/api/events?ticker=" + ticker),
      ]);
      price = await priceRes.json();
      events = await eventsRes.json();
    } catch (err) {
      statusEl.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
      return;
    }

    if (price.error) {
      statusEl.textContent = "Error: " + price.error;
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

    const candlestick = {
      x: price.dates,
      open: price.open,
      high: price.high,
      low: price.low,
      close: price.close,
      type: "candlestick",
      name: ticker,
      increasing: { line: { color: "#26a69a" } },
      decreasing: { line: { color: "#ef5350" } },
    };

    const maxHigh = Math.max(...price.high);
    const macroTrace = {
      x: events.c.map((e) => e.date),
      y: events.c.map(() => maxHigh * 1.03),
      mode: "markers",
      type: "scatter",
      name: "Macro event (C)",
      marker: {
        symbol: "triangle-down",
        size: 11,
        color: events.c.map((e) => classColor(e.class)),
        line: { color: "#0e1117", width: 1 },
      },
      customdata: events.c,
      hovertemplate: "%{x}<extra></extra>",
    };

    const dateIndex = {};
    price.dates.forEach((d, i) => {
      dateIndex[d] = i;
    });
    const companyTrace = {
      x: events.b.map((e) => e.date),
      y: events.b.map((e) => {
        const i = dateIndex[e.date];
        return i !== undefined ? price.close[i] : null;
      }),
      mode: "markers",
      type: "scatter",
      name: "Company news (B)",
      marker: {
        symbol: "circle",
        size: 10,
        color: events.b.map((e) => classColor(e.class)),
        line: { color: "#fff", width: 1 },
      },
      customdata: events.b,
      hovertemplate: "%{x}<extra></extra>",
    };

    const shapes = events.c.map((e) => ({
      type: "line",
      xref: "x",
      yref: "paper",
      x0: e.date,
      x1: e.date,
      y0: 0,
      y1: 1,
      line: { color: classColor(e.class), dash: "dash", width: 1 },
      opacity: 0.6,
    }));

    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#d1d4dc" },
      margin: { t: 20, r: 20, l: 50, b: 40 },
      xaxis: { gridcolor: "#262b36", rangeslider: { visible: false } },
      yaxis: { gridcolor: "#262b36", title: "Price (USD)" },
      shapes: shapes,
      showlegend: true,
      legend: { orientation: "h", y: -0.15, font: { color: "#d1d4dc" } },
      hovermode: "closest",
    };

    Plotly.newPlot(chartDiv, [candlestick, macroTrace, companyTrace], layout, {
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
