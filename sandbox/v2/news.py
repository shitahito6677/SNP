"""
ข่าว manual ของ sandbox v2 (source="manual") — ไม่ใช่ output ของโมเดล และ**ไม่ปนกับ training data**
(training data ของ Model C อยู่ที่ data/raw/, data/processed/ ที่ root — ไฟล์นี้เขียนแค่ sandbox/v2/data/manual_news.jsonl)

- detect(): หา ticker ที่ถูกพูดถึงในข้อความ (alias dict + ticker รูปแบบ $TSLA / (TSLA)) → เป็น "ข้อเสนอ" ให้ผู้ใช้ยืนยันทีละตัว
- keyword มหภาค (Fed, CPI, tariff …) → แนะนำให้ติดเป็นข่าว C (ผู้ใช้ต้องยืนยัน)
- วันที่ตลาดปิด → เสนอวันทำการถัดไป
"""

from __future__ import annotations

import csv
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
    macro = [k for k, pat in MACRO_KEYWORDS if re.search(pat, text, re.I)]
    sectors = [e for e, pat in SECTOR_KEYWORDS.items() if re.search(pat, text, re.I)]
    return {"mentions": sorted(found.values(), key=lambda x: text.find(x["match"])),
            "macro": {"keywords": macro, "suggest": bool(macro), "sectors": sectors}}


def trading_day_info(date: str) -> dict:
    d = pd.Timestamp(date).normalize()
    cal = pd.read_parquet(cfg.PRICES_DIR / f"{cfg.BENCHMARK}.parquet").index
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


def list_news(limit=300) -> list:
    return [r for r in reversed(_load()) if not r.get("deleted")][:limit]


def add(item: dict) -> dict:
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
    sentiment = item.get("sentiment", "neutral")
    if sentiment not in ("positive", "neutral", "negative"):
        raise ValueError("sentiment ต้องเป็น positive / neutral / negative")
    score = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}[sentiment]
    if isinstance(item.get("score"), (int, float)) and -1 <= item["score"] <= 1 \
            and np.sign(item["score"]) == np.sign(score):  # score ละเอียดจาก CSV (เช่น -1 บนสเกล ±2 → -0.5) ต้องทิศเดียวกับ sentiment
        score = float(item["score"])
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
           "sentiment": sentiment, "score": score,
           "detected_by": item.get("detected_by") or {}, "deleted": False}
    if item.get("label_raw") is not None:  # ค่า label ดิบจาก CSV (เช่น -2..+2) — เก็บไว้ไม่ทิ้ง
        row["label_raw"] = item["label_raw"]
        row["label_scale"] = item.get("label_scale")
    if item.get("extra"):  # column ที่ระบบไม่รู้จัก (source_url, label_reason, …) → metadata ต่อแถว
        row["extra"] = {str(k)[:100]: str(v)[:BODY_MAX] for k, v in dict(item["extra"]).items()}
    rows = _load()
    rows.append(row)
    _write(rows)
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
    """label → (sentiment, score ∈ [-1, 1], ค่าดิบ, error)
    ตัวเลข: >0 positive, <0 negative, 0 neutral; score = ค่า/สเกล (เช่น -2 บนสเกล ±2 → -1.0 = แย่สุดของระบบ)
    ข้อความ: positive/negative/neutral (+ คำพ้อง) → score ±1/0 เหมือนข่าวที่พิมพ์เอง"""
    s = ("" if v is None else str(v)).strip()
    if not s:
        return "neutral", 0.0, None, None
    try:
        x = float(s.replace("+", ""))
    except ValueError:
        k = s.lower()
        lab = TEXT_LABELS.get(k) or TEXT_LABELS.get(k[:3])
        if lab is None:
            return None, None, s, f"label อ่านไม่ได้: '{s[:30]}' (รองรับตัวเลข หรือ positive/neutral/negative)"
        return lab, {"positive": 1.0, "neutral": 0.0, "negative": -1.0}[lab], s, None
    if not np.isfinite(x) or not scale or abs(x) > scale:
        return None, None, s, f"label {s} อยู่นอกสเกล ±{scale:g}" if scale else f"label {s} อ่านไม่ได้"
    raw = int(x) if float(x).is_integer() else x
    return ("positive" if x > 0 else "negative" if x < 0 else "neutral"), x / scale, raw, None


def _parse_tickers(raw: str, man) -> tuple:
    out, bad = [], []
    for t in re.split(r"[,;| ]+", raw or ""):
        t = t.strip().lstrip("$@").upper().replace(".", "-")
        if not t:
            continue
        (out if t in man and man[t].get("kind") == "stock" else bad).append(t)
    return sorted(set(out)), bad


def csv_preview(text: str, mapping: dict | None = None, limit=2000) -> dict:
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
        det = detect(" ".join([headline, body] + [v for c, v in extra.items() if any(h in c.lower() for h in NAME_HINT)]))
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
        sent, score, raw, lerr = parse_label(get(r, "sentiment"), scale) if mapping["sentiment"] else ("neutral", 0.0, None, None)
        if lerr:
            skip.append(lerr)
        if len(body) > BODY_MAX:
            warn.append(f"เนื้อข่าวยาว {len(body):,} ตัวอักษร เกิน {BODY_MAX:,} — จะถูกตัด")
        rows.append({"row": i + 1, "headline": headline, "body": body,
                     "date": dinfo["date"] if dinfo else date_raw, "effective_date": dinfo["next_trading_day"] if dinfo else None,
                     "date_ok": bool(dinfo), "tickers": tick, "ticker_source": src,
                     "sentiment": sent or "neutral", "score": score, "label_raw": raw,
                     "label_scale": f"±{scale:g}" if scale and isinstance(raw, (int, float)) else None,
                     "macro": det["macro"], "extra": extra, "warnings": warn, "skip_reasons": skip, "include": not skip})
    return {"mapping": mapping, "guessed": guessed, "columns": cols, "extra_columns": extra_cols, "fields": [[f, FIELD_TH[f]] for f in FIELD_KEYWORDS],
            "label_scale": scale, "problems": problems, "rows": rows, "total_rows": len(data),
            "truncated": len(data) > limit, "n_include": sum(r["include"] for r in rows)}
