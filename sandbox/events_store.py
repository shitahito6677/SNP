"""
Event store — Phase 2/3 "manual event injection": ผู้ใช้พิมพ์ headline เองในหน้า Events
แล้วเรียก Model B/C (stub ตอนนี้) เพื่อได้ class/score ผูกกับวันที่ เก็บไว้เป็น "event" ที่
หน้า Dashboard เอาไปวาดเป็น marker บนกราฟราคา และหน้า Experiments เอาไปแสดงเป็นประวัติ

Event มี 2 แบบ:
    - "macro"   : ข่าวมหภาค/FOMC ผ่าน Model C — กระทบทุก ticker แต่ "ยังไง" ขึ้นกับ sector
                  ของแต่ละ ticker ดังนั้นเก็บผลแยกต่อ ticker ไว้ในนี้เลย (per_ticker)
                  เวลาวาดบนกราฟ ticker ไหนก็ใช้ผลของ ticker นั้น (เส้นแนวตั้งจะโผล่ทุกกราฟ
                  เหมือนกัน แต่สี/score อาจต่างกันเพราะคนละ sector)
    - "company" : ข่าวรายบริษัท ผ่าน Model B — ผูกกับ ticker เดียว โผล่แค่กราฟของ ticker นั้น

เก็บเป็น JSON Lines ที่ sandbox/data/events/events.jsonl (append-only, gitignored)
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sandbox import config
from sandbox.inference import model_b, model_c

EVENTS_PATH = Path(__file__).resolve().parent / "data" / "events" / "events.jsonl"

KINDS = ("macro", "company")


def _append(record: dict) -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def add_macro_event(date: str, headline: str) -> dict:
    """รัน Model C แยกต่อ sector ของทั้ง 5 ticker ใน universe แล้วเก็บเป็น 1 event เดียว
    ที่มีผลต่อ ticker แยกกัน (per_ticker) — เพราะ Model C เทรนแยกตาม GICS sector จริงๆ
    ไม่ใช่ค่าเดียวกันทุก sector"""
    per_ticker = {}
    for ticker in config.TICKERS:
        etf = config.ticker_to_etf(ticker)
        per_ticker[ticker] = model_c.predict(headline, etf)

    record = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "kind": "macro",
        "date": date,
        "headline": headline,
        "per_ticker": per_ticker,
    }
    _append(record)
    return record


def add_company_event(date: str, headline: str, ticker: str) -> dict:
    if ticker not in config.TICKERS:
        raise ValueError(f"ticker ต้องเป็นหนึ่งใน {config.TICKERS}")

    result = model_b.predict(headline, ticker)
    record = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "kind": "company",
        "date": date,
        "headline": headline,
        "ticker": ticker,
        "class": result["class"],
        "score": result["score"],
        "is_stub": result["is_stub"],
    }
    _append(record)
    return record


def _load_all() -> list:
    if not EVENTS_PATH.exists():
        return []
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def list_events_for_ticker(ticker: str) -> dict:
    """คืน dict {"macro": [...], "company": [...]} สำหรับวาดบนกราฟของ ticker เดียว
    macro event ทุกอันโผล่ (ใช้ per_ticker[ticker] เป็น class/score) company event
    เฉพาะอันที่ ticker ตรงกัน"""
    all_events = _load_all()
    macro = []
    for e in all_events:
        if e["kind"] != "macro":
            continue
        result = e["per_ticker"].get(ticker)
        if result is None:
            continue
        macro.append(
            {
                "id": e["id"],
                "date": e["date"],
                "headline": e["headline"],
                "class": result["class"],
                "score": result["score"],
                "is_stub": result["is_stub"],
            }
        )
    company = [e for e in all_events if e["kind"] == "company" and e.get("ticker") == ticker]
    return {"macro": macro, "company": company}


def list_all_events(limit: int = 100) -> list:
    """คืน event ทั้งหมด (ใหม่สุดก่อน) สำหรับหน้า Experiments — ไม่กรองตาม ticker"""
    all_events = _load_all()
    return list(reversed(all_events))[:limit]
