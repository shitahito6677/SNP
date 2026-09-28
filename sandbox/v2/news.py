"""
ข่าว manual ของ sandbox v2 (source="manual") — ไม่ใช่ output ของโมเดล และ**ไม่ปนกับ training data**
(training data ของ Model C อยู่ที่ data/raw/, data/processed/ ที่ root — ไฟล์นี้เขียนแค่ sandbox/v2/data/manual_news.jsonl)

- detect(): หา ticker ที่ถูกพูดถึงในข้อความ (alias dict + ticker รูปแบบ $TSLA / (TSLA)) → เป็น "ข้อเสนอ" ให้ผู้ใช้ยืนยันทีละตัว
- keyword มหภาค (Fed, CPI, tariff …) → แนะนำให้ติดเป็นข่าว C (ผู้ใช้ต้องยืนยัน)
- วันที่ตลาดปิด → เสนอวันทำการถัดไป
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg, prices

SUFFIX = re.compile(r"(,?\s+(Inc\.?|Incorporated|Corp\.?|Corporation|Co\.?|Company|Ltd\.?|plc|PLC|Holdings?|Group|N\.V\.|S\.A\.|L\.P\.|Class [A-C]|\(The\)))+$")
# alias ที่ชื่อบริษัทเต็มจับไม่ได้ (ชื่อเล่น/ชื่อเดิม/ชื่อไทย) — case-sensitive
CUSTOM_ALIASES = {
    "Nvidia": "NVDA", "NVIDIA": "NVDA", "เอ็นวิเดีย": "NVDA", "Google": "GOOGL", "Alphabet": "GOOGL", "กูเกิล": "GOOGL",
    "Facebook": "META", "Meta": "META", "เมตา": "META", "Amazon": "AMZN", "อเมซอน": "AMZN", "Apple": "AAPL", "แอปเปิล": "AAPL",
    "Microsoft": "MSFT", "ไมโครซอฟท์": "MSFT", "Tesla": "TSLA", "เทสลา": "TSLA", "Berkshire": "BRK-B", "JPMorgan": "JPM",
    "JP Morgan": "JPM", "Goldman Sachs": "GS", "Goldman": "GS", "Exxon": "XOM", "ExxonMobil": "XOM", "Chevron": "CVX",
    "Walmart": "WMT", "Disney": "DIS", "Netflix": "NFLX", "Intel": "INTC", "AMD": "AMD", "Coca-Cola": "KO", "Coke": "KO",
    "PepsiCo": "PEP", "Pepsi": "PEP", "Boeing": "BA", "FedEx": "FDX", "Schwab": "SCHW", "UnitedHealth": "UNH", "Visa": "V",
    "Mastercard": "MA", "Salesforce": "CRM", "Oracle": "ORCL", "Broadcom": "AVGO", "Costco": "COST", "McDonald's": "MCD",
    "Starbucks": "SBUX", "Nike": "NKE", "Pfizer": "PFE", "Moderna": "MRNA", "Eli Lilly": "LLY", "Lilly": "LLY",
    "Johnson & Johnson": "JNJ", "J&J": "JNJ", "Bank of America": "BAC", "Wells Fargo": "WFC", "Citigroup": "C", "Citi": "C",
    "Morgan Stanley": "MS", "Caterpillar": "CAT", "3M": "MMM", "Ford": "F", "General Motors": "GM", "AT&T": "T",
    "Verizon": "VZ", "Comcast": "CMCSA", "IBM": "IBM", "Adobe": "ADBE", "PayPal": "PYPL", "Uber": "UBER", "Airbnb": "ABNB",
    "Palantir": "PLTR", "Micron": "MU", "Qualcomm": "QCOM", "Texas Instruments": "TXN", "Home Depot": "HD", "Lowe's": "LOW",
    "ExxonMobil Corp": "XOM", "Occidental": "OXY", "Berkshire Hathaway": "BRK-B",
}
# คำที่เป็นทั้ง ticker และคำภาษาอังกฤษทั่วไป — ไม่จับจากตัวพิมพ์ใหญ่ลอย ๆ (ต้องมี $ หรือวงเล็บ)
TICKER_STOPWORDS = {"A", "ALL", "ARE", "CAN", "CEO", "CFO", "EPS", "ETF", "FOR", "GDP", "IT", "KEY", "LOW", "NOW", "ON", "ONE",
                    "PAY", "SEE", "SO", "THE", "USA", "US", "WELL", "AI", "CPI", "PCE", "FED", "IPO", "SEC", "NYSE", "BIG", "DAY",
                    "HAS", "NEW", "HD", "GE", "C", "F", "T", "V", "K", "L", "O", "D", "J", "MA", "MS", "GS", "BA", "DG", "ES", "IR",
                    "AN", "OR", "AM", "PM", "UK", "EU", "Q", "DOW", "FAST", "MOS", "TECH", "LIN", "WAT", "AME", "APA", "CAT", "CAR"}
# ชื่อบริษัทแบบสั้นที่เป็นคำทั่วไป — ไม่ใช้เป็น alias (จับได้แต่จากชื่อเต็ม/alias เฉพาะ)
COMMON_WORDS = {"news", "match", "block", "ball", "fox", "target", "southern", "general", "public", "international", "first",
                "equity", "global", "american", "united", "national", "live", "gap", "best", "waters", "dollar", "coherent",
                "progressive", "principal", "state", "tapestry", "entergy", "delta", "visa", "apple", "amazon", "oracle",
                "republic", "realty", "prudential", "chubb", "regions", "truist", "invitation", "welltower", "citizens",
                "discover", "fortive", "masco", "carrier", "ventas", "hess", "cardinal", "sherwin", "linde", "moody's",
                "trade", "insulet", "ralph", "universal", "vistra", "copart", "equinix", "keurig", "lamb", "loews", "motorola"}
MACRO_KEYWORDS = [
    ("Fed", r"\bFed\b|Federal Reserve|\bFOMC\b|Powell|เฟด"), ("rates", r"rate (hike|cut)s?|interest rates?|\b(hold|held|holds|raise[sd]?|cuts?|hike[sd]?|keeps?|kept) (interest )?rates\b|ขึ้นดอกเบี้ย|ลดดอกเบี้ย|อัตราดอกเบี้ย"),
    ("inflation", r"\bCPI\b|\bPCE\b|inflation|เงินเฟ้อ"), ("jobs", r"jobs report|nonfarm|payrolls|unemployment|การจ้างงาน|ว่างงาน"),
    ("tariff", r"tariffs?|trade war|ภาษีนำเข้า|สงครามการค้า"), ("growth", r"\bGDP\b|recession|จีดีพี|ถดถอย"),
    ("yields", r"treasury yields?|bond yields?|10-year|พันธบัตร"),
]
SECTOR_KEYWORDS = {
    "XLE": r"\boil\b|crude|OPEC|natural gas|น้ำมัน", "XLF": r"\bbanks?\b|lenders?|credit|ธนาคาร", "XLK": r"chips?|semiconductor|software|เซมิคอนดักเตอร์|ชิป",
    "XLRE": r"real estate|housing|mortgage|REITs?|อสังหา", "XLU": r"utilit(y|ies)|power grid", "XLV": r"pharma|drug|health ?care|ยา",
    "XLY": r"retail|consumer spending|automakers?", "XLI": r"airlines?|industrial|manufacturing|freight", "XLB": r"metals?|steel|copper|chemicals?",
    "XLP": r"consumer staples|groceries|food prices", "XLC": r"telecom|media|advertising",
}


# label ความแรงของข่าว 5 ระดับ = ค่าหลักของข่าว manual (ไม่ยุบเหลือ 3 กลุ่ม)
LABELS = {-2: "negative แรงมาก", -1: "negative", 0: "neutral (ไม่ค่อยมีผล)", 1: "positive", 2: "positive แรงมาก"}
SENTIMENT_TO_LABEL = {"positive": 1, "neutral": 0, "negative": -1}  # ข่าวเก่า/ข้อความ positive-neutral-negative


# วิธีที่ใช้ตั้ง label — แยก Oracle test ออกจากสิ่งที่ทำได้จริง (ห้ามเดาแทนผู้ใช้: ไม่ระบุ = unknown)
LABEL_METHODS = {
    "hindsight": "hindsight — label ตอนรู้ผลราคาจริงแล้ว (Oracle test)",
    "real_time": "real-time — label จากเนื้อข่าว ณ วันที่ข่าวออก ไม่รู้ผลล่วงหน้า",
    "unknown": "ยังไม่ระบุ — ไม่ควรใช้แปลผลจนกว่าจะระบุ",
}


def label_method_of(n: dict) -> str:
    m = n.get("label_method")
    return m if m in LABEL_METHODS else "unknown"


def label_class(label: int) -> str:
    """3 คลาสแบบ output ของ Model B (ดี/ไม่กระทบ/แย่) — ใช้เฉพาะจุดที่ต้องเข้ากับเกณฑ์กรองของ B/C เท่านั้น ไม่เขียนทับ label"""
    return "positive" if label >= 1 else "negative" if label <= -1 else "neutral"


def label_tag(label: int) -> str:
    """เช่น "-2 negative แรงมาก", "0 neutral (ไม่ค่อยมีผล)", "+1 positive" """
    return f"{label:+d} {LABELS[label]}" if label else f"0 {LABELS[0]}"


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v)


def label_of(n: dict) -> int:
    """label -2..+2 ของข่าวที่บันทึกไว้ — อ่านได้ทุกรูปแบบที่เคยเขียนลงไฟล์ โดยไม่แก้ไฟล์เดิม:
    1) `label` (รูปแบบปัจจุบัน)
    2) `label_raw` + `label_scale` (ข่าวที่นำเข้าจาก CSV ช่วง F1 แรก ซึ่งเก็บ sentiment 3 กลุ่มเป็นหลัก) → คืนความแรงเดิม
    3) `sentiment` อย่างเดียว (ข่าวที่พิมพ์เองก่อนมี 5 ระดับ) → +1 / 0 / -1"""
    v = n.get("label")
    if _num(v) and float(v).is_integer() and int(v) in LABELS:
        return int(v)
    raw, sc = n.get("label_raw"), re.search(r"(\d+(?:\.\d+)?)", str(n.get("label_scale") or ""))
    if _num(raw) and sc and float(sc.group(1)) > 0 and abs(raw) <= float(sc.group(1)):
        y = raw * 2 / float(sc.group(1))
        return int(np.sign(y) * np.floor(abs(y) + 0.5))
    return SENTIMENT_TO_LABEL.get(n.get("sentiment"), 0)


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@lru_cache(maxsize=1)
def alias_table() -> list:
    """[(alias, ticker, kind)] เรียงจาก alias ยาวไปสั้น (จับชื่อยาวก่อน เช่น 'Bank of America' ก่อน 'America')"""
    man = prices.manifest()["tickers"]
    out = {}
    for t, r in man.items():
        if r.get("kind") != "stock" or r.get("status") not in ("ok", "partial") or not r.get("name"):
            continue
        full = r["name"].strip()
        short = SUFFIX.sub("", full).strip()
        for a in {full, short}:
            if len(a) < 3 or (" " not in a and a.lower() in COMMON_WORDS):
                continue
            out.setdefault(a, (t, "name"))
    for a, t in CUSTOM_ALIASES.items():
        if t in man:
            out[a] = (t, "alias")
    return sorted(((a, t, k) for a, (t, k) in out.items()), key=lambda x: -len(x[0]))


def _info(t):
    r = prices.manifest()["tickers"].get(t, {})
    return {"ticker": t, "name": r.get("name") or t, "sector": r.get("sector") or "Unknown",
            "etf": cfg.SECTOR_ETFS.get(r.get("sector") or "")}


def detect(text: str) -> dict:
    text = text or ""
    found, taken = {}, []

    def add(t, match, how, start, end):
        if any(s < end and start < e for s, e in taken):
            return
        taken.append((start, end))
        if t not in found:
            found[t] = {**_info(t), "match": match, "how": how}

    man = prices.manifest()["tickers"]
    for m in re.finditer(r"@([A-Za-z][A-Za-z.\-]{0,6})\b", text):  # @mention ที่พิมพ์ไว้
        t = m.group(1).upper().replace(".", "-")
        if t in man:
            add(t, m.group(0), "@mention", m.start(), m.end())
    for m in re.finditer(r"\$([A-Z][A-Z.\-]{0,6})\b|\(([A-Z][A-Z.\-]{0,6})\)", text):
        t = (m.group(1) or m.group(2)).replace(".", "-")
        if t in man and man[t].get("kind") == "stock":
            add(t, m.group(0), "ticker", m.start(), m.end())
    for alias, t, kind in alias_table():
        pat = r"(?<![\w&])" + re.escape(alias) + r"(?![\w&])" if alias.isascii() else re.escape(alias)
        for m in re.finditer(pat, text):
            add(t, m.group(0), kind, m.start(), m.end())
    for m in re.finditer(r"\b([A-Z]{3,5})\b", text):  # ticker พิมพ์ใหญ่ลอย ๆ (เข้มงวด)
        t = m.group(1)
        if t in man and man[t].get("kind") == "stock" and t not in TICKER_STOPWORDS:
            add(t, m.group(0), "ticker", m.start(), m.end())
    return {"mentions": sorted(found.values(), key=lambda x: text.find(x["match"])), "macro": macro_info(text)}


def macro_info(text: str) -> dict:
    """คำบ่งชี้ข่าวมหภาค (แนะนำเป็นข่าว C) — แยกจาก detect() เพราะถูกกว่ามาก (ใช้ตอนไฟล์มี column ticker อยู่แล้ว)"""
    macro = [k for k, pat in MACRO_KEYWORDS if re.search(pat, text or "", re.I)]
    sectors = [e for e, pat in SECTOR_KEYWORDS.items() if re.search(pat, text or "", re.I)]
    return {"keywords": macro, "suggest": bool(macro), "sectors": sectors}


@lru_cache(maxsize=2)
def _calendar(mtime: float) -> pd.DatetimeIndex:
    return pd.read_parquet(cfg.PRICES_DIR / f"{cfg.BENCHMARK}.parquet").index


def trading_day_info(date: str) -> dict:
    d = pd.Timestamp(date).normalize()
    f = cfg.PRICES_DIR / f"{cfg.BENCHMARK}.parquet"
    cal = _calendar(f.stat().st_mtime)  # อ่านไฟล์ครั้งเดียวต่อเวอร์ชัน (import CSV หลายร้อยแถวเรียกทุกแถว)
    if d <= cal[-1]:
        ok = d in cal
        nxt = cal[cal >= d][0] if not ok else d
    else:  # อนาคตเกินข้อมูล → ใช้วันจันทร์–ศุกร์
        ok = d.weekday() < 5
        nxt = d if ok else d + pd.offsets.BDay(1)
    reason = None if ok else ("วันเสาร์/อาทิตย์" if d.weekday() >= 5 else "วันหยุดตลาดสหรัฐ")
    return {"date": str(d.date()), "is_trading_day": bool(ok), "next_trading_day": str(pd.Timestamp(nxt).date()), "reason": reason}


def _load() -> list:
    if not cfg.MANUAL_NEWS.exists():
        return []
    return [json.loads(x) for x in cfg.MANUAL_NEWS.read_text(encoding="utf-8").splitlines() if x.strip()]


def _write(rows):
    cfg.MANUAL_NEWS.parent.mkdir(parents=True, exist_ok=True)
    cfg.MANUAL_NEWS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


# ---------------------------------------------------------------- content hash (กันข่าวซ้ำตอน import ไฟล์เดิมซ้ำ)
HEADLINE_MAX = 500


def normalize_headline(h: str) -> str:
    """ตัดช่องว่างหัวท้าย · ตัวพิมพ์เล็ก · ยุบช่องว่างซ้อน — ใช้ความยาวเท่าที่บันทึกจริง (HEADLINE_MAX)"""
    return " ".join((h or "").strip()[:HEADLINE_MAX].lower().split())


def content_hash(ticker: str, publish_date: str, headline: str) -> str:
    """sha256(ticker | publish_date | normalize(headline)) — ข่าวไม่มี ticker (มหภาค) ใช้ ticker = "macro" """
    return hashlib.sha256(f"{ticker}|{publish_date}|{normalize_headline(headline)}".encode("utf-8")).hexdigest()


def hashes_for(tickers, publish_date: str, headline: str) -> list:
    return sorted(content_hash(t, publish_date, headline) for t in (sorted(set(tickers or [])) or ["macro"]))


def ensure_hashes() -> int:
    """migrate: ข่าวที่บันทึกก่อนมี content hash → เติม `content_hashes` (สำรองไฟล์เดิมไว้ก่อนเขียนครั้งแรก) — คืนจำนวนที่เติม"""
    rows = _load()
    todo = [r for r in rows if not r.get("content_hashes")]
    if not todo:
        return 0
    bak = cfg.MANUAL_NEWS.with_name(cfg.MANUAL_NEWS.name + ".bak-before-content-hash")
    if not bak.exists():
        bak.write_bytes(cfg.MANUAL_NEWS.read_bytes())
    for r in todo:
        r["content_hashes"] = hashes_for(r.get("tickers"), r["date"], r.get("headline", ""))
    _write(rows)
    return len(todo)


def hash_index(rows=None) -> tuple:
    """(hash → id, (ticker, publish_date) → [ข่าว]) ของข่าวที่ยังไม่ถูกลบ — lookup O(1) ต่อแถว (ไฟล์โตได้หลายพันแถว)"""
    by_hash, by_td = {}, {}
    for r in (_load() if rows is None else rows):
        if r.get("deleted"):
            continue
        for h in r.get("content_hashes") or hashes_for(r.get("tickers"), r["date"], r.get("headline", "")):
            by_hash.setdefault(h, r["id"])
        for t in r.get("tickers") or []:
            by_td.setdefault((t, r["date"]), []).append(r)
    return by_hash, by_td


def dup_check(tickers, publish_date: str, headline: str, by_hash: dict, by_td: dict) -> dict:
    """exact = ข่าวเดิมทุก ticker (ข้ามอัตโนมัติ) · review = ticker+วันที่ตรงแต่ headline ต่าง/ซ้ำบางส่วน (ผู้ใช้ตัดสินใจ) · new"""
    hs = hashes_for(tickers, publish_date, headline)
    hit = [h for h in hs if h in by_hash]
    if hs and len(hit) == len(hs):
        return {"status": "exact", "hashes": hs, "ids": sorted({by_hash[h] for h in hit})}
    same_day = {}
    for t in tickers or []:
        for r in by_td.get((t, publish_date), []):
            if content_hash(t, publish_date, headline) not in (r.get("content_hashes") or []):
                same_day[r["id"]] = r
    if hit or same_day:
        return {"status": "review", "hashes": hs, "partial": bool(hit),
                "matches": [{"id": r["id"], "headline": r.get("headline", ""), "tickers": r.get("tickers"), "date": r["date"],
                             "label": label_of(r), "label_method": label_method_of(r)} for r in same_day.values()]}
    return {"status": "new", "hashes": hs}


def list_news(limit=300) -> list:
    return [dict(r, label=label_of(r), label_method=label_method_of(r)) for r in reversed(_load()) if not r.get("deleted")][:limit]


def ticker_counts() -> dict:
    """จำนวนข่าว manual (ที่ยังไม่ถูกลบ) ต่อ ticker — ใช้ใน gallery หน้าหุ้นรายตัว"""
    out = {}
    for r in _load():
        if not r.get("deleted"):
            for t in r.get("tickers") or []:
                out[t] = out.get(t, 0) + 1
    return out


def method_summary() -> dict:
    """จำนวนข่าวตามวิธี label + ข่าวที่ยังไม่ระบุ จัดกลุ่มตามชุดที่นำเข้า (import_batch หรือ นาทีที่บันทึก) ให้ผู้ใช้ระบุทีละชุด"""
    live = [r for r in _load() if not r.get("deleted")]
    counts = {m: 0 for m in LABEL_METHODS}
    batches = {}
    for r in live:
        m = label_method_of(r)
        counts[m] += 1
        if m == "unknown":
            key = r.get("import_batch") or f"บันทึกเมื่อ {str(r.get('created_at', ''))[:16].replace('T', ' ')}"
            b = batches.setdefault(key, {"batch": key, "ids": [], "tickers": set(), "sample": r.get("headline", "")[:120],
                                         "sample_reason": (r.get("extra") or {}).get(next((k for k in (r.get("extra") or {}) if "reason" in k.lower()
                                                                                       or "เหตุผล" in k), ""), "")[:200]})
            b["ids"].append(r["id"])
            b["tickers"].update(r.get("tickers") or [])
    out = [dict(b, n=len(b["ids"]), tickers=sorted(b["tickers"])[:12]) for b in batches.values()]
    return {"counts": counts, "unknown_batches": sorted(out, key=lambda b: b["batch"])}


def set_label_method(ids: list, method: str) -> int:
    """ผู้ใช้ระบุวิธี label ของข่าวที่บันทึกไว้แล้ว (ทีละรายการหรือทั้งชุด) — ไม่แตะ label/เนื้อข่าว"""
    if method not in LABEL_METHODS:
        raise ValueError(f"label_method ต้องเป็น {sorted(LABEL_METHODS)}")
    want, n = set(ids or []), 0
    rows = _load()
    for r in rows:
        if r["id"] in want and not r.get("deleted") and label_method_of(r) != method:
            r["label_method"] = method
            r["updated_at"] = _now()
            n += 1
    if n:
        _write(rows)
    return n


def add(item: dict) -> dict:
    """เพิ่มข่าว 1 รายการ (ฟอร์มพิมพ์เอง) — ซ้ำเป๊ะกับข่าวที่มีอยู่ (ทุก ticker) = ValueError"""
    rows = _load()
    by_hash, _ = hash_index(rows)
    row = make_row(item)
    dup = [h for h in row["content_hashes"] if h in by_hash]
    if dup and len(dup) == len(row["content_hashes"]) and not item.get("allow_duplicate"):
        raise ValueError(f"ข่าวนี้มีอยู่แล้ว (ticker + วันที่ + หัวข่าวซ้ำเป๊ะกับข่าว {by_hash[dup[0]][:8]})")
    rows.append(row)
    _write(rows)
    return row


def commit_rows(items: list) -> dict:
    """บันทึกแถวจากหน้า preview CSV แบบ batch (อ่าน/เขียนไฟล์ครั้งเดียว) — ตรวจข่าวซ้ำใหม่ฝั่ง server เสมอ:
    exact → ข้ามอัตโนมัติ · review → ทำตาม dup_action ของผู้ใช้ (skip / replace / keep_both; ยังไม่เลือก = ไม่บันทึก) · new → บันทึกถ้าติ๊ก"""
    ensure_hashes()
    rows = _load()
    by_hash, by_td = hash_index(rows)
    by_id = {r["id"]: r for r in rows}
    out = {"saved": [], "skipped_exact": 0, "review_pending": 0, "replaced": 0, "skipped_by_user": 0, "invalid": 0, "errors": []}
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("skip_reasons"):
            out["invalid"] += 1
            continue
        try:
            date = str(pd.Timestamp(it["date"]).date())
            tick = sorted({str(t).upper() for t in it.get("tickers") or []})
            head = (it.get("headline") or "").strip()
            dup = dup_check(tick, date, head, by_hash, by_td)
            action = it.get("dup_action")
            if dup["status"] == "exact":
                out["skipped_exact"] += 1
                continue
            if dup["status"] == "review" and action not in ("replace", "keep_both"):
                out["review_pending" if action is None else "skipped_by_user"] += 1
                continue
            if dup["status"] == "new" and not it.get("include"):
                out["skipped_by_user"] += 1
                continue
            row = make_row(dict(it, effective_date=None))  # ผู้ใช้อาจแก้วันที่ใน preview → คำนวณวันที่มีผลใหม่
        except (ValueError, KeyError, TypeError) as e:
            out["errors"].append({"row": it.get("row"), "error": str(e).strip("'\"")})
            continue
        if dup["status"] == "review" and action == "replace":
            for m in dup["matches"]:
                old = by_id.get(m["id"])
                if old and not old.get("deleted"):
                    old.update(deleted=True, replaced_by=row["id"], updated_at=_now())
                    out["replaced"] += 1
            live_before = [r for r in rows if r["id"] not in {x["id"] for x in out["saved"]}]
            by_hash = hash_index(rows)[0]
            by_td = hash_index(live_before)[1]
        rows.append(row)
        by_id[row["id"]] = row
        for h in row["content_hashes"]:  # แถวซ้ำเป๊ะภายในไฟล์เดียวกัน → ตัวหลังข้ามอัตโนมัติ
            by_hash.setdefault(h, row["id"])
        # by_td ไม่เติมแถวจากไฟล์เดียวกัน: ข่าวต่างหัวข้อของหุ้นเดียวกันวันเดียวกันในไฟล์เดียว = คนละข่าว (ตรงกับที่ preview แสดง)
        out["saved"].append(row)
    if out["saved"] or out["replaced"]:
        _write(rows)
    return out


def make_row(item: dict) -> dict:
    """ตรวจ + สร้าง record ข่าว (ยังไม่บันทึก)"""
    headline = (item.get("headline") or "").strip()
    if not headline:
        raise ValueError("ต้องมี headline")
    tickers = sorted({t.upper() for t in item.get("tickers") or []})
    man = prices.manifest()["tickers"]
    bad = [t for t in tickers if t not in man]
    if bad:
        raise ValueError(f"ไม่รู้จัก ticker: {bad}")
    sectors = sorted({s for s in item.get("sectors") or [] if s in cfg.SECTOR_ETFS.values()})
    if not tickers and not sectors:
        raise ValueError("ต้องเลือกหุ้นอย่างน้อย 1 ตัว หรือยืนยันเป็นข่าวมหภาค (C) พร้อม sector")
    if item.get("label") is not None and item.get("label") != "":
        try:
            label = int(item["label"])
        except (TypeError, ValueError):
            label = None
        if label not in LABELS or float(item["label"]) != label:
            raise ValueError(f"label ต้องเป็นจำนวนเต็ม -2..+2 (ได้ {item['label']!r})")
    else:  # รูปแบบเดิม: sentiment 3 ค่า
        sentiment = item.get("sentiment", "neutral")
        if sentiment not in SENTIMENT_TO_LABEL:
            raise ValueError("ต้องระบุ label -2..+2 (หรือ sentiment positive / neutral / negative)")
        label = SENTIMENT_TO_LABEL[sentiment]
    if not item.get("date"):
        raise ValueError("ต้องมีวันที่")
    try:
        date = str(pd.Timestamp(item["date"]).date())
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"วันที่อ่านไม่ได้: {item['date']!r}") from None
    info = trading_day_info(date)
    eff = item.get("effective_date") or info["next_trading_day"]
    row = {"id": str(uuid.uuid4()), "created_at": _now(), "source": "manual", "headline": headline[:500],
           "body": (item.get("body") or "")[:BODY_MAX], "date": date, "effective_date": str(pd.Timestamp(eff).date()),
           "kind": "company" if tickers else "macro", "tickers": tickers, "sectors": sectors,
           "label": label, "label_method": item.get("label_method") or "unknown",
           "detected_by": item.get("detected_by") or {}, "deleted": False}
    if row["label_method"] not in LABEL_METHODS:
        raise ValueError(f"label_method ต้องเป็น {sorted(LABEL_METHODS)} (ได้ {row['label_method']!r})")
    if item.get("import_batch"):
        row["import_batch"] = str(item["import_batch"])[:200]
    if item.get("label_raw") is not None and item.get("label_raw") != label:  # ค่าในไฟล์ไม่ใช่ -2..+2 ตรง ๆ (ข้อความ/สเกลอื่น) → เก็บต้นฉบับ
        row["label_raw"] = item["label_raw"]
        row["label_scale"] = item.get("label_scale")
    if item.get("extra"):  # column ที่ระบบไม่รู้จัก (source_url, label_reason, …) → metadata ต่อแถว
        row["extra"] = {str(k)[:100]: str(v)[:BODY_MAX] for k, v in dict(item["extra"]).items()}
    row["content_hashes"] = hashes_for(tickers, date, row["headline"])
    return row


def delete(nid: str) -> bool:
    rows = _load()
    hit = False
    for r in rows:
        if r["id"] == nid:
            r["deleted"] = True
            hit = True
    _write(rows)
    return hit


# ---------------------------------------------------------------- CSV
# จับคู่ column ด้วย keyword ที่อยู่ "ในชื่อ" (ไม่สนวงเล็บ/คำไทยนำหน้า) เช่น "ข่าวแบบย่อ (short_news)" → headline
# (keyword, คะแนน) — คะแนนสูง = เจาะจงกว่า; จับคู่แบบ greedy คะแนนสูงก่อน, 1 column ใช้ได้กับ field เดียว
FIELD_KEYWORDS = {
    "ticker": [("ticker", 10), ("symbol", 10), ("สัญลักษณ์", 8)],
    "date": [("publish_date", 10), ("วันที่", 9), ("date", 8), ("published", 7), ("datetime", 7), ("time", 3)],
    "headline": [("headline", 10), ("short_news", 10), ("ข่าวแบบย่อ", 10), ("หัวข่าว", 9), ("title", 9), ("หัวข้อ", 9),
                 ("text", 2), ("ข่าว", 1)],
    "body": [("full_news", 10), ("ข่าวแบบเต็ม", 10), ("body", 9), ("content", 8), ("เนื้อหา", 8), ("summary", 7),
             ("description", 6)],
    "sentiment": [("sentiment", 10), ("label", 8), ("polarity", 8)],
}
FIELD_EXCLUDE = {"sentiment": ("reason", "เหตุผล", "explain")}  # "เหตุผลของ label (label_reason)" ไม่ใช่ label
FIELD_TH = {"ticker": "ticker", "date": "วันที่", "headline": "หัวข่าว (headline)", "body": "เนื้อข่าว (body)",
            "sentiment": "label/sentiment"}
NAME_HINT = ("stock", "company", "หุ้น", "บริษัท")  # column ชื่อบริษัท → ใช้ช่วยตรวจจับ ticker เมื่อไม่มี column ticker
TEXT_LABELS = {"positive": "positive", "pos": "positive", "bullish": "positive", "บวก": "positive",
               "negative": "negative", "neg": "negative", "bearish": "negative", "ลบ": "negative",
               "neutral": "neutral", "neu": "neutral", "กลาง": "neutral"}
BODY_MAX = 20000


def _col_score(col: str, field: str) -> int:
    low = col.lower().strip()
    if any(x in low for x in FIELD_EXCLUDE.get(field, ())):
        return 0
    inner = {x.strip() for x in re.findall(r"\(([^)]*)\)", low)} | {low}
    best = 0
    for kw, sc in FIELD_KEYWORDS[field]:
        if kw in inner:
            best = max(best, sc + 5)  # ชื่อตรงตัว หรือตรงกับส่วนในวงเล็บ
        elif kw in low:
            best = max(best, sc)
    return best


def guess_mapping(cols: list) -> dict:
    pairs = sorted(((_col_score(c, f), -i, f, c) for i, c in enumerate(cols) for f in FIELD_KEYWORDS), reverse=True)
    out, used = {f: None for f in FIELD_KEYWORDS}, set()
    for sc, _, f, c in pairs:
        if sc > 0 and out[f] is None and c not in used:
            out[f] = c
            used.add(c)
    return out


def label_scale(col: str | None, values: list):
    """สเกลของ label ตัวเลข: จากหัว column เช่น "(-2..+2)" ถ้ามี ไม่งั้นใช้ค่าสัมบูรณ์สูงสุดที่เจอในไฟล์ (ปัดขึ้น)"""
    if col:
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:\.\.|to|–|~)\s*\+?(\d+(?:\.\d+)?)", col)
        if m and float(m.group(2)) > 0:
            return float(m.group(2))
    nums = []
    for v in values:
        try:
            nums.append(abs(float(str(v).strip().replace("+", ""))))
        except ValueError:
            pass
    return float(np.ceil(max(nums))) if nums and max(nums) > 0 else None


def parse_label(v, scale):
    """ค่าในไฟล์ → (label -2..+2, ค่าดิบ, error) — label 5 ระดับคือค่าหลัก ไม่ยุบเหลือ 3 กลุ่ม
    ตัวเลขสเกล ±2 → ใช้ค่าตรง ๆ; สเกลอื่น (เช่น ±1, ±5) → เทียบสัดส่วนเป็น -2..+2 (ปัดครึ่งออกจาก 0) และเก็บค่าดิบไว้
    ข้อความ positive/neutral/negative (+ คำพ้อง) → +1 / 0 / -1"""
    s = ("" if v is None else str(v)).strip()
    if not s:
        return 0, None, None
    try:
        x = float(s.replace("+", ""))
    except ValueError:
        k = s.lower()
        lab = TEXT_LABELS.get(k) or TEXT_LABELS.get(k[:3])
        if lab is None:
            return None, s, f"label อ่านไม่ได้: '{s[:30]}' (รองรับตัวเลข -2..+2 หรือ positive/neutral/negative)"
        return SENTIMENT_TO_LABEL[lab], s, None
    if not np.isfinite(x) or not scale or abs(x) > scale:
        return None, s, f"label {s} อยู่นอกสเกล ±{scale:g}" if scale else f"label {s} อ่านไม่ได้"
    raw = int(x) if float(x).is_integer() else x
    y = x * 2 / scale
    return int(np.sign(y) * np.floor(abs(y) + 0.5)), raw, None


def _parse_tickers(raw: str, man) -> tuple:
    out, bad = [], []
    for t in re.split(r"[,;| ]+", raw or ""):
        t = t.strip().lstrip("$@").upper().replace(".", "-")
        if not t:
            continue
        (out if t in man and man[t].get("kind") == "stock" else bad).append(t)
    return sorted(set(out)), bad


def csv_preview(text: str, mapping: dict | None = None, limit=20000) -> dict:
    """อ่าน CSV → mapping ที่เดา (หรือที่ผู้ใช้เลือกเอง) + ทุกแถวพร้อมเหตุผลถ้าข้าม — ไม่บันทึกอะไร
    raise ValueError (ข้อความไทย) เฉพาะกรณีอ่านไฟล์ไม่ได้เลย; ปัญหารายแถว/ไม่มี column → แสดงใน preview"""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        raise ValueError("อ่านไฟล์ไม่ได้: ไฟล์ว่างเปล่า")
    if "�" in text[:2000]:
        raise ValueError("อ่านไฟล์ไม่ได้: encoding ไม่ใช่ UTF-8 (ลอง Save As → CSV UTF-8)")
    try:
        rd = csv.DictReader(io.StringIO(text, newline=""))
        cols = [c for c in (rd.fieldnames or []) if c is not None]
        data = list(rd)
    except csv.Error as e:
        raise ValueError(f"อ่านไฟล์ไม่ได้: รูปแบบ CSV ผิด ({e})") from None
    if not cols or not any(c.strip() for c in cols):
        raise ValueError("อ่านไฟล์ไม่ได้: ไม่พบแถวหัวตาราง (ชื่อ column)")
    if len(set(cols)) != len(cols):
        raise ValueError(f"อ่านไฟล์ไม่ได้: ชื่อ column ซ้ำกัน {sorted({c for c in cols if cols.count(c) > 1})}")
    guessed = guess_mapping(cols)
    if mapping:
        bad = [v for v in mapping.values() if v and v not in cols]
        if bad:
            raise ValueError(f"mapping อ้างถึง column ที่ไม่มีในไฟล์: {bad}")
        mapping = {f: (mapping.get(f) or None) for f in FIELD_KEYWORDS}
    else:
        mapping = guessed
    problems = []
    if not mapping["headline"] and not mapping["body"]:
        problems.append("ไม่พบ column หัวข่าว/เนื้อข่าว (เช่น headline, title, short_news, ข่าวแบบย่อ) — เลือก mapping เองด้านบน")
    if not mapping["date"]:
        problems.append("ไม่พบ column วันที่ (เช่น date, publish_date, วันที่) — เลือก mapping เองด้านบน")
    if not mapping["ticker"]:
        problems.append("ไม่พบ column ticker — จะตรวจจับชื่อหุ้นจากข้อความแทน (ตรวจผลก่อนบันทึก)")
    used = {v for v in mapping.values() if v}
    extra_cols = [c for c in cols if c not in used]
    scale = label_scale(mapping["sentiment"], [r.get(mapping["sentiment"]) for r in data]) if mapping["sentiment"] else None
    man = prices.manifest()["tickers"]
    ensure_hashes()
    by_hash, by_td = hash_index()
    seen = {}
    get = lambda r, f: (r.get(mapping[f]) or "") if mapping[f] else ""  # noqa: E731
    rows = []
    for i, r in enumerate(data[:limit]):
        skip = []
        headline = get(r, "headline").strip()
        body = get(r, "body")
        if not headline and body.strip():
            headline = re.split(r"(?<=[.!?])\s", body.strip(), maxsplit=1)[0][:300]  # ไม่มีหัวข่าว → ประโยคแรกของเนื้อข่าว
        if not headline:
            skip.append("ไม่มีหัวข่าว")
        date_raw = get(r, "date").strip()
        dinfo = None
        if date_raw:
            try:
                dinfo = trading_day_info(str(pd.Timestamp(date_raw).date()))
            except (ValueError, TypeError, OverflowError):
                skip.append(f"วันที่อ่านไม่ได้: '{date_raw[:30]}'")
        else:
            skip.append("ไม่มีวันที่")
        extra = {c: r.get(c) for c in extra_cols if (r.get(c) or "").strip()}
        has_col_ticker = bool(mapping["ticker"] and get(r, "ticker").strip())
        det = ({"mentions": [], "macro": macro_info(headline + " " + body)} if has_col_ticker  # มี ticker แล้ว → ไม่ต้องไล่ alias ทั้งตาราง
               else detect(" ".join([headline, body] + [v for c, v in extra.items() if any(h in c.lower() for h in NAME_HINT)])))
        warn = []
        if mapping["ticker"] and get(r, "ticker").strip():
            tick, bad = _parse_tickers(get(r, "ticker"), man)
            src = "column"
            if bad:
                (skip if not tick else warn).append(f"ไม่พบ ticker ในระบบ: {bad}")
        else:
            tick, src = [m["ticker"] for m in det["mentions"]], "detected"
        if not tick and not det["macro"]["suggest"] and not any("ticker" in x for x in skip):
            skip.append("ไม่มี ticker และไม่พบคำที่บ่งว่าเป็นข่าวมหภาค")
        label, raw, lerr = parse_label(get(r, "sentiment"), scale) if mapping["sentiment"] else (0, None, None)
        if lerr:
            skip.append(lerr)
        if len(body) > BODY_MAX:
            warn.append(f"เนื้อข่าวยาว {len(body):,} ตัวอักษร เกิน {BODY_MAX:,} — จะถูกตัด")
        dup = {"status": "invalid"}
        if not skip and dinfo:
            dup = dup_check(tick, dinfo["date"], headline, by_hash, by_td)
            if dup["status"] == "new":
                key = tuple(dup["hashes"])
                if key in seen:  # แถวซ้ำกันเองภายในไฟล์เดียวกัน
                    dup = {"status": "exact", "hashes": dup["hashes"], "ids": [], "in_file": seen[key]}
                else:
                    seen[key] = i + 1
        rows.append({"row": i + 1, "headline": headline, "body": body, "dup": dup,
                     "dup_action": "skip" if dup["status"] == "exact" else None,
                     "date": dinfo["date"] if dinfo else date_raw, "effective_date": dinfo["next_trading_day"] if dinfo else None,
                     "date_ok": bool(dinfo), "tickers": tick, "ticker_source": src,
                     "label": label if label is not None else 0, "label_raw": raw,
                     "label_scale": f"±{scale:g}" if scale and isinstance(raw, (int, float)) else None,
                     "macro": det["macro"], "extra": extra, "warnings": warn, "skip_reasons": skip,
                     "include": not skip and dup["status"] == "new"})  # exact = ข้ามอัตโนมัติ, review = รอผู้ใช้เลือก
    n = {k: sum(1 for r in rows if r["dup"]["status"] == k) for k in ("new", "exact", "review")}
    return {"mapping": mapping, "guessed": guessed, "dup_summary": {**n, "invalid": sum(1 for r in rows if r["skip_reasons"])}, "columns": cols, "extra_columns": extra_cols, "fields": [[f, FIELD_TH[f]] for f in FIELD_KEYWORDS],
            "label_scale": scale, "problems": problems, "rows": rows, "total_rows": len(data),
            "truncated": len(data) > limit, "n_include": sum(r["include"] for r in rows)}
