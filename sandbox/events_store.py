"""
Manual event store (Phase 3) — ผู้ใช้พิมพ์ headline เองในหน้า Events แล้วเรียก Model B
(ticker เดียว) หรือ Model C (ทุก ticker ใน universe, แยกตาม sector) เก็บผลเป็นแถวใน
`sandbox/data/manual_events.csv` — CSV เดียว **แยกจาก dataset จริงของ Model C โดยเด็ดขาด**
(ของจริงอยู่ที่ `data/raw/macro_news_raw.parquet` / `data/processed/*.parquet` ที่ root
ของ repo คนละไฟล์ คนละ format คนละโฟลเดอร์ทั้งหมด — ดู sandbox/OVERNIGHT_LOG.md สำหรับ
verification ว่าไม่ปนกัน)

ทุกแถวมี `source` = "manual" เสมอ (บังคับตาม spec) เพื่อให้ใครก็ตามที่มาอ่านไฟล์นี้ทีหลัง
รู้ทันทีว่าไม่ใช่ข้อมูลจริง แม้จะเผลอเอาไปรวมกับที่อื่น

Schema (1 แถว = 1 (event, ticker) pair — event แบบ "c" กระทบทุก ticker เลยมีหลายแถว/event
แต่ event แบบ "b" มีแค่ 1 แถว):
    id, created_at, source, kind (b|c), ticker, date, headline, class, score, is_stub
"""

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sandbox import config
from sandbox.inference import model_b, model_c

MANUAL_EVENTS_PATH = Path(__file__).resolve().parent / "data" / "manual_events.csv"

FIELDNAMES = [
    "id", "created_at", "source", "kind", "ticker", "date", "headline",
    "class", "score", "is_stub",
]

KINDS = ("b", "c")  # b = company news (Model B, 1 ticker) / c = macro news (Model C, ทุก ticker)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ensure_file() -> None:
    MANUAL_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MANUAL_EVENTS_PATH.exists():
        with MANUAL_EVENTS_PATH.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def _append_rows(rows: list) -> None:
    _ensure_file()
    with MANUAL_EVENTS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        for r in rows:
            writer.writerow(r)


def add_company_event(date: str, headline: str, ticker: str) -> dict:
    """kind = 'b' — Model B, โผล่แค่ ticker เดียว"""
    if ticker not in config.TICKERS:
        raise ValueError(f"ticker ต้องเป็นหนึ่งใน {config.TICKERS}")
    if not config.has_company_news(ticker):
        raise ValueError(
            f"{ticker} ไม่มี company-level news ให้ inject event แบบ B ได้ (ปุ่ม B ควรถูก "
            "disable ไปแล้วตั้งแต่ฝั่ง UI — เห็น error นี้แปลว่ามีคน bypass client-side check)"
        )

    result = model_b.predict(headline, ticker)
    row = {
        "id": str(uuid.uuid4()),
        "created_at": _now_iso(),
        "source": "manual",
        "kind": "b",
        "ticker": ticker,
        "date": date,
        "headline": headline,
        "class": result["class"],
        "score": result["score"],
        "is_stub": result["is_stub"],
    }
    _append_rows([row])
    return {"kind": "b", "rows": [row]}


def add_macro_event(date: str, headline: str) -> dict:
    """kind = 'c' — Model C, รันแยกทุก sector ของทั้ง 5 ticker ใน universe เก็บเป็นคนละแถว
    (Model C เทรนแยกตาม GICS sector จริง จึงไม่ควรบังคับ class เดียวกันทุก ticker)"""
    rows = []
    for ticker in config.TICKERS:
        etf = config.ticker_to_etf(ticker)
        result = model_c.predict(headline, etf)
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "source": "manual",
                "kind": "c",
                "ticker": ticker,
                "date": date,
                "headline": headline,
                "class": result["class"],
                "score": result["score"],
                "is_stub": result["is_stub"],
            }
        )
    _append_rows(rows)
    return {"kind": "c", "rows": rows}


def _normalize(row: dict) -> dict:
    """csv.DictReader คืนทุก field เป็น str — แปลง score/is_stub กลับเป็น type ที่ใช้งานได้"""
    row = dict(row)
    row["score"] = float(row["score"])
    row["is_stub"] = row["is_stub"] in ("True", "true", "1")
    return row


def _load_all() -> list:
    _ensure_file()
    with MANUAL_EVENTS_PATH.open(newline="", encoding="utf-8") as f:
        return [_normalize(r) for r in csv.DictReader(f)]


def list_events_for_ticker(ticker: str) -> dict:
    """คืน {"b": [...], "c": [...]} สำหรับวาด marker บนกราฟของ ticker เดียว"""
    all_rows = _load_all()
    b = [r for r in all_rows if r["kind"] == "b" and r["ticker"] == ticker]
    c = [r for r in all_rows if r["kind"] == "c" and r["ticker"] == ticker]
    return {"b": b, "c": c}


def list_all_events(limit: int = 200) -> list:
    """คืนทุกแถว (ใหม่สุดก่อน) สำหรับหน้า Experiments — ไม่กรองตาม ticker"""
    return list(reversed(_load_all()))[:limit]


def load_events_in_range(start: str, end: str, ticker_set: list) -> list:
    """สำหรับ Phase 5 experiment runner — คืนทุกแถวที่ date อยู่ใน [start, end] และ ticker
    อยู่ใน ticker_set"""
    rows = _load_all()
    return [r for r in rows if start <= r["date"] <= end and r["ticker"] in ticker_set]
