"""
r3_llm_extraction.py — Phase R3: LLM structured-variable extraction (ชั้น 1 ของ Model C
rule-based sector impact engine)

**กฎเหล็ก (จุดที่แก้ปัญหา bias ของ exp_02 โดยตรง):** prompt ห้าม LLM พูดถึง sector ใดๆ
ทั้งสิ้น หน้าที่มันคือ "อ่านเอกสารแล้วกรอกแบบฟอร์มตัวแปรเชิงโครงสร้าง" เท่านั้น — การตัดสินว่า
ตัวแปรเหล่านี้กระทบ sector ไหนยังไงเป็นงานของ rule engine (R4) ล้วนๆ ไม่ใช่งานของ LLM

Schema ที่สกัด (ทุก field คือ "ส่วนต่างจาก release ครั้งก่อนของแหล่งเดียวกัน" ไม่ใช่ค่าสัมบูรณ์
เพราะตลาดตอบสนองต่อการเปลี่ยนแปลง ไม่ใช่ระดับ — "ครั้งก่อน" หมายถึง FOMC statement ครั้งก่อน
เทียบกับ FOMC statement เท่านั้น, Beige Book ครั้งก่อนเทียบกับ Beige Book เท่านั้น เพราะสอง
แหล่งมีโครงสร้าง/จุดประสงค์ต่างกันมาก เทียบข้ามแหล่งจะไม่มีความหมาย):
    stance_delta, growth_delta, inflation_delta, labor_delta,
    forward_guidance_delta, balance_sheet_signal        : -2..+2
    uncertainty_language, financial_stability_concern    : 0..+2
    evidence_quotes: {field: "ข้อความจริงจากเอกสาร"}     บังคับมีทุก field ที่ค่า != 0

การตรวจสอบ (บังคับ, ไม่ fallback เงียบๆ):
    - field ใดค่า != 0 แต่ไม่มี evidence_quotes ที่ไม่ว่างเปล่า -> reject ทั้ง response, retry
      ใหม่ (สูงสุด MAX_VALIDATION_RETRIES ครั้ง) ถ้ายัง fail หมด -> ข้ามข่าวนั้น (log ไว้ ไม่เดา)
    - ค่านอกช่วงที่กำหนด หรือ key ไม่ครบ -> reject เหมือนกัน

Self-consistency: ยิงซ้ำ 2 ครั้ง (temperature=0.7) ต่อข่าว — เหตุผลที่ใช้ 2 ไม่ใช่ 3 (ต้นฉบับ
งานวิจัยมักใช้ 3+ เพื่อดู majority vote): ประหยัด quota Qwen (452 ข่าว x 2 = 904 ครั้ง แทน
1,356) แลกกับตรวจ inconsistency ได้หยาบกว่า (2 รอบบอกได้แค่ "ตรงกันมั้ย" บอกไม่ได้ว่าเสียงส่วน
ใหญ่เอนไปทางไหนแบบ 3 รอบ) ยอมรับ trade-off นี้ในรอบทดลองแรกตามที่ตกลงไว้ ถ้า low_confidence
เยอะผิดปกติจาก run จริง ค่อยพิจารณากลับไป 3 รอบ
    - field ใดต่างกันเกิน 1 ระดับระหว่าง 2 รอบ -> ทั้งข่าวนั้น flag `low_confidence=True`
      (เก็บผลไว้ ไม่ทิ้ง แต่ R4 จะลดน้ำหนัก 0.5x ตามที่กำหนด)
    - ค่าสุดท้ายที่บันทึก = round(mean ของ 2 รอบ) ต่อ field (การรวมผลตัดสินใจเอง เพราะสเปกเดิม
      ไม่ได้ระบุวิธีรวมไว้ — บันทึกไว้ตรงนี้ให้ตรวจสอบย้อนได้)

Input : data/raw/macro_news_raw.parquet (ข้อความข่าวดิบ, ไม่แก้)
        model_c_rulebase/data/fomc_market_context.csv (Phase R1/R2 — ใช้แค่ join key
        date/source/url เพื่อจำกัดให้ตรงกับ 452 ข่าวที่มี CAR label เท่านั้น)
Output: model_c_rulebase/data/fomc_structured_vars.csv
        model_c_rulebase/data/fomc_structured_vars.jsonl  (checkpoint กัน crash, resume ได้)

การใช้งาน:
    python3 -m model_c_rulebase.scripts.r3_llm_extraction --mode test   # 3 ข่าว, print ผล ไม่เซฟ
    python3 -m model_c_rulebase.scripts.r3_llm_extraction --mode full   # รันเต็ม, resume ได้
"""

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIStatusError, APIConnectionError

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NEWS_PATH = PROJECT_ROOT / "data" / "raw" / "macro_news_raw.parquet"
CTX_PATH = PROJECT_ROOT / "model_c_rulebase" / "data" / "fomc_market_context.csv"
OUT_CSV = PROJECT_ROOT / "model_c_rulebase" / "data" / "fomc_structured_vars.csv"
OUT_JSONL = PROJECT_ROOT / "model_c_rulebase" / "data" / "fomc_structured_vars.jsonl"
FAILURES_PATH = PROJECT_ROOT / "model_c_rulebase" / "data" / "fomc_structured_vars_failures.json"

BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-plus"

# ตัดข้อความยาว — เหตุผลเดียวกับ src/s3_sector_views.py (Beige Book บางฉบับยาวเป็นแสนตัวอักษร,
# National Summary + district แรกๆ อยู่ต้นเอกสารเสมอคุมประเด็นหลักไว้แล้ว) CURRENT ตัดยาวกว่า
# PREVIOUS เพราะเป็นเอกสารหลักที่ต้องอ่านละเอียด ส่วน PREVIOUS ใช้แค่เป็นฐานเทียบ
MAX_CURRENT_CHARS = 6000
MAX_PREV_CHARS = 4000

N_SELF_CONSISTENCY = 2
CONSISTENCY_THRESHOLD = 1  # ต่างกันเกินเท่านี้ (ระดับ) -> low_confidence
MAX_VALIDATION_RETRIES = 2  # ต่อ 1 การยิง (นอกเหนือจาก self-consistency 2 รอบ)
MAX_API_RETRIES = 3

TEMPERATURE = 0.7

FIELDS_RANGE_PM2 = ["stance_delta", "growth_delta", "inflation_delta", "labor_delta",
                     "forward_guidance_delta", "balance_sheet_signal"]
FIELDS_RANGE_02 = ["uncertainty_language", "financial_stability_concern"]
ALL_FIELDS = FIELDS_RANGE_PM2 + FIELDS_RANGE_02

TOKEN_BUDGET = 900_000
PROGRESS_EVERY = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("r3_llm_extraction")


# --------------------------------------------------------------------------
# Setup / data loading
# --------------------------------------------------------------------------

def get_client():
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.environ.get("QWEN_API_KEY")
    if not key:
        raise RuntimeError("ไม่พบ QWEN_API_KEY ใน .env")
    return OpenAI(api_key=key, base_url=BASE_URL)


def load_ordered_news():
    """โหลดข้อความข่าวดิบ จำกัดแค่ 452 ข่าวที่มี CAR label แล้ว (join กับ context จาก R1)
    เรียงตามวันที่ *แยกตาม source* แล้วคำนวณ prev_text/prev_date จาก release ก่อนหน้าของ
    source เดียวกันเท่านั้น (FOMC เทียบ FOMC, Beige Book เทียบ Beige Book)"""
    news = pd.read_parquet(NEWS_PATH)
    news["date"] = pd.to_datetime(news["date"])

    ctx = pd.read_csv(CTX_PATH)
    ctx["date"] = pd.to_datetime(ctx["date"])
    keys = set(zip(ctx["date"].astype(str), ctx["source"], ctx["url"]))

    news = news[news.apply(lambda r: (str(r["date"].date()), r["source"], r["url"]) in keys, axis=1)]
    news = news.sort_values(["source", "date"]).reset_index(drop=True)

    news["prev_text"] = news.groupby("source")["text"].shift(1)
    news["prev_date"] = news.groupby("source")["date"].shift(1)

    n_no_prev = news["prev_text"].isna().sum()
    log.info(f"โหลดข่าว {len(news)} รายการ (จาก 452 ที่มี CAR label) — "
             f"{n_no_prev} รายการเป็นข่าวแรกสุดของ source นั้น (ไม่มี release ก่อนหน้าให้เทียบ)")

    return news.sort_values("date").reset_index(drop=True)


# --------------------------------------------------------------------------
# Prompt building — ห้ามพูดถึง sector เด็ดขาด
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a text-to-structured-data extraction assistant for US monetary
policy documents (FOMC statements and Federal Reserve Beige Book reports). Your ONLY job is
to read the CURRENT document, compare it against the PREVIOUS document of the SAME type, and
fill in a structured form describing how the CURRENT document's language/tone changed
relative to the PREVIOUS one.

You must NOT mention, imply, or reason about any specific industry, sector, company, or stock
market segment. You are not an investment analyst here — you are a linguistic/structural
comparison tool. Any output that references sectors will be rejected.

Fill in exactly these 8 fields, each an integer:
- stance_delta (-2 to +2): overall monetary policy stance, more hawkish/restrictive (+) vs
  more dovish/accommodative (-) compared to the previous document
- growth_delta (-2 to +2): assessment of economic growth/activity, more optimistic (+) vs
  more pessimistic (-)
- inflation_delta (-2 to +2): assessment of inflation, hotter/more concerning (+) vs
  cooler/less concerning (-)
- labor_delta (-2 to +2): assessment of labor market, stronger (+) vs weaker (-)
- forward_guidance_delta (-2 to +2): forward-looking signal about future policy path, more
  tightening signaled (+) vs more easing signaled (-)
- balance_sheet_signal (-2 to +2): balance sheet / QT-QE signal, more aggressive
  quantitative tightening (+) vs quantitative easing or QT slowdown (-)
- uncertainty_language (0 to +2): how much MORE uncertainty/hedging language is used
  compared to the previous document (0 = no more than before)
- financial_stability_concern (0 to +2): how much financial-system-stability risk language
  appears (0 = none)

Use 0 for any field with no discernible change or no discernible signal.

For EVERY field where your value is NOT 0, you MUST include a short verbatim quote (a few
words to one sentence, copied exactly from the CURRENT document) in "evidence_quotes" under
that exact field name, justifying your rating. Fields you set to 0 do not need a quote. Never
fabricate a quote — copy real text only.

Write all integers as plain JSON numbers (e.g. 1, -1, 0) — never with a leading "+" sign
(e.g. NOT "+1"), since that is not valid JSON.

Respond with ONLY a single valid JSON object, no markdown fences, no extra commentary, in
exactly this shape:
{
  "stance_delta": 0, "growth_delta": 0, "inflation_delta": 0, "labor_delta": 0,
  "forward_guidance_delta": 0, "balance_sheet_signal": 0,
  "uncertainty_language": 0, "financial_stability_concern": 0,
  "evidence_quotes": {"stance_delta": "...", ...only for non-zero fields...}
}"""


def build_messages(source, current_date, current_text, prev_date, prev_text):
    current_trunc = current_text[:MAX_CURRENT_CHARS]
    prev_trunc = prev_text[:MAX_PREV_CHARS]
    user_prompt = (
        f"Document type: {source}\n\n"
        f"=== PREVIOUS ({prev_date}) ===\n{prev_trunc}\n\n"
        f"=== CURRENT ({current_date}) ===\n{current_trunc}\n\n"
        "Compare CURRENT against PREVIOUS and fill in the JSON form."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# --------------------------------------------------------------------------
# Validation (ห้าม fallback เงียบๆ)
# --------------------------------------------------------------------------

def validate_response(content):
    """คืน (parsed_dict, None) ถ้าผ่าน, (None, reason_str) ถ้าไม่ผ่าน"""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    # โมเดลบางครั้งเขียนเลขบวกแบบ "+1" (พบจริงตอน dev, เช่น "growth_delta": +1) ซึ่งไม่ใช่
    # JSON number literal ที่ถูกต้อง (JSON ไม่รับ leading "+") -> ตัด "+" หน้าตัวเลขหลัง ":" ทิ้ง
    # ก่อน parse (ทำแค่ตำแหน่งหลัง colon กันไปกระทบข้อความ quote ที่อาจมี "+" อยู่จริง)
    cleaned = re.sub(r':\s*\+(\d)', r': \1', cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, "JSON parse failed"

    if not isinstance(data, dict):
        return None, "response ไม่ใช่ JSON object"

    missing = set(ALL_FIELDS) - set(data.keys())
    if missing:
        return None, f"ขาด field: {missing}"
    if "evidence_quotes" not in data or not isinstance(data["evidence_quotes"], dict):
        return None, "ขาดหรือ evidence_quotes ไม่ใช่ dict"

    for f in FIELDS_RANGE_PM2:
        v = data[f]
        if not isinstance(v, int) or not (-2 <= v <= 2):
            return None, f"{f}={v!r} ไม่ใช่ int ในช่วง -2..2"
    for f in FIELDS_RANGE_02:
        v = data[f]
        if not isinstance(v, int) or not (0 <= v <= 2):
            return None, f"{f}={v!r} ไม่ใช่ int ในช่วง 0..2"

    for f in ALL_FIELDS:
        if data[f] != 0:
            q = data["evidence_quotes"].get(f)
            if not isinstance(q, str) or not q.strip():
                return None, f"{f}={data[f]} แต่ไม่มี evidence_quotes (บังคับ ห้าม fallback เป็น 0)"

    return data, None


def call_qwen_validated(client, messages):
    """เรียก Qwen + validate, retry MAX_VALIDATION_RETRIES ครั้งถ้า validate ไม่ผ่าน (ยิงใหม่
    ทั้งหมด ไม่แก้ response เดิมเอง) และ retry MAX_API_RETRIES ครั้งถ้า API เอง fail (rate
    limit/connection) คืน (parsed_dict, usage_tokens_total) หรือ (None, reason) ถ้าสุดท้ายก็ fail"""
    total_tokens = 0
    last_reason = None
    for val_attempt in range(MAX_VALIDATION_RETRIES + 1):
        resp = None
        for api_attempt in range(MAX_API_RETRIES + 1):
            try:
                resp = client.chat.completions.create(
                    model=MODEL, messages=messages, temperature=TEMPERATURE, max_tokens=700,
                )
                break
            except RateLimitError as e:
                last_reason = f"RateLimitError: {e}"
            except APIStatusError as e:
                last_reason = f"APIStatusError({e.status_code}): {e}"
                if e.status_code == 429:
                    pass  # retry เหมือน rate limit
            except APIConnectionError as e:
                last_reason = f"APIConnectionError: {e}"
            if api_attempt < MAX_API_RETRIES:
                backoff = 2 ** (api_attempt + 1)
                time.sleep(backoff)
        if resp is None:
            raise RuntimeError(f"Qwen API ล้มเหลวหมดหลัง retry: {last_reason}")

        total_tokens += resp.usage.total_tokens
        content = resp.choices[0].message.content
        parsed, reason = validate_response(content)
        if parsed is not None:
            return parsed, total_tokens
        last_reason = reason
        if val_attempt < MAX_VALIDATION_RETRIES:
            log.warning(f"  validate ไม่ผ่าน ({reason}) — retry ยิงใหม่ ({val_attempt + 1}/{MAX_VALIDATION_RETRIES})")

    return None, last_reason


# --------------------------------------------------------------------------
# Self-consistency: ยิง 2 ครั้ง, รวมผล
# --------------------------------------------------------------------------

def run_self_consistency(client, messages):
    """คืน (final_record_dict, total_tokens, reason_if_failed)"""
    runs = []
    total_tokens = 0
    for i in range(N_SELF_CONSISTENCY):
        parsed, tok_or_reason = call_qwen_validated(client, messages)
        if parsed is None:
            return None, total_tokens, f"run {i+1}/{N_SELF_CONSISTENCY} ล้มเหลว: {tok_or_reason}"
        runs.append(parsed)
        total_tokens += tok_or_reason

    low_confidence = False
    final = {}
    for f in ALL_FIELDS:
        vals = [r[f] for r in runs]
        if max(vals) - min(vals) > CONSISTENCY_THRESHOLD:
            low_confidence = True
        final[f] = round(sum(vals) / len(vals))

    # evidence_quotes: เก็บของรอบแรกที่ field นั้น != 0 (ไม่รวม/ไม่แต่งใหม่ — เก็บของจริงจากรอบใด
    # รอบหนึ่งที่ตอบมา ไม่ใช่การเดา)
    evidence = {}
    for f in ALL_FIELDS:
        if final[f] != 0:
            for r in runs:
                if r.get(f, 0) != 0 and r["evidence_quotes"].get(f):
                    evidence[f] = r["evidence_quotes"][f]
                    break

    final["low_confidence"] = low_confidence
    final["evidence_quotes"] = evidence
    final["_runs"] = runs  # เก็บดิบไว้ตรวจสอบย้อนหลังได้ (ไม่ต้องใช้ตอน analysis ปกติ)
    return final, total_tokens, None


# --------------------------------------------------------------------------
# Checkpoint helpers (เหมือนแนวทาง src/s3_sector_views.py)
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


def rebuild_csv_from_jsonl():
    if not OUT_JSONL.exists():
        return 0
    rows = []
    with open(OUT_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            row = {k: v for k, v in rec.items() if k != "_runs"}
            row["evidence_quotes"] = json.dumps(row.get("evidence_quotes", {}), ensure_ascii=False)
            rows.append(row)
    if not rows:
        return 0
    df = pd.DataFrame(rows).sort_values(["date", "source"]).reset_index(drop=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    return len(df)


# --------------------------------------------------------------------------
# Test mode
# --------------------------------------------------------------------------

def run_test(client, news_df):
    with_prev = news_df.dropna(subset=["prev_text"])
    fomc = with_prev[with_prev["source"] == "FOMC_statement"].sort_values("date").tail(1)
    beige = with_prev[with_prev["source"] == "Beige_Book"].sort_values("date").tail(2)
    sample = pd.concat([fomc, beige]).sort_values("date")

    print("=" * 70)
    print(f"TEST MODE: {len(sample)} ข่าว (1 FOMC ล่าสุด + 2 Beige Book ล่าสุด, มี prev_text ครบ)")
    print("=" * 70)

    total_tok = 0
    for _, row in sample.iterrows():
        print(f"\n--- {row['source']} | {row['date'].date()} (prev: {row['prev_date'].date()}) ---")
        messages = build_messages(row["source"], row["date"].date(), row["text"],
                                   row["prev_date"].date(), row["prev_text"])
        final, tok, reason = run_self_consistency(client, messages)
        total_tok += tok
        if final is None:
            print(f"!! FAILED: {reason}")
            continue
        print(f"tokens ใช้ไป (2 runs รวม): {tok}")
        print(f"low_confidence: {final['low_confidence']}")
        for f in ALL_FIELDS:
            q = final["evidence_quotes"].get(f, "")
            print(f"  {f:28s} = {final[f]:+d}" if f in FIELDS_RANGE_PM2 else f"  {f:28s} = {final[f]}")
            if q:
                print(f"      quote: {q[:150]!r}")
        print(f"  raw runs: {[{k: r[k] for k in ALL_FIELDS} for r in final['_runs']]}")

    n = len(sample)
    print("\n" + "=" * 70)
    print(f"TEST SUMMARY: {n} ข่าว, token รวม {total_tok:,} "
          f"(เฉลี่ย {total_tok/n:,.0f}/ข่าว, ประเมินรันเต็ม 452 ข่าว ~{total_tok/n*452:,.0f} tokens)")
    print(">>> test mode เท่านั้น ไม่ได้เซฟไฟล์ <<<")


# --------------------------------------------------------------------------
# Full mode
# --------------------------------------------------------------------------

def run_full(client, news_df, token_budget=TOKEN_BUDGET):
    with_prev = news_df.dropna(subset=["prev_text"]).sort_values("date").reset_index(drop=True)
    n_skipped_no_prev = len(news_df) - len(with_prev)

    done_keys = load_done_keys()
    if done_keys:
        log.info(f"พบ checkpoint เดิม {len(done_keys)} ข่าวที่ทำไปแล้ว จะ resume ต่อ")

    todo = [row for _, row in with_prev.iterrows()
            if (str(row["date"].date()), row["source"], row["url"]) not in done_keys]

    log.info(f"ข่าวทั้งหมดที่มี prev release ให้เทียบ: {len(with_prev)} "
             f"(ข้าม {n_skipped_no_prev} ข่าวแรกสุดของแต่ละ source — ไม่มี baseline เทียบ)")
    log.info(f"เหลือต้องทำ: {len(todo)} ข่าว")

    if not todo:
        log.info("ทำครบแล้ว ไม่มีอะไรต้องทำเพิ่ม")
        rebuild_csv_from_jsonl()
        return

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    total_tok = 0
    n_done = 0
    failures = []
    stop_reason = "completed"

    for i, row in enumerate(todo, 1):
        messages = build_messages(row["source"], row["date"].date(), row["text"],
                                   row["prev_date"].date(), row["prev_text"])
        try:
            final, tok, reason = run_self_consistency(client, messages)
        except RuntimeError as e:
            log.warning("=" * 60)
            log.warning(f"API ล้มเหลวเกิน retry limit — หยุดแบบปลอดภัย ({e})")
            log.warning(f"ทำไปแล้วรอบนี้: {n_done}/{len(todo)} (checkpoint เซฟไว้แล้ว resume ต่อได้)")
            log.warning("=" * 60)
            stop_reason = "api_error"
            break

        total_tok += tok
        if final is None:
            log.warning(f"ข่าว {row['url']} ล้มเหลว ({reason}) — ข้ามไป ไม่เดาผล")
            failures.append({"date": str(row["date"].date()), "source": row["source"],
                              "url": row["url"], "reason": reason})
            continue

        record = {
            "date": str(row["date"].date()), "source": row["source"], "url": row["url"],
            "prev_date": str(row["prev_date"].date()),
            **{f: final[f] for f in ALL_FIELDS},
            "low_confidence": final["low_confidence"],
            "evidence_quotes": final["evidence_quotes"],
            "_runs": final["_runs"],
        }
        with open(OUT_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        rebuild_csv_from_jsonl()

        n_done += 1
        if n_done % PROGRESS_EVERY == 0:
            log.info(f"[{n_done + len(done_keys)}/{len(with_prev)}] token สะสมรอบนี้: {total_tok:,}")

        if total_tok >= token_budget:
            log.warning(f"token สะสมรอบนี้ ({total_tok:,}) ถึง safety budget — หยุด resume ต่อได้")
            stop_reason = "token_budget"
            break

    if failures:
        FAILURES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FAILURES_PATH, "w", encoding="utf-8") as f:
            json.dump(failures, f, ensure_ascii=False, indent=2)

    log.info("=" * 60)
    log.info(f"FULL RUN SUMMARY — หยุดเพราะ: {stop_reason}")
    log.info(f"สำเร็จรอบนี้: {n_done}, ล้มเหลว/ข้ามรอบนี้: {len(failures)}")
    log.info(f"token ใช้ไปรอบนี้: {total_tok:,}")
    n_total = rebuild_csv_from_jsonl()
    log.info(f"รวมทั้งหมดใน {OUT_CSV}: {n_total} ข่าว")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["test", "full"], default="test")
    args = parser.parse_args()

    news_df = load_ordered_news()
    client = get_client()

    if args.mode == "test":
        run_test(client, news_df)
    else:
        run_full(client, news_df)


if __name__ == "__main__":
    main()
