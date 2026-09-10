"""
Sandbox dashboard (Phase 2) — Flask + Plotly.js (CDN), dark trading-dashboard theme.

รัน (จาก project root เพื่อให้ import `sandbox.*` เจอ): python3 -m sandbox.app.server
เปิด: http://127.0.0.1:5050

หน้า: Dashboard (กราฟแท่งเทียน + event marker) / Events (manual event injection) /
Rules (27-row rule table) / Experiments (ประวัติ event ที่ inject ไปแล้ว)
"""

from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request

from sandbox import config, events_store
from sandbox.inference import model_a, model_b, model_c
from sandbox.rules import versions as rule_versions

SANDBOX_DIR = Path(__file__).resolve().parent.parent
PRICES_DIR = SANDBOX_DIR / "data" / "prices"

app = Flask(
    __name__,
    template_folder=str(SANDBOX_DIR / "templates"),
    static_folder=str(SANDBOX_DIR / "static"),
)


def _probe_stub_mode() -> bool:
    """เช็คแบบไม่เสียค่าใช้จ่าย (ไม่เรียก predict() จริง) ว่ายังมีโมเดลไหนเป็น stub อยู่ไหม
    โดยอ่าน module-level constant `IS_STUB` ของแต่ละ inference module — พอสลับเป็นโมเดลจริง
    ครบทั้ง 3 ตัว (ตั้ง IS_STUB = False) banner จะหายไปเองโดยไม่ต้องแก้โค้ด UI"""
    return any(getattr(m, "IS_STUB", True) for m in (model_a, model_b, model_c))


@app.context_processor
def inject_globals():
    date_min, date_max = config.price_date_range()
    return {
        "stub_mode": _probe_stub_mode(),
        "tickers": config.TICKERS,
        "date_min": date_min,
        "date_max": date_max,
    }


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return dashboard()


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", ticker_sector=config.TICKER_SECTOR)


@app.route("/events")
def events_page():
    return render_template(
        "events.html",
        ticker_sector=config.TICKER_SECTOR,
        tickers_with_company_news=sorted(config.TICKERS_WITH_COMPANY_NEWS),
    )


@app.route("/rules")
def rules_page():
    requested = request.args.get("version", type=int)
    try:
        n = requested if requested is not None else rule_versions.latest_version()
        payload = rule_versions.load_version(n)
    except FileNotFoundError as e:
        return render_template("rules.html", error=str(e), payload=None, all_versions=[]), 404

    all_versions = [
        {"n": v, **rule_versions.load_version(v)} for v in rule_versions.list_versions()
    ]
    return render_template(
        "rules.html", error=None, payload=payload, current_n=n, all_versions=all_versions
    )


@app.route("/experiments")
def experiments_page():
    return render_template("experiments.html", events=events_store.list_all_events())


# --------------------------------------------------------------------------
# API — prices
# --------------------------------------------------------------------------

@app.route("/api/prices/<ticker>")
def api_prices(ticker):
    if ticker not in config.TICKERS:
        return jsonify({"error": f"ticker ต้องเป็นหนึ่งใน {config.TICKERS}"}), 400

    csv_path = PRICES_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        return jsonify({"error": f"ไม่พบไฟล์ราคา {csv_path.name} — รัน Phase 0 script ก่อน"}), 404

    df = pd.read_csv(csv_path)
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.strftime("%Y-%m-%d")

    start = request.args.get("start")
    end = request.args.get("end")
    if start:
        df = df[df["Date"] >= start]
    if end:
        df = df[df["Date"] <= end]

    return jsonify(
        {
            "ticker": ticker,
            "dates": df["Date"].tolist(),
            "open": df["Open"].round(2).tolist(),
            "high": df["High"].round(2).tolist(),
            "low": df["Low"].round(2).tolist(),
            "close": df["Close"].round(2).tolist(),
            "volume": df["Volume"].tolist(),
        }
    )


# --------------------------------------------------------------------------
# API — events
# --------------------------------------------------------------------------

@app.route("/api/events")
def api_events_get():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "ต้องระบุ ?ticker="}), 400
    if ticker not in config.TICKERS:
        return jsonify({"error": f"ticker ต้องเป็นหนึ่งใน {config.TICKERS}"}), 400
    return jsonify(events_store.list_events_for_ticker(ticker))


@app.route("/api/events", methods=["POST"])
def api_events_post():
    payload = request.get_json(force=True, silent=True) or {}
    kind = (payload.get("kind") or "").strip()
    date = (payload.get("date") or "").strip()
    headline = (payload.get("headline") or "").strip()
    ticker = (payload.get("ticker") or "").strip() or None

    if kind not in events_store.KINDS:
        return jsonify({"error": f"kind ต้องเป็นหนึ่งใน {events_store.KINDS}"}), 400
    if not date:
        return jsonify({"error": "date ห้ามว่าง (YYYY-MM-DD)"}), 400
    if not headline:
        return jsonify({"error": "headline ห้ามว่าง"}), 400

    date_min, date_max = config.price_date_range()
    if not (date_min <= date <= date_max):
        return jsonify({"error": f"date ต้องอยู่ในช่วงที่มีข้อมูลราคา ({date_min} .. {date_max})"}), 400

    try:
        if kind == "c":
            record = events_store.add_macro_event(date, headline)
        else:
            if ticker not in config.TICKERS:
                return jsonify({"error": f"event แบบ B ต้องระบุ ticker หนึ่งใน {config.TICKERS}"}), 400
            record = events_store.add_company_event(date, headline, ticker)
    except Exception as e:  # noqa: BLE001 — ส่ง error กลับเป็น JSON ให้ UI แสดง ไม่ให้ 500 เปล่าๆ
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500

    return jsonify(record)


@app.route("/api/experiments")
def api_experiments():
    return jsonify(events_store.list_all_events())


# --------------------------------------------------------------------------
# API — rules
# --------------------------------------------------------------------------

@app.route("/api/rules")
def api_rules():
    n = request.args.get("version", type=int)
    try:
        n = n if n is not None else rule_versions.latest_version()
        return jsonify(rule_versions.load_version(n))
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/rules/save", methods=["POST"])
def api_rules_save():
    payload = request.get_json(force=True, silent=True) or {}
    table = payload.get("table")
    description = (payload.get("description") or "").strip()

    if not isinstance(table, list):
        return jsonify({"error": "ต้องส่ง table เป็น list ของ {a,b,c,decision}"}), 400

    try:
        result = rule_versions.save_new_version(table, description=description)
    except (ValueError, FileExistsError) as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
