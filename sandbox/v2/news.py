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
    date = str(pd.Timestamp(item["date"]).date())
    info = trading_day_info(date)
    eff = item.get("effective_date") or info["next_trading_day"]
    row = {"id": str(uuid.uuid4()), "created_at": _now(), "source": "manual", "headline": headline[:500],
           "body": (item.get("body") or "")[:4000], "date": date, "effective_date": str(pd.Timestamp(eff).date()),
           "kind": "company" if tickers else "macro", "tickers": tickers, "sectors": sectors,
           "sentiment": sentiment, "score": {"positive": 1.0, "neutral": 0.0, "negative": -1.0}[sentiment],
           "detected_by": item.get("detected_by") or {}, "deleted": False}
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
COLMAP = {
    "date": ["date", "published", "published_at", "datetime", "time", "วันที่"],
    "headline": ["headline", "title", "หัวข้อ", "ข่าว", "text"],
    "body": ["body", "summary", "content", "description", "เนื้อหา"],
    "ticker": ["ticker", "tickers", "symbol", "symbols", "หุ้น"],
    "sentiment": ["sentiment", "label", "polarity"],
}


def csv_preview(text: str, limit=500) -> dict:
    rd = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    cols = rd.fieldnames or []
    low = {c.lower().strip(): c for c in cols}
    mapping = {k: next((low[a] for a in al if a in low), None) for k, al in COLMAP.items()}
    if not mapping["headline"]:
        raise ValueError(f"หา column headline ไม่เจอ (มี: {cols})")
    rows = []
    for i, r in enumerate(rd):
        if i >= limit:
            break
        h = (r.get(mapping["headline"]) or "").strip()
        det = detect(h + " " + (r.get(mapping["body"]) or "" if mapping["body"] else ""))
        if mapping["ticker"] and r.get(mapping["ticker"]):
            tick = [t.strip().upper().replace(".", "-") for t in re.split(r"[,;| ]+", r[mapping["ticker"]]) if t.strip()]
            src = "column"
        else:
            tick = [m["ticker"] for m in det["mentions"]]
            src = "detected"
        date = (r.get(mapping["date"]) or "").strip() if mapping["date"] else ""
        try:
            dinfo = trading_day_info(str(pd.Timestamp(date).date())) if date else None
        except (ValueError, TypeError):
            dinfo = None
        s = (r.get(mapping["sentiment"]) or "neutral").strip().lower() if mapping["sentiment"] else "neutral"
        s = {"pos": "positive", "neg": "negative", "neu": "neutral"}.get(s[:3], s) if s else "neutral"
        rows.append({"row": i + 1, "headline": h, "body": (r.get(mapping["body"]) or "") if mapping["body"] else "",
                     "date": dinfo["date"] if dinfo else date, "effective_date": dinfo["next_trading_day"] if dinfo else None,
                     "date_ok": bool(dinfo), "tickers": tick, "ticker_source": src,
                     "sentiment": s if s in ("positive", "neutral", "negative") else "neutral",
                     "macro": det["macro"], "include": bool(h and dinfo and (tick or det["macro"]["suggest"]))})
    return {"mapping": mapping, "columns": cols, "rows": rows}
