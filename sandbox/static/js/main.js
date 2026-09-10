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
      x: events.macro.map((e) => e.date),
      y: events.macro.map(() => maxHigh * 1.03),
      mode: "markers",
      type: "scatter",
      name: "Macro event",
      marker: {
        symbol: "triangle-down",
        size: 11,
        color: events.macro.map((e) => classColor(e.class)),
        line: { color: "#0e1117", width: 1 },
      },
      customdata: events.macro,
      hovertemplate: "%{x}<extra></extra>",
    };

    const dateIndex = {};
    price.dates.forEach((d, i) => {
      dateIndex[d] = i;
    });
    const companyTrace = {
      x: events.company.map((e) => e.date),
      y: events.company.map((e) => {
        const i = dateIndex[e.date];
        return i !== undefined ? price.close[i] : null;
      }),
      mode: "markers",
      type: "scatter",
      name: "Company news",
      marker: {
        symbol: "circle",
        size: 10,
        color: events.company.map((e) => classColor(e.class)),
        line: { color: "#fff", width: 1 },
      },
      customdata: events.company,
      hovertemplate: "%{x}<extra></extra>",
    };

    const shapes = events.macro.map((e) => ({
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
      ") | macro events: " +
      events.macro.length +
      " | company events: " +
      events.company.length;
  }

  tickerSelect.addEventListener("change", render);
  reloadBtn.addEventListener("click", render);
  render();
}

// --------------------------------------------------------------------------
// Events (manual event injection) page
// --------------------------------------------------------------------------

function renderEventResult(data) {
  if (data.kind === "company") {
    const stubBadge = data.is_stub ? '<span class="stub-tag">STUB</span>' : "";
    return `Injected <strong>company</strong> event for <strong>${data.ticker}</strong> on ${data.date}: <strong>${data.class}</strong> (score ${data.score}) ${stubBadge}`;
  }
  const rows = Object.entries(data.per_ticker)
    .map(([t, r]) => {
      const stubBadge = r.is_stub ? '<span class="stub-tag">STUB</span>' : "";
      return `<div><strong>${t}</strong>: ${r.class} (${r.score}) ${stubBadge}</div>`;
    })
    .join("");
  return `Injected <strong>macro</strong> event on ${data.date} — per ticker/sector:${rows}`;
}

function initEvents() {
  const kindSelect = document.getElementById("event-kind");
  const tickerField = document.getElementById("ticker-field");
  const form = document.getElementById("event-form");
  const errorEl = document.getElementById("event-error");
  const resultEl = document.getElementById("event-result");

  function syncTickerField() {
    tickerField.style.display = kindSelect.value === "company" ? "block" : "none";
  }
  kindSelect.addEventListener("change", syncTickerField);
  syncTickerField();

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
      ticker: document.getElementById("event-ticker").value,
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
      form.reset();
      syncTickerField();
    } catch (err) {
      errorEl.textContent = "เชื่อมต่อ server ไม่ได้: " + err.message;
      errorEl.hidden = false;
    } finally {
      submitBtn.disabled = false;
    }
  });
}

// --------------------------------------------------------------------------
// Dispatch on page load
// --------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("candlestick-chart")) initDashboard();
  if (document.getElementById("event-form")) initEvents();
});
