"""
Experiment persistence (Phase 5) — SQLite ไฟล์เดียว `sandbox/experiments.db`
(gitignored, local, regenerable) ตาราง `experiments` ตาม schema ที่กำหนด

"รัน experiment" หมายถึง: เลือก rule version + ticker_set + date range แล้วสแกน
`sandbox/data/manual_events.csv` หา (ticker, date) ที่มี**ทั้ง** event แบบ B (company) และ C
(macro) ในวันเดียวกัน (คู่ที่ไม่ครบ B+C ข้ามไปเลย ไม่เดา/ไม่ fallback) คำนวณ Model A เพิ่มจาก
`model_a.predict(ticker, date)` แล้ว lookup decision จาก `combine(a, b, c, rule_path)`
เก็บผลเป็น `decisions_json` — list ของ {ticker, date, a, b, c, decision}

หมายเหตุ: นี่คือ sandbox สำหรับทดสอบว่า ensemble logic ทำงานยังไงกับ event ที่ inject เอง
(Phase 3) **ไม่ใช่ backtest ผลตอบแทนจริง** — ถ้าวันที่ในช่วงที่เลือกไม่มี event คู่ B+C ให้
เลย decisions_json จะว่างเปล่า (ไม่ fabricate ข้อมูลขึ้นมา)
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sandbox import config, events_store
from sandbox.engine import simulate
from sandbox.engine.combine import combine
from sandbox.inference import model_a
from sandbox.rules.versions import RULES_DIR

STRATEGY_PREFIX = "strategy:"  # rule_version column reused to tag strategy runs (see run_strategy_experiment)

DB_PATH = Path(__file__).resolve().parent / "experiments.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    rule_version TEXT NOT NULL,
    ticker_set TEXT NOT NULL,
    date_range_start DATE NOT NULL,
    date_range_end DATE NOT NULL,
    decisions_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    notes TEXT
)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def _rule_path_for_version(rule_version: str) -> Path:
    """'v1' -> sandbox/rules/rule_v1.json — validate ว่าไฟล์มีอยู่จริงก่อน (ไม่เดา)"""
    if not rule_version.startswith("v") or not rule_version[1:].isdigit():
        raise ValueError(f"rule_version ต้องเป็นรูปแบบ 'v<เลข>' เช่น 'v1' ไม่ใช่ {rule_version!r}")
    path = RULES_DIR / f"rule_{rule_version}.json"
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบ rule version {rule_version} ({path})")
    return path


def compute_decisions(rule_version: str, ticker_set: list, start: str, end: str) -> list:
    """สแกน manual_events.csv หาคู่ (ticker,date) ที่มีทั้ง B และ C แล้วรัน combine()
    คืน list ของ decision record — ข้ามคู่ที่ไม่ครบ B+C (ไม่ fallback/เดา)"""
    rule_path = _rule_path_for_version(rule_version)

    rows = events_store.load_events_in_range(start, end, ticker_set)
    by_key = {}  # (ticker, date) -> {"b": class, "c": class}
    for r in rows:
        key = (r["ticker"], r["date"])
        by_key.setdefault(key, {})[r["kind"]] = r["class"]

    decisions = []
    for (ticker, date), kinds in sorted(by_key.items()):
        if "b" not in kinds or "c" not in kinds:
            continue  # ไม่ครบ B+C สำหรับ (ticker,date) นี้ — ข้าม ไม่เดา
        a_result = model_a.predict(ticker, date)
        decision = combine(a_result["class"], kinds["b"], kinds["c"], str(rule_path))
        decisions.append(
            {
                "ticker": ticker,
                "date": date,
                "a": a_result["class"],
                "b": kinds["b"],
                "c": kinds["c"],
                "decision": decision,
            }
        )
    return decisions


def run_experiment(rule_version: str, ticker_set: list, start: str, end: str, notes: str = "") -> dict:
    invalid = [t for t in ticker_set if t not in config.TICKERS]
    if invalid:
        raise ValueError(f"ticker ไม่อยู่ใน universe: {invalid}")
    if not ticker_set:
        raise ValueError("ticker_set ห้ามว่าง")
    if start > end:
        raise ValueError(f"date_range_start ({start}) ต้องไม่มากกว่า date_range_end ({end})")

    decisions = compute_decisions(rule_version, ticker_set, start, end)

    record = {
        "experiment_id": str(uuid.uuid4()),
        "rule_version": rule_version,
        "ticker_set": json.dumps(ticker_set),
        "date_range_start": start,
        "date_range_end": end,
        "decisions_json": json.dumps(decisions),
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "notes": notes,
    }

    conn = _connect()
    with conn:
        conn.execute(
            """INSERT INTO experiments
               (experiment_id, rule_version, ticker_set, date_range_start, date_range_end,
                decisions_json, created_at, notes)
               VALUES (:experiment_id, :rule_version, :ticker_set, :date_range_start,
                       :date_range_end, :decisions_json, :created_at, :notes)""",
            record,
        )
    conn.close()

    return {**record, "ticker_set": ticker_set, "decisions": decisions}


def run_strategy_experiment(
    strategy_name: str, ticker_set: list, start: str, end: str, initial_cash: float, notes: str = ""
) -> dict:
    """เหมือน run_experiment() แต่รัน Strategy engine (sandbox/engine/simulate.py) แทน
    rule-lookup — เก็บลงตาราง `experiments` เดียวกันเลย (schema เดียวกันเป๊ะ ไม่ต้อง migrate
    อะไร) โดยผูก `rule_version = "strategy:<strategy_name>"` เป็นตัวแยกประเภทตอนอ่านกลับ
    (ดู _row_to_dict) — decisions_json เก็บผลจำลองเต็ม (trade_log, portfolio_value_series,
    ฯลฯ) แทนที่จะเป็น list ของ decision แบบ rule-lookup"""
    result = simulate.run_simulation(strategy_name, ticker_set, start, end, initial_cash)

    record = {
        "experiment_id": str(uuid.uuid4()),
        "rule_version": f"{STRATEGY_PREFIX}{strategy_name}",
        "ticker_set": json.dumps(ticker_set),
        "date_range_start": start,
        "date_range_end": end,
        "decisions_json": json.dumps(result),
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "notes": notes,
    }

    conn = _connect()
    with conn:
        conn.execute(
            """INSERT INTO experiments
               (experiment_id, rule_version, ticker_set, date_range_start, date_range_end,
                decisions_json, created_at, notes)
               VALUES (:experiment_id, :rule_version, :ticker_set, :date_range_start,
                       :date_range_end, :decisions_json, :created_at, :notes)""",
            record,
        )
    conn.close()

    return {**record, "ticker_set": ticker_set, **result}


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["ticker_set"] = json.loads(d["ticker_set"])
    is_strategy = d["rule_version"].startswith(STRATEGY_PREFIX)
    d["is_strategy"] = is_strategy
    if is_strategy:
        strategy_result = json.loads(d["decisions_json"])
        d["strategy_result"] = strategy_result
        d["decisions"] = strategy_result.get("trade_log", [])  # ให้ len(decisions) ยังใช้ได้
    else:
        d["decisions"] = json.loads(d["decisions_json"])
    return d


def list_experiments(limit: int = 100) -> list:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_experiment(experiment_id: str) -> dict:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise KeyError(f"ไม่พบ experiment_id={experiment_id}")
    return _row_to_dict(row)


def diff_experiments(id_a: str, id_b: str) -> dict:
    """เทียบ decisions ของ 2 experiment คีย์ด้วย (ticker, date) — คืน rows ที่ decision ต่างกัน,
    rows ที่เหมือนกัน, และ rows ที่มีแค่ฝั่งเดียว"""
    exp_a = get_experiment(id_a)
    exp_b = get_experiment(id_b)

    if exp_a["is_strategy"] or exp_b["is_strategy"]:
        raise ValueError(
            "diff รองรับเฉพาะ rule-lookup experiment (decision ต่อ (ticker,date)) เท่านั้น — "
            "strategy run เก็บ trade log/portfolio value ซึ่งเทียบแบบนี้ไม่ได้ "
            f"(experiment_a.is_strategy={exp_a['is_strategy']}, experiment_b.is_strategy={exp_b['is_strategy']})"
        )

    map_a = {(d["ticker"], d["date"]): d for d in exp_a["decisions"]}
    map_b = {(d["ticker"], d["date"]): d for d in exp_b["decisions"]}

    all_keys = sorted(set(map_a) | set(map_b))
    differs, same, only_a, only_b = [], [], [], []

    for key in all_keys:
        in_a, in_b = key in map_a, key in map_b
        if in_a and in_b:
            if map_a[key]["decision"] != map_b[key]["decision"]:
                differs.append(
                    {
                        "ticker": key[0],
                        "date": key[1],
                        "decision_a": map_a[key]["decision"],
                        "decision_b": map_b[key]["decision"],
                    }
                )
            else:
                same.append({"ticker": key[0], "date": key[1], "decision": map_a[key]["decision"]})
        elif in_a:
            only_a.append(map_a[key])
        else:
            only_b.append(map_b[key])

    return {
        "experiment_a": {"experiment_id": id_a, "rule_version": exp_a["rule_version"]},
        "experiment_b": {"experiment_id": id_b, "rule_version": exp_b["rule_version"]},
        "differs": differs,
        "same": same,
        "only_in_a": only_a,
        "only_in_b": only_b,
    }
