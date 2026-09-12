"""
Shared helpers สำหรับ collect_{source}.py ทุกไฟล์ — path, resumable log, metadata index
เขียนรวมไว้ที่นี่เพื่อไม่ให้แต่ละ collector ต้องเขียนกลไก resume/log ซ้ำกัน (ตัว logic การ
ดึงข่าวจริงของแต่ละ source ยังคงแยกไฟล์กันชัดเจนตามที่กำหนด)

11 GICS sector ETF — ใช้ list เดียวกับที่ `src/s4_sentiment.py` (Model C จริง) ใช้เทรนอยู่แล้ว
ไม่ได้กำหนดขึ้นใหม่ (ดูตัวแปร SECTORS ในไฟล์นั้น)
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = SANDBOX_DIR / "data" / "sector_news_raw"
PROCESSED_DIR = SANDBOX_DIR / "data" / "sector_news_processed"
INDEX_PATH = PROCESSED_DIR / "index.csv"
LOG_PATH = SANDBOX_DIR / "data" / "collection_log.jsonl"

SECTOR_ETFS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]

# GICS sector name (ตามที่ Wikipedia ใช้จริง ยืนยันด้วยการดึงตารางจริงแล้ว — ดู
# experiments/log.md) -> sector ETF — mapping มาตรฐานของ State Street Select Sector SPDRs
# (1 ETF ต่อ 1 GICS sector พอดี ไม่ใช่ค่าที่เดาเอง)
GICS_SECTOR_TO_ETF = {
    "Information Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Energy": "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

INDEX_FIELDNAMES = [
    "source", "item_id", "date", "sector_etf", "url", "sentiment_score", "word_count", "raw_path",
]

_SP500_CACHE_PATH = PROCESSED_DIR / ".sp500_ticker_sector_cache.json"


def load_ticker_to_etf_map(max_cache_age_days: int = 7) -> dict:
    """คืน {ticker: sector_etf} ของทุกบริษัทใน S&P500 ปัจจุบัน — ใช้ derive sector จาก
    ticker ที่ข่าวพูดถึงจริง (แม่นกว่า topic/category ที่ provider ให้มาเอง) ดึงจาก Wikipedia
    ผ่าน fetch_sp500_table() เดียวกับที่ Phase 0 ใช้ (ยืนยันแล้วว่าทำงานถูก) cache ไว้ในไฟล์
    local (ไม่ commit — ใน sector_news_processed/ แต่ชื่อขึ้นต้นด้วย . และไม่อยู่ใน
    INDEX_FIELDNAMES ไม่ใช่ deliverable) กัน fetch Wikipedia ซ้ำทุกครั้งที่รัน collector"""
    import json as _json
    import time as _time

    if _SP500_CACHE_PATH.exists():
        age_days = (_time.time() - _SP500_CACHE_PATH.stat().st_mtime) / 86400
        if age_days < max_cache_age_days:
            return _json.loads(_SP500_CACHE_PATH.read_text(encoding="utf-8"))

    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phase0_validate_universe import fetch_sp500_table  # noqa: E402

    df = fetch_sp500_table()
    mapping = {}
    for _, row in df.iterrows():
        sector = row["GICS Sector"]
        etf = GICS_SECTOR_TO_ETF.get(sector)
        if etf:
            mapping[row["Symbol"]] = etf

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    _SP500_CACHE_PATH.write_text(_json.dumps(mapping, indent=2), encoding="utf-8")
    return mapping


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_done_ids(source: str) -> set:
    """อ่าน collection_log.jsonl คืน set ของ item_id ที่ source นี้ทำสำเร็จไปแล้ว (status
    == "success") — ใช้ skip รายการที่เคยดึงแล้วตอน resume รันข้ามวัน"""
    done = set()
    if not LOG_PATH.exists():
        return done
    with LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("source") == source and rec.get("status") == "success":
                done.add(rec["item_id"])
    return done


def log_result(source: str, item_id: str, status: str, detail: str = "") -> None:
    """Append 1 บรรทัดลง collection_log.jsonl — เรียกทุกครั้งหลังพยายามดึง 1 รายการ ไม่ว่า
    จะสำเร็จหรือ error (status="success"|"error") เพื่อ track progress ครบทุก attempt"""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "source": source,
        "item_id": item_id,
        "timestamp": now_iso(),
        "status": status,
        "detail": detail,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_index_rows(rows: list) -> None:
    """Append แถว metadata (ไม่มี raw text) ลง sector_news_processed/index.csv — สร้างไฟล์ +
    header ถ้ายังไม่มี"""
    if not rows:
        return
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not INDEX_PATH.exists()
    with INDEX_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDNAMES)
        if is_new:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in INDEX_FIELDNAMES})


def write_raw_jsonl(source: str, sector_etf: str, date_str: str, records: list) -> Path:
    """เขียน raw record (มีเนื้อหาเต็ม) ลง sector_news_raw/{source}/{sector_etf}/{date}.jsonl
    — โฟลเดอร์นี้อยู่ใน .gitignore ทั้งก้อน ห้าม commit เด็ดขาด คืน path ที่เขียน (relative
    ต่อ sandbox/ สำหรับเก็บใน index.csv)"""
    out_dir = RAW_DIR / source / sector_etf
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.jsonl"
    with out_path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out_path.relative_to(SANDBOX_DIR)
