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

from sandbox import config, events_store, experiments_db, historical_data
from sandbox.analytics import indicators
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


def _model_status() -> list:
    """สถานะแยกรายโมเดล (ไม่ใช่แค่ badge รวมทั้งหน้า) — Model C มี 2 มิติแยกกัน: live
    inference (predict() สำหรับ headline ใหม่ ยังเป็น stub) กับ historical data (ข่าวจริง
    477 ข่าวที่ผ่าน pipeline จริงแล้ว เชื่อมต่อ dashboard แล้วจริง ไม่ใช่ stub)"""
    n_historical = historical_data.real_event_count()
    return [
        {
            "key": "A",
            "name": "Model A — Piotroski Fundamental",
            "inference": "stub" if model_a.IS_STUB else "real",
            "data_note": None,
        },
        {
            "key": "B",
            "name": "Model B — FinBERT Company News",
            "inference": "stub" if model_b.IS_STUB else "real",
            "data_note": None,
        },
        {
            "key": "C",
            "name": "Model C — Macro/Sector News",
            "inference": "stub" if model_c.IS_STUB else "real",
            "data_note": (
                f"real historical data connected ({n_historical} FOMC/Beige Book news)"
                if n_historical
                else "historical data file not found"
            ),
        },
    ]


@app.context_processor
def inject_globals():
    date_min, date_max = config.price_date_range()
    return {
        "stub_mode": _probe_stub_mode(),
        "model_status": _model_status(),
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
    return render_template(
        "experiments.html",
        events=events_store.list_all_events(),
        runs=experiments_db.list_experiments(),
        rule_version_options=[f"v{n}" for n in rule_versions.list_versions()],
    )


# --------------------------------------------------------------------------
# API — prices + indicators
# --------------------------------------------------------------------------

def _load_price_df(ticker: str) -> pd.DataFrame:
    """โหลดราคาเต็มช่วง (ไม่ filter วันที่) — ใช้ร่วมกันทั้ง /api/prices และ
    /api/indicators เพราะ indicator (SMA50 ฯลฯ) ต้องคำนวณจากประวัติเต็มก่อน filter ทีหลัง"""
    csv_path = PRICES_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ราคา {csv_path.name} — รัน Phase 0 script ก่อน")
    df = pd.read_csv(csv_path)
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.strftime("%Y-%m-%d")
    return df


def _series_to_json_list(series: pd.Series) -> list:
    """แปลง pandas Series -> list สำหรับ jsonify — NaN ต้องเป็น None (json null) ไม่งั้น
    Python json module จะ emit ตัวหนังสือ `NaN` ดิบๆ ซึ่งไม่ใช่ JSON ที่ถูกต้อง (JS
    JSON.parse จะ error) ปัดเศษ 4 ตำแหน่งให้ payload ไม่ใหญ่เกินจำเป็น"""
    return [None if pd.isna(v) else round(float(v), 4) for v in series]


@app.route("/api/prices/<ticker>")
def api_prices(ticker):
    if ticker not in config.TICKERS:
        return jsonify({"error": f"ticker ต้องเป็นหนึ่งใน {config.TICKERS}"}), 400

    try:
        df = _load_price_df(ticker)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404

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


@app.route("/api/indicators/<ticker>")
def api_indicators(ticker):
    if ticker not in config.TICKERS:
        return jsonify({"error": f"ticker ต้องเป็นหนึ่งใน {config.TICKERS}"}), 400

    try:
        df = _load_price_df(ticker)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404

    # คำนวณจากราคาเต็มช่วงก่อนเสมอ (ดู docstring compute_all) แล้วค่อย filter วันที่ทีหลัง
    df = indicators.compute_all(df)

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
            "sma20": _series_to_json_list(df["sma20"]),
            "sma50": _series_to_json_list(df["sma50"]),
            "rsi14": _series_to_json_list(df["rsi14"]),
            "macd": _series_to_json_list(df["macd"]),
            "macd_signal": _series_to_json_list(df["macd_signal"]),
            "macd_hist": _series_to_json_list(df["macd_hist"]),
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

    # real historical macro news ครอบคลุม 1996-2026 (477 ข่าว) แต่ราคาที่มีมีแค่ 5 ปีล่าสุด —
    # ต้อง bound ด้วย date range เสมอ (default = ทั้งช่วงราคา) ไม่งั้น Plotly จะขยาย x-axis
    # ไปครอบคลุม event ที่อยู่นอกช่วงราคาจนกราฟแท่งเทียนเพี้ยน (มีแค่ 80/477 ข่าวที่อยู่ใน
    # ช่วงราคา 5 ปีล่าสุด — ดู experiments/log.md)
    date_min, date_max = config.price_date_range()
    start = request.args.get("start") or date_min
    end = request.args.get("end") or date_max

    manual = events_store.list_events_for_ticker(ticker)
    real_c = historical_data.load_real_macro_events_for_ticker(ticker)

    # รวม macro (C) event จริง (477 ข่าว FOMC/Beige Book, source="real_historical") เข้ากับ
    # manual C event (source="manual") เรียงตามวันที่ — ก่อนหน้านี้ endpoint นี้คืนแค่ manual
    # อย่างเดียว ทำให้ ticker ที่ไม่เคย inject event เองเห็น C = 0 เสมอ (ดู experiments/log.md)
    c_events = sorted(manual["c"] + real_c, key=lambda e: e["date"])
    c_events = [e for e in c_events if start <= e["date"] <= end]
    b_events = [e for e in manual["b"] if start <= e["date"] <= end]

    return jsonify({"b": b_events, "c": c_events})


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


# --------------------------------------------------------------------------
# API — experiments (Phase 5: SQLite persistence + diff)
# --------------------------------------------------------------------------

@app.route("/api/experiments/runs", methods=["POST"])
def api_experiments_run():
    payload = request.get_json(force=True, silent=True) or {}
    rule_version = (payload.get("rule_version") or "").strip()
    ticker_set = payload.get("ticker_set") or []
    start = (payload.get("start") or "").strip()
    end = (payload.get("end") or "").strip()
    notes = (payload.get("notes") or "").strip()

    if not rule_version:
        return jsonify({"error": "rule_version ห้ามว่าง (เช่น 'v1')"}), 400
    if not start or not end:
        return jsonify({"error": "start/end ห้ามว่าง (YYYY-MM-DD)"}), 400

    try:
        record = experiments_db.run_experiment(rule_version, ticker_set, start, end, notes)
    except (ValueError, FileNotFoundError) as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400

    return jsonify(record)


@app.route("/api/experiments/runs")
def api_experiments_runs_list():
    return jsonify(experiments_db.list_experiments())


@app.route("/api/experiments/diff")
def api_experiments_diff():
    id_a = request.args.get("a")
    id_b = request.args.get("b")
    if not id_a or not id_b:
        return jsonify({"error": "ต้องระบุ ?a=<experiment_id>&b=<experiment_id>"}), 400
    try:
        return jsonify(experiments_db.diff_experiments(id_a, id_b))
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


if __name__ == "__main__":
    app.run(debug=True, port=5050)
