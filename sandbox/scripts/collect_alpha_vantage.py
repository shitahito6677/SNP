"""
collect_alpha_vantage.py — เก็บข่าวจาก Alpha Vantage `NEWS_SENTIMENT` API

Sector มา**derive จาก ticker ที่บทความพูดถึงจริง** (join กับ S&P500 ticker -> GICS sector ->
ETF mapping จาก Wikipedia ปัจจุบัน ผ่าน `_sector_news_common.load_ticker_to_etf_map()`) แม่น
กว่าการใช้ `topics` param เป็น sector label ตรงๆ เพราะ `topics` ของ AV (~7 กลุ่มกว้าง:
technology, finance, life_sciences, real_estate, energy_transportation, retail_wholesale,
manufacturing) ไม่ตรง 11 GICS เป๊ะ (เช่น "energy_transportation" ปนกันระหว่าง Energy กับ
Industrials, "retail_wholesale" ปนกันระหว่าง Consumer Discretionary กับ Staples — ดู
DECISIONS_NEEDED.md) `topics` ยังใช้เป็นตัวกรองความเกี่ยวข้องคร่าวๆ เพื่อลด noise/กระจาย
เนื้อหาเท่านั้น ไม่ใช้เป็น sector label โดยตรง 1 บทความอาจพูดถึงหลาย ticker คนละ sector ->
เขียนหลายแถวใน index.csv (1 แถวต่อ sector ที่บทความนั้นแตะ) sentiment_score ของแถวนั้น =
weighted average (ด้วย relevance_score) ของ ticker_sentiment_score ของ ticker ในกลุ่ม sector
นั้นในบทความนั้น

⚠️ Rate limit: free tier = **25 request/วัน** (เข้มงวดมาก ไม่เหมือน Finnhub) — ยืนยันจากการ
เรียกจริงด้วยว่า `limit=1000` ต่อ request ถ้าช่วงเวลาที่ขอมีข่าวมากกว่า 1000 รายการ จะได้แค่
1000 รายการล่าสุดในช่วงนั้น (เก่ากว่านั้นในช่วงเดียวกันหายไปเงียบๆ — เจอจริงตอนขอ 7 วันได้ผล
แค่วันเดียวเพราะข่าวทั่วไปเกิน 1000/วัน) เพราะงั้น script นี้:
    1. เดินทีละ topic (round-robin) ทำ **แค่ N request/run** (ปรับได้ผ่าน --max-requests
       default 8) ไม่พยายามดึงให้ครบในวันเดียว — เก็บ "cursor" (time_to ล่าสุดที่เคยดึงถึง)
       ต่อ topic ไว้ใน collection_log.jsonl ให้วันถัดไปรันต่อจากจุดเดิมได้
    2. ถ้า topic ไหนได้ feed ว่างเปล่า **ไม่ mark exhausted ถาวร** — เจอจริงว่า provider นี้
       คืน feed ว่างเฉยๆ (ไม่ error ชัดเจน) ตอนติด rate limit ด้วย (query เดิมเป๊ะ ได้ 1000
       ตอนแรก แล้วได้ 0 ตอนเรียกซ้ำ) แค่ skip topic นั้นสำหรับ "รันนี้" เท่านั้น รันครั้งถัดไป
       จะลองคิวร์เดิมใหม่เสมอ (เสีย quota เพิ่มนิดหน่อยถ้า topic นั้น exhausted จริง แต่ปลอดภัย
       กว่าเสี่ยงเสียข้อมูลจริงจากการ mark ผิด) เช็คด้วยว่า response มี key `Information`/`Note`
       (สัญญาณ rate-limit/invalid-input ของ AV) ไหมก่อนเชื่อว่า feed ว่างคือ "ไม่มีข้อมูลจริง"

รัน (จาก project root): python3 -m sandbox.scripts.collect_alpha_vantage [--max-requests N]
"""

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from sandbox.scripts._sector_news_common import (
    LOG_PATH,
    append_index_rows,
    load_done_ids,
    load_ticker_to_etf_map,
    log_result,
    write_raw_jsonl,
)

SOURCE = "alpha_vantage"
API_URL = "https://www.alphavantage.co/query"
HEADERS = {"User-Agent": "sandbox-research-script/1.0 (contact: boeing6677@gmail.com)"}

# topic ที่พอจะสื่อถึง sector ได้บ้าง (ใช้กรอง noise เท่านั้น ไม่ใช่ sector label ตรงๆ — ดู
# docstring ด้านบน) เรียงตามลำดับ round-robin คงที่ให้แต่ละ topic ได้โควต้าเท่าๆ กันข้ามวัน
TOPICS = [
    "technology",
    "finance",
    "life_sciences",
    "real_estate",
    "energy_transportation",
    "retail_wholesale",
    "manufacturing",
]

AV_TIME_FMT = "%Y%m%dT%H%M"  # ใช้ส่งใน query param (time_from/time_to) — ไม่มีวินาที
AV_TIME_PUBLISHED_FMT = "%Y%m%dT%H%M%S"  # format จริงของ time_published ที่ API คืนมา (มีวินาที)


def _article_id(url: str) -> str:
    return "article:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _cursor_id(topic: str) -> str:
    return f"cursor:{topic}"


def load_cursor(topic: str) -> str:
    """อ่าน time_to cursor ล่าสุดของ topic นี้จาก collection_log.jsonl — ไม่มีมาก่อนแปลว่า
    ยังไม่เคยดึง topic นี้เลย ให้เริ่มจากตอนนี้"""
    if not LOG_PATH.exists():
        return datetime.now(timezone.utc).strftime(AV_TIME_FMT)
    latest = None
    with LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("source") == SOURCE and rec.get("item_id") == _cursor_id(topic):
                latest = rec.get("detail") or latest
    return latest or datetime.now(timezone.utc).strftime(AV_TIME_FMT)


# AV rejects a request that has time_to but no time_from ("Invalid inputs" — confirmed by a
# real call, not assumed) — anchor time_from far enough in the past that it never actually
# constrains the query (the API already caps each call at the most recent `limit` items
# within whatever range is given, so an old time_from costs nothing extra)
AV_EPOCH_FLOOR = "20000101T0000"


def fetch_news(topic: str, time_to: str, api_key: str) -> dict:
    params = (
        f"function=NEWS_SENTIMENT&topics={topic}&time_from={AV_EPOCH_FLOOR}"
        f"&time_to={time_to}&limit=1000&apikey={api_key}"
    )
    req = urllib.request.Request(f"{API_URL}?{params}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def sector_rows_for_article(article: dict, ticker_to_etf: dict) -> dict:
    """คืน {sector_etf: weighted_avg_sentiment_score} จาก ticker_sentiment ของบทความนี้ —
    group ticker ที่ map เจอ sector ตาม etf แล้วถ่วงน้ำหนักด้วย relevance_score"""
    buckets = {}  # etf -> [(score, weight), ...]
    for ts in article.get("ticker_sentiment", []):
        etf = ticker_to_etf.get(ts["ticker"])
        if not etf:
            continue  # ticker ไม่อยู่ใน S&P500 ปัจจุบัน (เช่น ETF เอง, ตัวต่างประเทศ) ข้าม ไม่เดา sector
        try:
            score = float(ts["ticker_sentiment_score"])
            weight = float(ts["relevance_score"])
        except (KeyError, ValueError):
            continue
        buckets.setdefault(etf, []).append((score, weight))

    result = {}
    for etf, pairs in buckets.items():
        total_weight = sum(w for _, w in pairs)
        if total_weight > 0:
            result[etf] = sum(s * w for s, w in pairs) / total_weight
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-requests", type=int, default=8, help="จำนวน API request สูงสุดที่จะทำในรันนี้ (เผื่อ daily quota 25/วัน)")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise SystemExit("ไม่พบ ALPHA_VANTAGE_API_KEY ใน .env")

    ticker_to_etf = load_ticker_to_etf_map()
    print(f"Loaded ticker->sector map: {len(ticker_to_etf)} tickers")

    done_ids = load_done_ids(SOURCE)

    requests_made = 0
    total_new_articles = 0
    topic_idx = 0
    active_topics = list(TOPICS)
    skip_this_run = set()  # topic ที่เจอ 0 บทความรอบนี้ — ข้ามที่เหลือของ "รันนี้" เท่านั้น
    # ไม่ permanent-exhaust จาก response ว่างครั้งเดียว: เจอจริงว่า provider นี้คืน feed ว่าง
    # เปล่าเฉยๆ (ไม่ error) ตอนติด rate limit ด้วย (query เดิมเป๊ะได้ 1000 แล้วพอเรียกซ้ำได้ 0)
    # ถ้า mark exhausted ถาวรจาก response เดียวจะเสี่ยงเสียข้อมูลจริงไปฟรีๆ — ให้ลองใหม่ทุกวัน
    # แทน (เสีย quota แค่ 1 request/topic/วันถ้า topic นั้น exhausted จริง ถูกกว่าเสียข้อมูล)

    while requests_made < args.max_requests and active_topics:
        available = [t for t in active_topics if t not in skip_this_run]
        if not available:
            break
        topic = available[topic_idx % len(available)]
        cursor = load_cursor(topic)
        print(f"[{requests_made + 1}/{args.max_requests}] topic={topic} time_to={cursor}")

        try:
            data = fetch_news(topic, cursor, api_key)
        except urllib.error.HTTPError as e:
            log_result(SOURCE, f"request:{topic}:{cursor}", "error", f"HTTP {e.code}")
            print(f"  HTTP error {e.code} — น่าจะติด daily quota, หยุดรันนี้")
            break
        except Exception as e:  # noqa: BLE001
            log_result(SOURCE, f"request:{topic}:{cursor}", "error", f"{type(e).__name__}: {e}")
            print(f"  error: {e}")
            break

        requests_made += 1

        # AV คืน {"Information": "..."} หรือ {"Note": "..."} แทนที่จะเป็น HTTP error ตอนติด
        # rate limit หรือ input ผิด (เจอจริง — ดู DECISIONS_NEEDED.md) เช็คก่อนเชื่อว่า
        # "feed ว่าง" หมายถึง "ไม่มีข่าวเก่ากว่านี้แล้วจริงๆ"
        if "Information" in data or "Note" in data:
            msg = data.get("Information") or data.get("Note")
            log_result(SOURCE, f"request:{topic}:{cursor}", "error", f"API message: {msg}")
            print(f"  API message (ไม่ใช่ feed ว่างจริง): {msg}")
            print("  หยุดรันนี้ — อาจติด daily quota")
            break

        feed = data.get("feed", [])

        if not feed:
            print(f"  0 articles ที่ time_to={cursor} — อาจ exhausted จริง หรือติด quota เงียบๆ")
            print(f"  ไม่ mark exhausted ถาวร — ข้าม {topic} ไปก่อนสำหรับรันนี้ ลองใหม่รันหน้า")
            log_result(SOURCE, f"request:{topic}:{cursor}", "success", "0 articles (not marked exhausted)")
            skip_this_run.add(topic)
            continue

        new_count = 0
        earliest_seen = None  # ต้องเจอ time_published จริงอย่างน้อย 1 อัน ไม่งั้น cursor ต้องไม่ขยับ
        for article in feed:
            url = article.get("url", "")
            item_id = _article_id(url)
            time_published = article.get("time_published", "")
            if time_published and (earliest_seen is None or time_published < earliest_seen):
                earliest_seen = time_published

            if item_id in done_ids:
                continue  # เคยดึงบทความนี้แล้ว (topic อื่นอาจ overlap กันได้)

            sector_scores = sector_rows_for_article(article, ticker_to_etf)
            if not sector_scores:
                # ไม่มี ticker ไหน map sector ได้เลย — log ว่าดึงบทความนี้แล้ว (กัน retry ซ้ำ)
                # แต่ไม่เขียนแถว index (ไม่มี sector ให้ tag จริง ไม่เดา)
                log_result(SOURCE, item_id, "success", "no mappable sector")
                done_ids.add(item_id)
                continue

            date_str = time_published[:8]
            date_iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}" if len(date_str) == 8 else ""
            raw_path = write_raw_jsonl(SOURCE, "multi_sector", date_iso or "unknown", [article])

            index_rows = [
                {
                    "source": SOURCE,
                    "item_id": item_id,
                    "date": date_iso,
                    "sector_etf": etf,
                    "url": url,
                    "sentiment_score": round(score, 6),
                    "word_count": len((article.get("summary") or "").split()),
                    "raw_path": str(raw_path),
                }
                for etf, score in sector_scores.items()
            ]
            append_index_rows(index_rows)
            log_result(SOURCE, item_id, "success", f"sectors={list(sector_scores)}")
            done_ids.add(item_id)
            new_count += 1

        total_new_articles += new_count
        print(f"  {len(feed)} articles fetched, {new_count} new, tagged across sectors")

        # เดิน cursor ถอยหลัง (ก่อนหน้าข่าวที่เก่าที่สุดในรอบนี้ 1 นาที กันดึงซ้ำ item เดิม)
        # time_published จาก API มีวินาทีด้วย (เช่น "20260907T072828") ยาวกว่า AV_TIME_FMT ที่
        # ใช้ใน query (ไม่มีวินาที) — ต้อง parse ด้วย format ที่มีวินาทีจริง ไม่งั้น
        # strptime จะ raise ValueError เงียบๆ แล้ว cursor ไม่ขยับ (เจอบั๊กนี้จริงจากการรัน —
        # เดิม except ValueError เงียบๆ ทำให้ cursor ค้างที่เดิมและวน fetch ข่าวชุดเดิมซ้ำไม่รู้จบ)
        if earliest_seen is None:
            # ไม่ควรเกิดขึ้นได้จริง (feed ไม่ว่างแปลว่าต้องมี time_published อย่างน้อย 1 อัน)
            # แต่เผื่อไว้ — อย่าขยับ cursor เงียบๆ ให้เห็น error ชัดแทนที่จะวน loop ไม่รู้จบ
            log_result(SOURCE, f"request:{topic}:{cursor}", "error", "feed ไม่ว่างแต่ไม่มี time_published เลย")
            print("  WARNING: ไม่มี time_published ใน feed นี้เลย — ข้าม topic นี้ไปก่อน")
            skip_this_run.add(topic)
            continue
        earliest_dt = datetime.strptime(earliest_seen, AV_TIME_PUBLISHED_FMT)
        new_cursor = (earliest_dt - timedelta(minutes=1)).strftime(AV_TIME_FMT)
        log_result(SOURCE, _cursor_id(topic), "success", new_cursor)

        topic_idx += 1

    print(f"\nDone. {requests_made} request(s) made, {total_new_articles} new article(s) tagged this run.")


if __name__ == "__main__":
    main()
