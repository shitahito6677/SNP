"""
fix_sector_tags.py — สำหรับแถวที่ `filter_relevant_news.py` ติด `is_mistagged=True` และมี
บริษัทเดียวที่ระบุได้ชัดเจน (ไม่ ambiguous) ดึง sector จริงจาก Finnhub `company-profile2`
(field `finnhubIndustry`) แล้วแก้ `sector_etf` ให้ถูก — **เก็บค่าเดิมไว้เป็น
`original_sector_etf`** (ไม่ลบทิ้ง ย้อนดูได้เสมอ) รันซ้ำได้ปลอดภัย (แถวที่แก้แล้วจะไม่ใช่
`is_mistagged=True` อีกในรอบถัดไปเพราะ sector ใหม่ตรงกับบริษัทแล้ว — ข้ามให้เอง)

ตาม "ห้ามเดา" ที่สั่งไว้ — ข้าม (ไม่แก้ ไม่เดา) แถวที่เข้าเงื่อนไขข้อใดข้อหนึ่งต่อไปนี้:
    1. detect ได้มากกว่า 1 บริษัทในแถวนั้น (ไม่รู้จะใช้ตัวไหนเป็นตัวแก้ — ambiguous)
    2. เรียก `company-profile2` แล้วไม่เจอ profile จริง (response ว่างเปล่า/ไม่มี ticker)
    3. `finnhubIndustry` ที่ได้ map เข้า 1 ใน 11 sector ETF ด้วย keyword rule ที่กำหนดไว้ไม่ได้
       (Finnhub ใช้ industry ละเอียดกว่า GICS sector มาก ไม่ตรงกันเป๊ะเสมอไป)

รัน (จาก project root): python3 -m sandbox.scripts.fix_sector_tags
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from sandbox.scripts._sector_news_common import INDEX_PATH, load_ticker_to_etf_map
from sandbox.scripts.filter_relevant_news import (
    build_name_matchers,
    detect_companies_from_text,
    detect_companies_from_ticker_sentiment,
    load_raw_records_by_path,
    load_ticker_to_name_map,
    match_record,
)

FINNHUB_PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"
RATE_LIMIT_SLEEP = 1.1  # Finnhub free tier = 60 req/min
HEADERS = {"User-Agent": "sandbox-research-script/1.0 (contact: boeing6677@gmail.com)"}

# finnhubIndustry (ข้อความอิสระ ละเอียดกว่า GICS) -> sector ETF — จับคู่ด้วย keyword แบบ
# rule-based เดียวกับ SECTOR_KEYWORDS ใน filter_relevant_news.py ถ้าไม่มี keyword ไหนตรงเลย
# ถือว่า map ไม่ได้ (ไม่เดา — ข้ามแถวนั้นไป) เรียงจากเจาะจงไปกว้าง กันคำที่ overlap กัน
# หมายเหตุ: matching เป็น \bword\b (whole word) เสมอ (ดูเหตุผลใน map_industry_to_etf) —
# ต้องใส่ทั้งรูปเอกพจน์/พหูพจน์ที่ Finnhub ใช้จริงแยกกัน เจอช่องว่างจริงจากการรัน (ไม่ใช่เดา
# ล่วงหน้า): "semiconductor"→"Semiconductors", "chemical"→"Chemicals",
# "pharmaceutical"→"Pharmaceuticals", "bank"→"Banking", "telecom"→"Telecommunication",
# "auto"→"Automobiles" ไม่ match กันเพราะเป็นคนละคำ (word boundary กันไว้ตรงๆ ตามที่ตั้งใจ)
INDUSTRY_KEYWORD_TO_ETF = [
    (["semiconductor", "semiconductors", "software", "technology", "internet", "it services",
      "electronic"], "XLK"),
    (["bank", "banking", "financial services", "insurance", "capital markets", "asset management",
      "consumer finance", "credit"], "XLF"),
    (["pharmaceutical", "pharmaceuticals", "biotechnology", "health care", "healthcare", "medical",
      "drug manufacturer", "hospital"], "XLV"),
    (["oil", "gas", "energy", "petroleum", "drilling"], "XLE"),
    (["retail", "apparel", "restaurant", "auto", "automobile", "automobiles", "leisure", "hotel",
      "travel", "homebuilding", "specialty retail"], "XLY"),
    (["consumer staples", "food", "beverage", "tobacco", "household", "grocery"], "XLP"),
    (["industrial", "aerospace", "defense", "airline", "transportation", "logistics", "machinery",
      "construction", "railroad", "commercial services", "electrical equipment", "road & rail",
      "road and rail"], "XLI"),
    (["chemical", "chemicals", "mining", "metals", "materials", "steel", "packaging"], "XLB"),
    (["utilities", "utility", "electric power", "water"], "XLU"),
    (["real estate", "reit"], "XLRE"),
    (["telecom", "telecommunication", "telecommunications", "media", "communication", "entertainment",
      "broadcasting", "publishing"], "XLC"),
]

# "Consumer products" (Finnhub) เจอตัวอย่างจริงที่ครอบคลุมทั้ง XLY (Garmin, Lennar — consumer
# electronics/homebuilder) และ XLP (Procter & Gamble — staples) ปน — ไม่ map ให้เด็ดขาด
# (ambiguous จริง ไม่ใช่ช่องว่างที่ควรเติม — ดู experiments/log.md)


def map_industry_to_etf(industry: str):
    industry_lower = (industry or "").lower()
    # word-boundary match เสมอ — เจอบั๊กจริงตอน dev: substring เปล่าๆ ("technology" IN
    # "biotechnology") ทำให้ MRNA (Moderna, finnhubIndustry="Biotechnology") match keyword
    # "technology" ของกลุ่ม XLK ก่อนจะถึงคำ "biotechnology" ของกลุ่ม XLV ที่ถูกต้อง (XLK มา
    # ก่อนในลิสต์) ผลคือ "แก้" ไปเป็น sector เดิมที่ผิดอยู่ดี เงียบๆ ไม่ error ให้เห็น
    for keywords, etf in INDUSTRY_KEYWORD_TO_ETF:
        if any(re.search(r"\b" + re.escape(kw) + r"\b", industry_lower) for kw in keywords):
            return etf
    return None


def fetch_profile(ticker: str, api_key: str):
    url = f"{FINNHUB_PROFILE_URL}?symbol={ticker}&token={api_key}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main():
    load_dotenv()
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        raise SystemExit("ไม่พบ FINNHUB_API_KEY ใน .env")

    ticker_to_etf = load_ticker_to_etf_map()
    ticker_to_name = load_ticker_to_name_map()
    name_matchers = build_name_matchers(ticker_to_name)

    import csv

    with INDEX_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    mistagged_rows = [r for r in rows if r.get("is_mistagged") == "True"]
    print(f"Loaded {len(rows)} rows total, {len(mistagged_rows)} flagged is_mistagged=True")

    raw_paths = {r["raw_path"] for r in mistagged_rows if r.get("raw_path")}
    records_by_path = load_raw_records_by_path(raw_paths)

    profile_cache = {}  # ticker -> profile dict or None (ไม่เจอ) — กัน query ซ้ำ ticker เดิม

    n_fixed = 0
    n_ambiguous = 0
    n_profile_not_found = 0
    n_industry_unmapped = 0
    n_no_company_detected = 0  # ไม่ควรเกิด (เข้าเงื่อนไข mistagged ต้องมีบริษัทอย่างน้อย 1) เผื่อไว้
    fixed_examples = []

    for row in mistagged_rows:
        records = records_by_path.get(row["raw_path"], [])
        rec = match_record(row, records)
        if rec is None:
            n_no_company_detected += 1
            continue

        headline = rec.get("headline") or rec.get("title") or ""
        summary = rec.get("summary") or ""
        text = f"{headline} {summary}"

        if row["source"] == "alpha_vantage":
            companies = detect_companies_from_ticker_sentiment(rec, ticker_to_etf)
        else:
            companies = detect_companies_from_text(text, ticker_to_etf, name_matchers)

        if len(companies) == 0:
            n_no_company_detected += 1
            continue
        if len(companies) > 1:
            n_ambiguous += 1
            continue

        ticker = next(iter(companies))

        if ticker not in profile_cache:
            try:
                profile = fetch_profile(ticker, api_key)
            except urllib.error.HTTPError as e:
                print(f"  {ticker}: HTTP error {e.code}")
                profile = None
            except Exception as e:  # noqa: BLE001
                print(f"  {ticker}: error {type(e).__name__}: {e}")
                profile = None
            profile_cache[ticker] = profile
            time.sleep(RATE_LIMIT_SLEEP)

        profile = profile_cache[ticker]
        if not profile or not profile.get("ticker"):
            n_profile_not_found += 1
            continue

        industry = profile.get("finnhubIndustry", "")
        new_etf = map_industry_to_etf(industry)
        if new_etf is None:
            n_industry_unmapped += 1
            continue

        # เจอ sector จริงแล้ว แก้ field — เก็บของเดิมไว้เสมอ (ไม่ทับ ถ้ามี original_sector_etf
        # อยู่แล้วจากการรันรอบก่อนหน้า ไม่ต้องเขียนทับ เก็บค่าที่เก่าที่สุดไว้)
        if "original_sector_etf" not in row or not row.get("original_sector_etf"):
            row["original_sector_etf"] = row["sector_etf"]
        row["sector_etf"] = new_etf
        row["is_mistagged"] = "False"  # แก้แล้ว ไม่ mistagged อีกต่อไปตามนิยามเดิม
        n_fixed += 1
        if len(fixed_examples) < 10:
            fixed_examples.append(
                f"  {ticker} ({profile.get('name', '?')}, industry={industry!r}): "
                f"{row['original_sector_etf']} -> {new_etf}"
            )

    new_fieldnames = fieldnames + (["original_sector_etf"] if "original_sector_etf" not in fieldnames else [])

    with INDEX_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in new_fieldnames})

    total_mistagged = len(mistagged_rows)
    print(f"\nWrote corrected sector_etf back to {INDEX_PATH}\n")
    print("=== ตัวอย่างที่แก้แล้ว (สูงสุด 10) ===")
    for line in fixed_examples:
        print(line)

    print(f"\n=== สรุปผล ({total_mistagged} แถวที่ is_mistagged=True ทั้งหมด) ===")
    print(f"  แก้ sector สำเร็จ (fixed)                 : {n_fixed:5d}  ({n_fixed/total_mistagged*100:5.1f}%)")
    print(f"  ข้าม — มีมากกว่า 1 บริษัท (ambiguous)      : {n_ambiguous:5d}  ({n_ambiguous/total_mistagged*100:5.1f}%)")
    print(f"  ข้าม — หา profile ไม่เจอ                   : {n_profile_not_found:5d}  ({n_profile_not_found/total_mistagged*100:5.1f}%)")
    print(f"  ข้าม — industry map เข้า sector ไม่ได้      : {n_industry_unmapped:5d}  ({n_industry_unmapped/total_mistagged*100:5.1f}%)")
    if n_no_company_detected:
        print(f"  ข้าม — ไม่พบ record/บริษัทเลย (ผิดปกติ)     : {n_no_company_detected:5d}")
    print(f"\nUnique ticker ที่เรียก company-profile2 จริง: {len(profile_cache)}")


if __name__ == "__main__":
    main()
