"""
s3_sector_views.py — ขั้นที่ 3: ให้ Qwen อ่านข่าวมหภาคแล้วประเมินผลกระทบต่อแต่ละ GICS sector

Input : data/raw/macro_news_raw.parquet
Output: data/processed/sector_views.parquet   (date, source, url, view_XLK, ..., view_XLC)
        data/processed/sector_views.jsonl     (append-only checkpoint log กัน crash)

การใช้งาน:
    python3 src/s3_sector_views.py --mode test    # ทดสอบ 3 ข่าว (default) แค่ print ผล ไม่เซฟ
    python3 src/s3_sector_views.py --mode full     # รันเต็มทุกข่าว, resume ได้ถ้าค้างกลางทาง

ความปลอดภัย: อ่าน QWEN_API_KEY จาก .env เท่านั้น (python-dotenv) — ห้าม print ค่า key
ทุกกรณี รวมถึงตอน error/debug (ตรวจสอบแล้วว่า error message ของ openai SDK ไม่หลุด key ออกมา)
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
import os
from openai import OpenAI, RateLimitError, APIStatusError, APIConnectionError

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NEWS_PATH = PROJECT_ROOT / "data" / "raw" / "macro_news_raw.parquet"
OUT_PARQUET = PROJECT_ROOT / "data" / "processed" / "sector_views.parquet"
OUT_JSONL = PROJECT_ROOT / "data" / "processed" / "sector_views.jsonl"  # append-only checkpoint
FAILURES_PATH = PROJECT_ROOT / "data" / "processed" / "sector_views_failures.json"

BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-plus"

# ตัดข้อความข่าวยาวๆ (Beige Book บางฉบับยาวเป็นแสนตัวอักษร) ให้เหลือส่วนต้น
# ซึ่งมักมี National Summary + district แรกๆ ที่คุมประเด็นหลักไว้แล้ว — เป็นการ trade-off
# ต้นทุน/latency โดยตั้งใจ ไม่ใช่ข้อผิดพลาด (ระบุไว้ชัดเจนเพื่อไม่ให้เข้าใจผิดว่าใช้ข้อความเต็ม)
MAX_TEXT_CHARS = 6000

SECTORS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLE": "Energy",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

PROGRESS_EVERY = 20
MAX_RETRIES = 3
TOKEN_BUDGET = 900_000  # safety cap ต่อการรัน 1 รอบ กัน quota หมดกลางทาง — ถึงแล้วหยุดรอ confirm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("s3_sector_views")


# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

def get_client():
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.environ.get("QWEN_API_KEY")
    if not key:
        raise RuntimeError("ไม่พบ QWEN_API_KEY ใน .env")
    # ห้าม print/log ค่า key เด็ดขาด — เก็บไว้แค่ในตัวแปร key และส่งให้ SDK เท่านั้น
    return OpenAI(api_key=key, base_url=BASE_URL)


def build_messages(news_date, source, text):
    truncated = text[:MAX_TEXT_CHARS]
    sector_list = "\n".join(f'- {tk} ({name})' for tk, name in SECTORS.items())

    system_prompt = (
        "You are a macro/sector equity analyst. You will be given one piece of US macro "
        "economic news (an FOMC statement or a Fed Beige Book report). For EACH of the 11 "
        "GICS sector ETFs listed below, write exactly ONE short sentence describing the "
        "likely directional impact on that sector (positive / negative / neutral / mixed) "
        "and a brief reason.\n\n"
        f"Sectors (use these exact tickers as JSON keys):\n{sector_list}\n\n"
        "Respond with ONLY a single valid JSON object, no markdown fences, no extra text, "
        "with exactly these 11 keys (one per sector ticker above). Each value must be a "
        "single short sentence starting with the direction word. Example format:\n"
        '{"XLK": "Slightly negative — rate uncertainty pressures growth stocks", '
        '"XLF": "Positive — higher rates boost bank margins", ...}'
    )
    user_prompt = (
        f"News date: {news_date}\nNews source: {source}\n\nNews text:\n{truncated}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_json_response(content):
    """คืน dict ถ้า parse ผ่านและมีครบ 11 key ที่ต้องการ, คืน None ถ้าไม่ผ่าน (ไม่เดา/เติมเอง)"""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if set(data.keys()) != set(SECTORS.keys()):
        return None
    if not all(isinstance(v, str) and v.strip() for v in data.values()):
        return None
    return data


def call_qwen(client, messages):
    """เรียก Qwen พร้อม retry MAX_RETRIES ครั้งด้วย exponential backoff (2s, 4s, 8s, ...)
    ก่อนยอมแพ้ — retry ทุก error รวมถึง rate-limit/429 ด้วย (ตามที่กำหนด) ถ้า retry ครบแล้ว
    ยัง fail อยู่ จะ raise ข้อผิดพลาดล่าสุดออกไปให้ caller ตัดสินใจ (หยุด run ทั้งชุด ไม่เดาผล)"""
    last_err = None
    for attempt in range(MAX_RETRIES + 1):  # 1 ครั้งแรก + retry อีก MAX_RETRIES ครั้ง
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.2,
                max_tokens=900,
            )
            return resp
        except RateLimitError as e:
            last_err = e
        except APIStatusError as e:
            last_err = RateLimitError(message=str(e), response=e.response, body=e.body) if e.status_code == 429 else e
        except APIConnectionError as e:
            last_err = e

        if attempt < MAX_RETRIES:
            backoff = 2 ** (attempt + 1)  # 2, 4, 8 วินาที
            log.warning(f"เรียก Qwen ล้มเหลว (attempt {attempt + 1}/{MAX_RETRIES + 1}): "
                        f"{type(last_err).__name__} — retry ใน {backoff}s")
            time.sleep(backoff)

    raise last_err


# --------------------------------------------------------------------------
# Test mode: 3 ข่าว, print ผลอย่างละเอียด, ไม่เซฟไฟล์จริง
# --------------------------------------------------------------------------

def run_test(client, news_df):
    fomc = news_df[news_df["source"] == "FOMC_statement"].sort_values("date").tail(1)
    beige = news_df[news_df["source"] == "Beige_Book"].sort_values("date").tail(2)
    sample = pd.concat([fomc, beige]).sort_values("date")

    print("=" * 70)
    print(f"TEST MODE: {len(sample)} ข่าว (1 FOMC ล่าสุด + 2 Beige Book ล่าสุด)")
    print("=" * 70)

    total_prompt_tok = 0
    total_completion_tok = 0

    for _, row in sample.iterrows():
        print(f"\n--- {row['source']} | {row['date'].date()} | {row['url']} ---")
        print(f"text length: {len(row['text'])} chars (ส่งจริง {min(len(row['text']), MAX_TEXT_CHARS)} chars)")

        messages = build_messages(row["date"].date(), row["source"], row["text"])
        try:
            resp = call_qwen(client, messages)
        except RateLimitError as e:
            print(f"RATE LIMIT / QUOTA ระหว่าง test: {e}")
            return
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            continue

        content = resp.choices[0].message.content
        usage = resp.usage
        total_prompt_tok += usage.prompt_tokens
        total_completion_tok += usage.completion_tokens

        print(f"token usage: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, "
              f"total={usage.total_tokens}")

        parsed = parse_json_response(content)
        if parsed is None:
            print("!! JSON parse/validate FAILED — raw response:")
            print(content)
            continue

        missing = set(SECTORS.keys()) - set(parsed.keys())
        print(f"ครบ 11 sector: {'YES' if not missing else f'NO (ขาด {missing})'}")
        for tk in SECTORS:
            print(f"  {tk:5s}: {parsed[tk]}")

    n = len(sample)
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"ข่าวที่ test: {n}")
    print(f"token รวม: prompt={total_prompt_tok}, completion={total_completion_tok}, "
          f"total={total_prompt_tok + total_completion_tok}")
    if n:
        avg = (total_prompt_tok + total_completion_tok) / n
        print(f"เฉลี่ยต่อข่าว: {avg:.0f} tokens")
        full_n = len(news_df)
        print(f"ประเมินถ้ารันเต็ม {full_n} ข่าว: ~{avg * full_n:,.0f} tokens รวม")
    print("\n>>> นี่คือแค่ test mode ไม่ได้เซฟผลลัพธ์ใดๆ ลงไฟล์ <<<")
    print(">>> รัน --mode full เพื่อรันจริงหลังตรวจสอบผลข้างบนแล้ว <<<")


# --------------------------------------------------------------------------
# Full mode: รันทุกข่าว, เซฟทีละข่าว, resume ได้, หยุดสวยๆ ถ้าเจอ rate limit
# --------------------------------------------------------------------------

def load_done_keys():
    if not OUT_JSONL.exists():
        return set()
    done = set()
    with open(OUT_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                done.add((rec["date"], rec["source"], rec["url"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def rebuild_parquet_from_jsonl():
    if not OUT_JSONL.exists():
        return 0
    rows = []
    with open(OUT_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    cols = ["date", "source", "url"] + [f"view_{tk}" for tk in SECTORS]
    df = df[cols].sort_values(["date", "source"]).reset_index(drop=True)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    return len(df)


def progress_bar(done, total, width=30):
    frac = done / total if total else 0
    filled = int(width * frac)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {done}/{total} ({100*frac:.1f}%)"


def run_full(client, news_df, token_budget=TOKEN_BUDGET):
    done_keys = load_done_keys()
    if done_keys:
        log.info(f"พบ checkpoint เดิม {len(done_keys)} ข่าวที่ทำไปแล้ว จะ resume ต่อ")

    news_df = news_df.sort_values("date").reset_index(drop=True)
    todo = [
        row for _, row in news_df.iterrows()
        if (str(row["date"].date()), row["source"], row["url"]) not in done_keys
    ]
    log.info(f"ทั้งหมด {len(news_df)} ข่าว, เหลือต้องทำ {len(todo)} ข่าว")
    log.info(f"Token safety budget รอบนี้: {token_budget:,} tokens (เช็คทุกข่าว)")

    if not todo:
        log.info("ทำครบทุกข่าวแล้ว ไม่มีอะไรต้องทำเพิ่ม")
        rebuild_parquet_from_jsonl()
        return

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    total_prompt_tok = 0
    total_completion_tok = 0
    n_done_this_run = 0
    failures = []  # list of {"url":..., "date":..., "source":..., "reason":...}
    stop_reason = None

    for i, row in enumerate(todo, 1):
        messages = build_messages(row["date"].date(), row["source"], row["text"])
        try:
            resp = call_qwen(client, messages)
        except RateLimitError as e:
            log.warning("=" * 60)
            log.warning(f"RATE LIMIT / QUOTA EXHAUSTED หลัง retry {MAX_RETRIES} ครั้งแล้วยัง fail — หยุดแบบปลอดภัย ({e})")
            log.warning(f"ทำไปแล้วรอบนี้: {n_done_this_run}/{len(todo)} ข่าว "
                        f"(checkpoint เซฟไว้ที่ {OUT_JSONL} แล้ว รันสคริปต์นี้ซ้ำเพื่อ resume ต่อได้เลย)")
            log.warning("=" * 60)
            stop_reason = "rate_limit_or_quota"
            break
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            log.warning(f"ข่าว {row['url']} ล้มเหลว ({reason}) — ข้ามไป ไม่เดาผล")
            failures.append({"date": str(row["date"].date()), "source": row["source"],
                              "url": row["url"], "reason": reason})
            continue

        content = resp.choices[0].message.content
        usage = resp.usage
        total_prompt_tok += usage.prompt_tokens
        total_completion_tok += usage.completion_tokens

        parsed = parse_json_response(content)
        if parsed is None:
            reason = "JSON parse ไม่ผ่าน หรือไม่ครบ 11 sector key"
            log.warning(f"ข่าว {row['url']} {reason} — ข้ามไป ไม่เดาผล")
            failures.append({"date": str(row["date"].date()), "source": row["source"],
                              "url": row["url"], "reason": reason})
            continue

        record = {
            "date": str(row["date"].date()),
            "source": row["source"],
            "url": row["url"],
            **{f"view_{tk}": parsed[tk] for tk in SECTORS},
        }
        with open(OUT_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        rebuild_parquet_from_jsonl()  # เซฟทีละข่าว กัน crash ต้องเริ่มใหม่ (ตามที่กำหนด)

        n_done_this_run += 1
        run_total_tok = total_prompt_tok + total_completion_tok

        if n_done_this_run % PROGRESS_EVERY == 0:
            log.info(
                progress_bar(n_done_this_run + len(done_keys), len(news_df))
                + f" | token สะสมรอบนี้: prompt={total_prompt_tok}, completion={total_completion_tok}, "
                  f"total={run_total_tok:,}"
            )

        if run_total_tok >= token_budget:
            log.warning("=" * 60)
            log.warning(f"token สะสมรอบนี้ ({run_total_tok:,}) ถึง safety budget ({token_budget:,}) แล้ว")
            log.warning(f"หยุดรอ confirm ก่อนไปต่อ — ทำไปแล้ว {n_done_this_run}/{len(todo)} ข่าวรอบนี้ "
                        f"(checkpoint เซฟไว้แล้ว รันสคริปต์นี้ซ้ำเพื่อ resume ต่อได้)")
            log.warning("=" * 60)
            stop_reason = "token_budget"
            break

    if stop_reason is None:
        stop_reason = "completed"

    if failures:
        FAILURES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FAILURES_PATH, "w", encoding="utf-8") as f:
            json.dump(failures, f, ensure_ascii=False, indent=2)

    log.info("=" * 60)
    log.info("FULL RUN SUMMARY (รอบนี้)")
    log.info("=" * 60)
    log.info(f"หยุดเพราะ: {stop_reason}")
    log.info(f"สำเร็จรอบนี้: {n_done_this_run}, ล้มเหลว/ข้ามรอบนี้: {len(failures)}")
    if failures:
        log.info(f"รายละเอียด failure เซฟไว้ที่: {FAILURES_PATH}")
        for f_ in failures:
            log.info(f"  - [{f_['source']}] {f_['date']} {f_['url']} :: {f_['reason']}")
    log.info(f"token ใช้ไปรอบนี้: prompt={total_prompt_tok}, completion={total_completion_tok}, "
              f"total={total_prompt_tok + total_completion_tok:,}")
    n_total_saved = rebuild_parquet_from_jsonl()
    log.info(f"รวมทั้งหมดใน {OUT_PARQUET}: {n_total_saved} ข่าว")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["test", "full"], default="test")
    args = parser.parse_args()

    if not NEWS_PATH.exists():
        raise FileNotFoundError(f"ไม่พบ {NEWS_PATH} — รัน s1_fetch_news.py ก่อน")

    news_df = pd.read_parquet(NEWS_PATH)
    client = get_client()

    if args.mode == "test":
        run_test(client, news_df)
    else:
        run_full(client, news_df)


if __name__ == "__main__":
    main()
