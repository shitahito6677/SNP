"""
fundamentals.py — ดึง fundamental data ต่อ ticker (P/E ratio, market cap, EPS ฯลฯ) จาก Alpha
Vantage `OVERVIEW` endpoint (คนละ endpoint จาก `collect_alpha_vantage.py` ที่ใช้ดึงข่าว sector
— endpoint นี้คืนข้อมูลบริษัทตัวเดียวแบบ snapshot ปัจจุบัน ไม่ใช่ time series)

ใช้ API key เดียวกับ `sandbox/scripts/collect_alpha_vantage.py` (`ALPHA_VANTAGE_API_KEY` ใน
.env) แต่ free tier จำกัด 25 req/day รวมทุก endpoint ของ key นั้น — ต้อง cache ผลไว้เป็นไฟล์
เสมอ (`sandbox/data/fundamentals/{TICKER}.json`, gitignored เหมือน experiments.db เพราะ
regenerable + เป็นข้อมูลจาก API ภายนอกที่เปลี่ยนได้ทุกวัน) แล้วใช้ cache นั้นถ้ายังไม่หมดอายุ
(`CACHE_TTL_SECONDS`) ไม่เรียก API ซ้ำทุกครั้งที่เปิด dashboard

ถ้าเรียก API ไม่สำเร็จ (ไม่มี key, rate limit, network error) แต่มี cache เก่าอยู่ — คืน cache
เก่านั้นพร้อม `stale: true` แทนที่จะ error ทันที (ห้ามเดาตัวเลขใหม่ แต่การโชว์ตัวเลขจริงที่เคย
ดึงมาแล้วพร้อม label ว่าเก่า ดีกว่าจอว่างเปล่า) ถ้าไม่มี cache เลยและเรียกไม่สำเร็จ คืน
{"error": ...} ตรงๆ ให้ UI แสดง ไม่ fabricate ค่าไหนทั้งสิ้น
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

SANDBOX_DIR = Path(__file__).resolve().parent
CACHE_DIR = SANDBOX_DIR / "data" / "fundamentals"
CACHE_TTL_SECONDS = 24 * 60 * 60  # OVERVIEW เป็นข้อมูลรายวัน/รายไตรมาส ไม่ต้อง refresh ถี่กว่านี้
API_URL = "https://www.alphavantage.co/query"
HEADERS = {"User-Agent": "sandbox-research-script/1.0 (contact: boeing6677@gmail.com)"}

# Alpha Vantage OVERVIEW field -> (ชื่อที่ใช้ในระบบนี้, ประเภทตัวเลข)
# เลือกเฉพาะ field ที่เกี่ยวกับการตัดสินใจลงทุนระดับ fundamental โดยตรง (ไม่ดึงทุก field ที่
# endpoint คืนมา — OVERVIEW มีมากกว่า 50 field ส่วนใหญ่ไม่เกี่ยวกับ ensemble นี้)
NUMERIC_FIELDS = {
    "PERatio": "pe_ratio",
    "PEGRatio": "peg_ratio",
    "EPS": "eps",
    "MarketCapitalization": "market_cap",
    "DividendYield": "dividend_yield",
    "Beta": "beta",
    "ProfitMargin": "profit_margin",
    "ReturnOnEquityTTM": "roe_ttm",
    "52WeekHigh": "week52_high",
    "52WeekLow": "week52_low",
    "AnalystTargetPrice": "analyst_target_price",
}
TEXT_FIELDS = {
    "Name": "name",
    "Sector": "sector",
    "Industry": "industry",
}


def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}.json"


def _load_cache(ticker: str):
    path = _cache_path(ticker)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _save_cache(ticker: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with _cache_path(ticker).open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _to_float(raw):
    """Alpha Vantage คืนตัวเลขเป็น string เสมอ และใช้ "None" (string) แทนค่าที่ไม่มี — ต้องแปลง
    "None"/""/"-" ทั้งหมดเป็น Python None ไม่ใช่ 0.0 (0.0 คือค่าจริงที่ต่างจาก "ไม่มีข้อมูล")"""
    if raw is None:
        return None
    raw = str(raw).strip()
    if raw in ("", "None", "-", "n/a"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_overview(raw: dict, ticker: str) -> dict:
    parsed = {"ticker": ticker}
    for av_key, out_key in NUMERIC_FIELDS.items():
        parsed[out_key] = _to_float(raw.get(av_key))
    for av_key, out_key in TEXT_FIELDS.items():
        val = (raw.get(av_key) or "").strip()
        parsed[out_key] = val if val and val != "None" else None
    return parsed


def _fetch_overview(ticker: str, api_key: str) -> dict:
    url = f"{API_URL}?function=OVERVIEW&symbol={ticker}&apikey={api_key}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def get_fundamentals(ticker: str, force_refresh: bool = False) -> dict:
    """คืน fundamental snapshot ของ ticker — ใช้ cache ถ้ายังไม่หมดอายุ (เว้นแต่
    force_refresh=True) ไม่งั้นเรียก Alpha Vantage OVERVIEW จริง แล้ว fallback กลับไปใช้ cache
    เก่า (มาร์ค stale=True) ถ้าเรียกไม่สำเร็จ"""
    cached = _load_cache(ticker)
    now = time.time()
    if cached and not force_refresh and (now - cached.get("fetched_at", 0)) < CACHE_TTL_SECONDS:
        return {**cached, "stale": False}

    load_dotenv()
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        if cached:
            return {**cached, "stale": True, "error": "ไม่พบ ALPHA_VANTAGE_API_KEY ใน .env — แสดง cache เก่า"}
        return {"ticker": ticker, "error": "ไม่พบ ALPHA_VANTAGE_API_KEY ใน .env"}

    try:
        raw = _fetch_overview(ticker, api_key)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        if cached:
            return {**cached, "stale": True, "error": f"เรียก API ไม่สำเร็จ ({type(e).__name__}) — แสดง cache เก่า"}
        return {"ticker": ticker, "error": f"เรียก API ไม่สำเร็จ: {type(e).__name__}: {e}"}

    # Alpha Vantage คืน HTTP 200 เสมอแม้ rate-limited/invalid ticker — ต้องเช็ค payload shape
    # เอง ("Note"/"Information" = rate limit, {} หรือไม่มี "Symbol" = ticker ไม่เจอ/error อื่น)
    if not raw or "Symbol" not in raw:
        note = raw.get("Note") or raw.get("Information") if isinstance(raw, dict) else None
        err = note or f"ไม่มีข้อมูล OVERVIEW สำหรับ {ticker} (อาจโดน rate limit ของ free tier: 25 req/day)"
        if cached:
            return {**cached, "stale": True, "error": err}
        return {"ticker": ticker, "error": err}

    parsed = _parse_overview(raw, ticker)
    parsed["fetched_at"] = now
    parsed["source"] = "alpha_vantage_overview"
    _save_cache(ticker, parsed)
    return {**parsed, "stale": False}
