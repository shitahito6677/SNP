"""
Real historical macro news data (Phase 3 follow-up fix) — connects the Dashboard's macro (C)
event markers to the REAL FOMC/Beige Book news + FinBERT sentiment scores that already exist
in the repo from Model C's data pipeline, instead of showing only manually-injected events.

**เคยเป็นบั๊ก/gap**: ก่อนหน้านี้ macro (C) event บน Dashboard มาจาก
`sandbox/data/manual_events.csv` เท่านั้น (Phase 3 manual injection) ซึ่งว่างเปล่าถ้ายังไม่มี
ใคร inject event เอง — real historical data (477 ข่าวจริงจาก `src/s1_fetch_news.py` ..
`src/s4_sentiment.py`) ไม่เคยถูกเชื่อมเข้า dashboard เลยตั้งแต่ Phase 2 เป็นต้นมา ทำให้
NVDA (หรือ ticker ไหนก็ตาม) โชว์ macro events = 0 ถ้ายังไม่เคย inject เอง — **ไม่ใช่บั๊ก
query/filter วันที่**, เป็นเพราะ feature นี้ไม่เคยถูกสร้างมาก่อน (ดู experiments/log.md)

ไฟล์นี้อ่าน 2 ไฟล์จริงจาก root ของ repo (ไม่แก้ไฟล์เดิม แค่อ่าน):
    - data/raw/macro_news_raw.parquet    (date, text, source, url — จาก s1_fetch_news.py)
    - data/processed/sentiment.parquet   (date, source, url, sent_XLK..sent_XLC — จาก s4_sentiment.py)
join กันด้วย url แล้วแปลง continuous score (P(positive)-P(negative), ช่วง [-1,1]) เป็น
discrete class (positive/neutral/negative) ด้วย threshold ±0.1 (ดูเหตุผลของค่านี้ด้านล่าง)

หมายเหตุสำคัญ: นี่คือ**ข้อมูลจริง** (real Qwen view text + real FinBERT score) ไม่ใช่ stub —
`is_stub` ของ event พวกนี้จึงเป็น `False` เสมอ ต่างจาก `model_c.predict()` (Phase 1) ที่ยังเป็น
stub สำหรับ headline **ใหม่** ที่ยังไม่เคยผ่าน pipeline จริง — สองเรื่องนี้คนละเรื่องกัน
(ดู sandbox/inference/README.md)
"""

from pathlib import Path

import pandas as pd

from sandbox import config

REPO_ROOT = Path(__file__).resolve().parent.parent
MACRO_NEWS_PATH = REPO_ROOT / "data" / "raw" / "macro_news_raw.parquet"
SENTIMENT_PATH = REPO_ROOT / "data" / "processed" / "sentiment.parquet"

# Threshold แปลง continuous score -> discrete class ตัดสินใจจากการดูการกระจายจริงของข้อมูล
# (ไม่ใช่เดา — รันแล้วเห็นว่า median ของแต่ละ sector อยู่ไกลจาก 0 มาก ยกเว้นไม่กี่ sector
# ที่ p25 ใกล้ 0, ค่าส่วนใหญ่กระจุกใกล้ ±0.9 — ธนาคาร ±0.1 กันไม่ให้ noise เล็กน้อยรอบ 0 ถูก
# classify เป็น positive/negative เกินจริง แต่ก็ไม่กว้างเกินจนกลืนสัญญาณ bias ที่ตั้งใจจะโชว์)
POSITIVE_THRESHOLD = 0.1
NEGATIVE_THRESHOLD = -0.1

_cache = None


def _score_to_class(score: float) -> str:
    if score >= POSITIVE_THRESHOLD:
        return "positive"
    if score <= NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def _load() -> pd.DataFrame:
    global _cache
    if _cache is not None:
        return _cache

    if not MACRO_NEWS_PATH.exists() or not SENTIMENT_PATH.exists():
        _cache = pd.DataFrame(
            columns=["date", "source", "url", "text", *[f"sent_{e}" for e in config.SECTOR_ETF.values()]]
        )
        return _cache

    news = pd.read_parquet(MACRO_NEWS_PATH)[["date", "source", "url", "text"]]
    sentiment = pd.read_parquet(SENTIMENT_PATH)
    merged = news.merge(sentiment, on=["date", "source", "url"], how="inner")
    merged["date"] = pd.to_datetime(merged["date"]).dt.strftime("%Y-%m-%d")
    _cache = merged
    return _cache


def real_event_count() -> int:
    """จำนวนข่าวจริงที่เชื่อมต่อได้ (สำหรับแสดงใน model status) — นับจริงจากไฟล์ ไม่ hardcode"""
    return len(_load())


def load_real_macro_events_for_ticker(ticker: str) -> list:
    """คืน real macro (C) event ทั้งหมดของ ticker นี้ (ตาม sector ETF ของมัน) —
    is_stub=False เสมอเพราะเป็นข้อมูลจริงจาก pipeline ที่รันจริงแล้ว (Qwen + FinBERT)"""
    etf = config.ticker_to_etf(ticker)
    sent_col = f"sent_{etf}"

    df = _load()
    if sent_col not in df.columns:
        return []

    events = []
    for _, row in df.iterrows():
        score = float(row[sent_col])
        headline = row["text"][:200] + ("…" if len(row["text"]) > 200 else "")
        events.append(
            {
                "date": row["date"],
                "class": _score_to_class(score),
                "score": round(score, 4),
                "is_stub": False,
                "source": "real_historical",
                "headline": f"[{row['source']}] {headline}",
            }
        )
    return events
