"""
Bulk CSV upload for manual events — parse + validate a CSV of events before committing,
then loop over the valid rows calling `events_store.add_company_event()` /
`add_macro_event()` exactly like the single-event form does. Same rules as manual
single-row injection, no exceptions: `source="manual"` always, written to the same
`sandbox/data/manual_events.csv` (never the real training data), B rejected for a ticker
without company news (server-side, same check `add_company_event` already does).

CSV columns required: date, ticker, type, headline
    - type: "B" or "C" (case-insensitive) — B = company news (Model B, needs ticker),
      C = macro news (Model C, applies to every ticker in the universe — ticker column
      ignored/optional for these rows)
"""

import csv
import io

from sandbox import config, events_store

REQUIRED_COLUMNS = {"date", "ticker", "type", "headline"}


def _validate_row(row_num: int, row: dict) -> dict:
    """คืน dict {row_num, date, ticker, type, headline, valid, error} — แค่ validate
    ไม่เขียนอะไรลง disk (ใช้ร่วมกันทั้ง preview และ commit)"""
    date = (row.get("date") or "").strip()
    ticker = (row.get("ticker") or "").strip().upper()
    type_raw = (row.get("type") or "").strip().lower()
    headline = (row.get("headline") or "").strip()

    result = {
        "row_num": row_num,
        "date": date,
        "ticker": ticker,
        "type": type_raw,
        "headline": headline,
        "valid": True,
        "error": None,
    }

    if type_raw not in ("b", "c"):
        result["valid"] = False
        result["error"] = f"type ต้องเป็น 'B' หรือ 'C' (ได้ {row.get('type')!r})"
        return result

    if not date:
        result["valid"] = False
        result["error"] = "date ห้ามว่าง"
        return result

    date_min, date_max = config.price_date_range()
    if not (date_min <= date <= date_max):
        result["valid"] = False
        result["error"] = f"date ต้องอยู่ในช่วง {date_min}..{date_max}"
        return result

    if not headline:
        result["valid"] = False
        result["error"] = "headline ห้ามว่าง"
        return result

    if type_raw == "b":
        if not ticker:
            result["valid"] = False
            result["error"] = "type=B ต้องระบุ ticker"
            return result
        if ticker not in config.TICKERS:
            result["valid"] = False
            result["error"] = f"ticker ต้องเป็นหนึ่งใน {config.TICKERS}"
            return result
        if not config.has_company_news(ticker):
            result["valid"] = False
            result["error"] = f"{ticker} ไม่มี company-level news (ปุ่ม B ถูก disable สำหรับ ticker นี้)"
            return result

    return result


def parse_and_validate(csv_text: str) -> dict:
    """Parse CSV text -> {rows: [...], valid_count, error_count, file_error} ไม่เขียนอะไรลง disk"""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return {"rows": [], "valid_count": 0, "error_count": 0, "file_error": "ไฟล์ว่างเปล่าหรืออ่านไม่ได้"}

    header = {c.strip().lower() for c in reader.fieldnames}
    missing_cols = REQUIRED_COLUMNS - header
    if missing_cols:
        return {
            "rows": [],
            "valid_count": 0,
            "error_count": 0,
            "file_error": f"ไฟล์ขาดคอลัมน์: {sorted(missing_cols)} (ต้องมีครบ {sorted(REQUIRED_COLUMNS)})",
        }

    rows = []
    for i, raw_row in enumerate(reader, start=2):  # แถว 1 = header, ข้อมูลเริ่มแถว 2
        normalized = {(k or "").strip().lower(): v for k, v in raw_row.items()}
        rows.append(_validate_row(i, normalized))

    valid_count = sum(1 for r in rows if r["valid"])
    return {
        "rows": rows,
        "valid_count": valid_count,
        "error_count": len(rows) - valid_count,
        "file_error": None,
    }


def commit_valid_rows(csv_text: str) -> dict:
    """Parse + validate อีกรอบ (ไม่เชื่อผลจาก client เก่า เผื่อไฟล์เปลี่ยนระหว่างทาง) แล้ว
    loop เรียก predict() ทีละแถวเหมือนฟอร์มเดี่ยวทุกอย่าง — เฉพาะแถวที่ valid แถวที่ error
    ถูกข้าม ไม่ทำให้ทั้งไฟล์ fail (partial success ตั้งใจ)"""
    parsed = parse_and_validate(csv_text)
    if parsed["file_error"]:
        return {"success": [], "failed": [], "file_error": parsed["file_error"]}

    success, failed = [], []
    for row in parsed["rows"]:
        if not row["valid"]:
            failed.append({"row_num": row["row_num"], "error": row["error"]})
            continue
        try:
            if row["type"] == "c":
                record = events_store.add_macro_event(row["date"], row["headline"])
            else:
                record = events_store.add_company_event(row["date"], row["headline"], row["ticker"])
            success.append({"row_num": row["row_num"], "record": record})
        except Exception as e:  # noqa: BLE001 — เก็บ error ต่อแถว ไม่ให้แถวเดียวล้มทั้งไฟล์
            failed.append({"row_num": row["row_num"], "error": f"{type(e).__name__}: {e}"})

    return {"success": success, "failed": failed, "file_error": None}
