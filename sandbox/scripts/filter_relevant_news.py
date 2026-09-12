"""
filter_relevant_news.py — คัดกรอง (tag ไม่ลบ/ไม่ทับข้อมูลเดิม) ข่าวใน
sandbox/data/sector_news_processed/index.csv ด้วยกฎ rule-based ล้วนๆ (ไม่ใช้ LLM):

    1. company_level — เนื้อหาพูดถึง**บริษัทเดียว**ที่ระบุตัวตนได้ชัดเจน (distinct company
       mention == 1) — ใช้ `ticker_sentiment` ตรงๆ สำหรับ Alpha Vantage (structured data
       จริงจาก provider) และ regex ticker pattern + จับคู่ชื่อบริษัท S&P500 กับข้อความ
       (headline+summary) สำหรับ Finnhub (ไม่มี structured field ให้ใช้)
    2. weak_signal   — ไม่มี sector/industry keyword ที่กำหนดเอง (ต่อ 11 sector) เลยแม้แต่
       คำเดียวในเนื้อหา (headline+summary)
    3. mistagged     — ระบุบริษัทที่เนื้อหาพูดถึงได้อย่างน้อย 1 บริษัท แต่**ไม่มีตัวไหนเลย**
       อยู่ใน sector ที่ index.csv tag แถวนั้นไว้ (เทียบกับ sector จริงของบริษัทนั้นจาก S&P500)

เขียนผลเป็นคอลัมน์ใหม่ **ในไฟล์เดิม** (`is_company_level`, `is_weak_signal`, `is_mistagged`,
`n_companies_detected`, `scope`) — ไม่ลบ/ไม่ย้ายคอลัมน์เดิมเลย รันซ้ำได้ปลอดภัย (คำนวณคอลัมน์
tag ใหม่ทับของเดิมทุกครั้ง ไม่ duplicate แถว)

⚠️ ข้อจำกัดที่ต้องรู้ (rule-based ธรรมดา ไม่ใช่ NER จริง):
    - การจับชื่อบริษัทใน Finnhub headline/summary ใช้ whole-word, case-sensitive matching
      กับชื่อบริษัท S&P500 (ตัดคำต่อท้ายองค์กรเช่น "Inc.", "Corp." ออกก่อน) — พลาดได้ทั้ง
      false negative (ชื่อเขียนแบบอื่น, ย่อ) และ false positive (ชื่อบริษัทที่ดันเป็นคำ
      อังกฤษทั่วไปด้วย เช่น "Target") ตัวเลขที่ได้จึงเป็น**ประมาณการ**ไม่ใช่ ground truth
    - keyword list ต่อ sector เป็นชุดที่กำหนดเอง (documented ในไฟล์นี้ตรงๆ) ไม่ใช่ทางการจาก
      GICS หรือแหล่งไหน ปรับ/เพิ่มได้ตรงๆ ในโค้ดถ้าคิดว่าควรมีคำอื่นด้วย

รัน (จาก project root): python3 -m sandbox.scripts.filter_relevant_news
"""

import csv
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from sandbox.scripts._sector_news_common import INDEX_PATH, PROCESSED_DIR, load_ticker_to_etf_map

NAME_CACHE_PATH = PROCESSED_DIR / ".sp500_ticker_name_cache.json"

# keyword ต่อ sector (กำหนดเอง — ไม่ใช่มาตรฐานทางการ) ใช้ตัดสิน weak_signal เท่านั้น เคส-
# insensitive ตรวจแค่ "มีคำไหนโผล่บ้างไหม" ไม่ได้ตรวจ context
SECTOR_KEYWORDS = {
    "XLK": ["software", "semiconductor", "chip", "cloud", "artificial intelligence", " ai ",
            "cybersecurity", "data center", "computing", "hardware", "processor", "silicon",
            "app store", "saas", "server"],
    "XLF": ["bank", "insurance", "lending", "loan", "mortgage", "credit", "financial",
            "asset management", "hedge fund", "interest rate", "fintech", "brokerage",
            "investment bank", "capital markets"],
    "XLV": ["drug", "pharma", "biotech", "hospital", "clinical trial", "fda", "medical device",
            "healthcare", "health care", "therapy", "vaccine", "patient", "medicine", "diagnostic"],
    "XLE": ["oil", "gas", "crude", "drilling", "energy", "pipeline", "refinery", "opec",
            "petroleum", "lng", "upstream", "downstream", "barrel"],
    "XLY": ["retail", "e-commerce", "apparel", "restaurant", "automotive", "travel", "hotel",
            "luxury", "consumer spending", "homebuilder", "leisure"],
    "XLP": ["grocery", "beverage", "food", "household products", "tobacco", "supermarket",
            "consumer goods", "staples"],
    "XLI": ["manufacturing", "aerospace", "defense", "construction", "logistics", "freight",
            "industrial", "machinery", "railroad", "shipping", "airline", "transportation"],
    "XLB": ["chemical", "mining", "steel", "metals", "commodities", "materials", "copper",
            "lumber", "packaging", "fertilizer"],
    "XLU": ["utility", "utilities", "electricity", "power grid", "water utility",
            "renewable energy", "solar", "wind power", "electric utility"],
    "XLRE": ["reit", "real estate", "property", "commercial real estate", "residential",
             "office space", "landlord", "leasing"],
    "XLC": ["telecom", "media", "streaming", "social media", "advertising", "broadcasting",
            "wireless", "entertainment", "gaming", "publishing"],
}

CORP_SUFFIX_RE = re.compile(
    r"\s*[,]?\s*(Inc\.?|Incorporated|Corp\.?|Corporation|Co\.?|Company|plc|Ltd\.?|Limited|"
    r"Holdings?|Group|L\.?P\.?|N\.?V\.?|S\.?A\.?|& Co\.?|Class [AB])\.?\s*$",
    re.IGNORECASE,
)
TICKER_MENTION_RE = re.compile(
    r"\((?:NASDAQ|NYSE|NYSEARCA|NASDAQGS|NASDAQCM|OTC)\s*:\s*([A-Z]{1,5})\)"
)


def clean_company_name(name: str) -> str:
    """ตัดคำต่อท้ายองค์กร (Inc./Corp./plc/...) ออก ตัดซ้ำได้หลายชั้น (เช่น 'X Corp, Inc.')"""
    prev = None
    while prev != name:
        prev = name
        name = CORP_SUFFIX_RE.sub("", name).strip()
    return name


def load_ticker_to_name_map(max_cache_age_days: int = 7) -> dict:
    if NAME_CACHE_PATH.exists():
        age_days = (time.time() - NAME_CACHE_PATH.stat().st_mtime) / 86400
        if age_days < max_cache_age_days:
            return json.loads(NAME_CACHE_PATH.read_text(encoding="utf-8"))

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phase0_validate_universe import fetch_sp500_table  # noqa: E402

    df = fetch_sp500_table()
    mapping = dict(zip(df["Symbol"], df["Security"]))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    NAME_CACHE_PATH.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    return mapping


def build_name_matchers(ticker_to_name: dict) -> list:
    """คืน list ของ (ticker, compiled_regex) — คอมไพล์ล่วงหน้าทั้งหมดครั้งเดียว (ไม่ใช่ใน
    loop ต่อบทความ) กันช้า ข้าม ชื่อที่สั้นเกินไปหลังตัด suffix (เสี่ยง false positive สูง)"""
    matchers = []
    for ticker, name in ticker_to_name.items():
        cleaned = clean_company_name(name)
        if len(cleaned) < 4:
            continue
        matchers.append((ticker, re.compile(r"\b" + re.escape(cleaned) + r"\b")))
    return matchers


def detect_companies_from_text(text: str, ticker_to_etf: dict, name_matchers: list) -> set:
    companies = set()
    for m in TICKER_MENTION_RE.finditer(text):
        t = m.group(1)
        if t in ticker_to_etf:
            companies.add(t)
    for ticker, pattern in name_matchers:
        if ticker in companies or ticker not in ticker_to_etf:
            continue
        if pattern.search(text):
            companies.add(ticker)
    return companies


def detect_companies_from_ticker_sentiment(record: dict, ticker_to_etf: dict) -> set:
    return {
        ts["ticker"]
        for ts in record.get("ticker_sentiment", [])
        if ts.get("ticker") in ticker_to_etf
    }


def sector_has_keyword(text_lower: str, sector_etf: str) -> bool:
    keywords = SECTOR_KEYWORDS.get(sector_etf, [])
    return any(kw in text_lower for kw in keywords)


def load_raw_records_by_path(raw_paths: set) -> dict:
    """เปิดแต่ละ raw file แค่ครั้งเดียว (ไม่ใช่ต่อแถว) คืน {path: [record, ...]}"""
    sandbox_dir = Path(__file__).resolve().parent.parent
    cache = {}
    for rel_path in raw_paths:
        full_path = sandbox_dir / rel_path if not rel_path.startswith(str(sandbox_dir)) else Path(rel_path)
        # raw_path ในไฟล์เก็บเป็น "sandbox/data/..." (relative ต่อ sandbox/ เอง จาก
        # write_raw_jsonl) ปรับให้เป็น absolute ให้ถูกจาก SANDBOX_DIR
        full_path = sandbox_dir / rel_path
        records = []
        if full_path.exists():
            with full_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        cache[rel_path] = records
    return cache


def match_record(row: dict, records: list):
    """หา record ที่ตรงกับแถวนี้ใน list ของ record ทั้งหมดในไฟล์เดียวกัน — match ด้วย
    item_id เดียวกับที่ collector เขียนไว้ (finnhub: 'item:{id}', alpha_vantage: 'article:{hash(url)}')"""
    item_id = row["item_id"]
    if item_id.startswith("item:"):
        target = item_id[len("item:"):]
        for rec in records:
            if str(rec.get("id", rec.get("url"))) == target:
                return rec
    elif item_id.startswith("article:"):
        import hashlib

        for rec in records:
            h = "article:" + hashlib.sha256(rec.get("url", "").encode("utf-8")).hexdigest()[:16]
            if h == item_id:
                return rec
    return None


def main():
    ticker_to_etf = load_ticker_to_etf_map()
    ticker_to_name = load_ticker_to_name_map()
    name_matchers = build_name_matchers(ticker_to_name)
    print(f"Loaded {len(ticker_to_etf)} tickers (sector map), {len(name_matchers)} name matchers")

    with INDEX_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        original_fieldnames = list(reader.fieldnames)
        rows = list(reader)
    print(f"Loaded {len(rows)} rows from {INDEX_PATH}")

    raw_paths = {row["raw_path"] for row in rows if row.get("raw_path")}
    records_by_path = load_raw_records_by_path(raw_paths)
    print(f"Opened {len(raw_paths)} raw file(s)")

    tag_counts = Counter()
    for row in rows:
        records = records_by_path.get(row["raw_path"], [])
        rec = match_record(row, records)

        if rec is None:
            row["is_company_level"] = ""
            row["is_weak_signal"] = ""
            row["is_mistagged"] = ""
            row["n_companies_detected"] = ""
            row["scope"] = "raw_not_found"
            tag_counts["raw_not_found"] += 1
            continue

        headline = rec.get("headline") or rec.get("title") or ""
        summary = rec.get("summary") or ""
        text = f"{headline} {summary}"
        text_lower = text.lower()

        if row["source"] == "alpha_vantage":
            companies = detect_companies_from_ticker_sentiment(rec, ticker_to_etf)
        else:
            companies = detect_companies_from_text(text, ticker_to_etf, name_matchers)

        is_company_level = len(companies) == 1
        is_weak_signal = not sector_has_keyword(text_lower, row["sector_etf"])
        company_sectors = {ticker_to_etf[c] for c in companies}
        is_mistagged = bool(companies) and row["sector_etf"] not in company_sectors

        tags = []
        if is_company_level:
            tags.append("company_level")
        if is_weak_signal:
            tags.append("weak_signal")
        if is_mistagged:
            tags.append("mistagged")
        scope = ";".join(tags) if tags else "clean"

        row["is_company_level"] = str(is_company_level)
        row["is_weak_signal"] = str(is_weak_signal)
        row["is_mistagged"] = str(is_mistagged)
        row["n_companies_detected"] = str(len(companies))
        row["scope"] = scope
        tag_counts[scope] += 1

    new_fields = ["is_company_level", "is_weak_signal", "is_mistagged", "n_companies_detected", "scope"]
    fieldnames = original_fieldnames + [f for f in new_fields if f not in original_fieldnames]

    with INDEX_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote tag columns back to {INDEX_PATH}\n")
    print("=== scope breakdown (exact combinations) ===")
    total = len(rows)
    for scope, count in tag_counts.most_common():
        print(f"  {scope:40s} {count:6d}  ({count / total * 100:5.1f}%)")

    print("\n=== per-flag breakdown (rows can have multiple flags) ===")
    for flag in ["is_company_level", "is_weak_signal", "is_mistagged"]:
        n = sum(1 for r in rows if r.get(flag) == "True")
        print(f"  {flag:20s} {n:6d}  ({n / total * 100:5.1f}%)")

    print("\n=== breakdown by source ===")
    for source in ["finnhub", "alpha_vantage"]:
        src_rows = [r for r in rows if r["source"] == source]
        if not src_rows:
            continue
        n = len(src_rows)
        print(f"  {source} (n={n}):")
        for flag in ["is_company_level", "is_weak_signal", "is_mistagged"]:
            cnt = sum(1 for r in src_rows if r.get(flag) == "True")
            print(f"    {flag:20s} {cnt:6d}  ({cnt / n * 100:5.1f}%)")


if __name__ == "__main__":
    main()
