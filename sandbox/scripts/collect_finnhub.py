"""
collect_finnhub.py — เก็บข่าว sector-tagged จาก Finnhub `company-news` endpoint โดย query
ด้วย **sector ETF ticker ตรงๆ** (เช่น symbol=XLK) แทนที่จะ query ทีละบริษัทแล้ว group เอง —
ยืนยันแล้วว่า endpoint นี้คืนข่าวที่เกี่ยวกับ sector ETF นั้นจริง (ทดสอบเรียกจริงกับ XLK, XLU,
XLRE, XLC, XLB) จึงครอบคลุมทั้ง Group A (official API) และเป้าหมายของ Group B (sector-ETF
news) พร้อมกัน โดยไม่ต้อง scrape เว็บไหนเลย (Group B ทุกเว็บถูกตัดแล้วเพราะ ToS/block — ดู
sandbox/data/DECISIONS_NEEDED.md)

หมายเหตุสำคัญที่ยืนยันจากการเรียกจริง (ไม่ใช่เดา):
    - endpoint `news-sentiment` (ที่คาดว่าจะมี sectorAverageScore) คืน 403 บน free tier —
      ใช้ไม่ได้ เพราะงั้น sentiment_score ใน index.csv ของ source นี้จะว่างไว้ก่อน
    - query ช่วงวันที่กว้างมาก (หลายเดือนในคำขอเดียว) ดูเหมือนจะ cap จำนวนผลลัพธ์แล้ว bias
      ไปทางข่าวล่าสุด (ข่าวเก่ากว่าในช่วงเดียวกันหายไปทั้งที่ query แคบกว่าตรงเดือนนั้นได้ผล
      จริง) — script นี้เลย query เป็น chunk รายเดือนเสมอ ไม่ query ช่วงกว้างทีเดียว
    - free tier เป็น rolling window ข้อมูลล่าสุดเท่านั้น (ทดสอบแล้วไม่มีข้อมูลย้อนหลังถึงปี
      2022/2024/กลางปี 2025) ไม่ใช่ archive ยาว — script จะหยุดแต่ละ ETF อัตโนมัติหลังเจอ
      เดือนว่างติดกัน 2 เดือน (แปลว่าถึงขอบของ rolling window แล้ว)

รัน (จาก project root): python3 -m sandbox.scripts.collect_finnhub
Resume ได้เสมอ — เช็ค collection_log.jsonl ก่อนทุก chunk/item ข้ามของที่ทำสำเร็จแล้ว
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

from sandbox.scripts._sector_news_common import (
    SECTOR_ETFS,
    append_index_rows,
    load_done_ids,
    log_result,
    write_raw_jsonl,
)

SOURCE = "finnhub"
API_BASE = "https://finnhub.io/api/v1/company-news"
RATE_LIMIT_SLEEP = 1.1  # Finnhub free tier = 60 req/min — เผื่อ margin เหลือ ~54/min จริง
MAX_LOOKBACK_MONTHS = 12
CONSECUTIVE_EMPTY_STOP = 2
HEADERS = {"User-Agent": "sandbox-research-script/1.0 (contact: boeing6677@gmail.com)"}


def month_chunks(max_months: int) -> list:
    """คืน [(start_date, end_date, label), ...] ไล่ย้อนจากเดือนปัจจุบันถอยหลัง max_months เดือน"""
    today = date.today()
    chunks = []
    y, m = today.year, today.month
    for _ in range(max_months):
        start = date(y, m, 1)
        end = date(y, 12, 31) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
        end = min(end, today)
        chunks.append((start, end, f"{y}-{m:02d}"))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return chunks


def fetch_chunk(symbol: str, start: date, end: date, api_key: str) -> list:
    url = f"{API_BASE}?symbol={symbol}&from={start.isoformat()}&to={end.isoformat()}&token={api_key}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    load_dotenv()
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        raise SystemExit("ไม่พบ FINNHUB_API_KEY ใน .env")

    done_ids = load_done_ids(SOURCE)
    total_new = 0

    for etf in SECTOR_ETFS:
        print(f"=== {etf} ===")
        consecutive_empty = 0

        for start, end, label in month_chunks(MAX_LOOKBACK_MONTHS):
            chunk_id = f"chunk:{etf}:{label}"
            if chunk_id in done_ids:
                print(f"  {label}: already done, skip")
                continue

            try:
                items = fetch_chunk(etf, start, end, api_key)
            except urllib.error.HTTPError as e:
                log_result(SOURCE, chunk_id, "error", f"HTTP {e.code}")
                print(f"  {label}: HTTP error {e.code}")
                time.sleep(RATE_LIMIT_SLEEP)
                continue
            except Exception as e:  # noqa: BLE001 — network/JSON error ทุกแบบ log แล้วไปต่อ
                log_result(SOURCE, chunk_id, "error", f"{type(e).__name__}: {e}")
                print(f"  {label}: error {e}")
                time.sleep(RATE_LIMIT_SLEEP)
                continue

            new_items = [it for it in items if f"item:{it.get('id', it.get('url'))}" not in done_ids]

            index_rows = []
            for it in new_items:
                item_id = f"item:{it.get('id', it.get('url'))}"
                item_date = datetime.fromtimestamp(it["datetime"], tz=timezone.utc).date().isoformat()
                raw_path = write_raw_jsonl(SOURCE, etf, item_date, [it])
                index_rows.append(
                    {
                        "source": SOURCE,
                        "item_id": item_id,
                        "date": item_date,
                        "sector_etf": etf,
                        "url": it.get("url", ""),
                        "sentiment_score": "",  # free tier ไม่มี sentiment ติดมา — ดู DECISIONS_NEEDED.md
                        "word_count": len((it.get("summary") or "").split()),
                        "raw_path": str(raw_path),
                    }
                )
                log_result(SOURCE, item_id, "success")
                done_ids.add(item_id)

            if index_rows:
                append_index_rows(index_rows)
                total_new += len(index_rows)

            log_result(SOURCE, chunk_id, "success", f"{len(items)} items, {len(index_rows)} new")
            done_ids.add(chunk_id)

            if items:
                consecutive_empty = 0
                print(f"  {label}: {len(items)} item(s), {len(index_rows)} new")
            else:
                consecutive_empty += 1
                print(f"  {label}: 0 items")
                if consecutive_empty >= CONSECUTIVE_EMPTY_STOP:
                    print(
                        f"  stopping {etf} early — {CONSECUTIVE_EMPTY_STOP} consecutive empty "
                        "months (likely hit the free-tier rolling-window boundary)"
                    )
                    break

            time.sleep(RATE_LIMIT_SLEEP)

    print(f"\nDone. {total_new} new item(s) collected this run.")


if __name__ == "__main__":
    main()
