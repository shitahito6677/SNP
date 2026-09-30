"""
EXPLORE2 T4 — Lazy Prices: ดาวน์โหลด 10-K (เอกสารหลัก) ของบริษัท S&P 500 แล้วเก็บความถี่คำ (ไม่เก็บ HTML) — ไม่ใช้ LLM
รัน: python3 -m lib.lazyprices   (จาก model_A) — log ความคืบหน้า; cache ต่อ filing ที่ data/raw/sec/lazy/<cik>_<accn>.pkl
"""
import gzip
import html
import json
import pickle
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from lib import guard
from lib.paths import INTERIM, SEC_DIR, SEC_USER_AGENT

DIR = SEC_DIR / "lazy"
SUBS = SEC_DIR / "submissions"
FORMS = {"10-K", "10-K405", "10-KT"}
TOK = re.compile(r"[a-z]{2,}")
START = re.compile(r"item\s*1a\.?\s*[\-–—:]?\s*risk\s+factors", re.I)
END = re.compile(r"item\s*1b\.?|item\s*2\.?\s*[\-–—:]?\s*properties", re.I)
_lock = threading.Lock()
_last = [0.0]


def _get(url):
    """≤ 8 คำขอ/วินาทีรวมทุก thread"""
    for attempt in range(4):
        with _lock:
            wait = _last[0] + 0.125 - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        r = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=120)
        if r.status_code == 200:
            return r
        if r.status_code == 404:
            return None
        time.sleep(2 * (attempt + 1))
    return None


def filings_for(cik: int) -> pd.DataFrame:
    SUBS.mkdir(parents=True, exist_ok=True)
    p = SUBS / f"CIK{cik:010d}.json"
    if not p.exists():
        r = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if r is None:
            return pd.DataFrame()
        p.write_bytes(r.content)
    d = json.loads(p.read_text())
    parts = [pd.DataFrame(d["filings"]["recent"])]
    for f in d["filings"].get("files", []):
        q = SUBS / f["name"]
        if not q.exists():
            r = _get(f"https://data.sec.gov/submissions/{f['name']}")
            if r is None:
                continue
            q.write_bytes(r.content)
        parts.append(pd.DataFrame(json.loads(q.read_text())))
    df = pd.concat(parts, ignore_index=True)
    df = df[df["form"].isin(FORMS)].copy()
    df["filingDate"] = pd.to_datetime(df["filingDate"])
    df = df[(df["filingDate"] >= "2010-01-01") & (df["filingDate"] <= guard.CUTOFF)]
    df["cik"] = cik
    return df[["cik", "accessionNumber", "filingDate", "reportDate", "form", "primaryDocument"]]


def text_of(raw: bytes) -> str:
    s = raw.decode("utf-8", errors="ignore")
    s = re.sub(r"(?is)<(script|style|ix:header).*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s))


def item1a(text: str) -> str:
    best = ""
    for m in START.finditer(text):
        e = END.search(text, m.end())
        seg = text[m.end(): e.start()] if e else ""
        if len(seg) > len(best):
            best = seg
    return best if len(best) >= 1000 else ""


def process(row) -> dict:
    DIR.mkdir(parents=True, exist_ok=True)
    out = DIR / f"{row.cik}_{row.accessionNumber}.pkl"
    if out.exists():
        return pickle.loads(out.read_bytes())
    url = f"https://www.sec.gov/Archives/edgar/data/{row.cik}/{row.accessionNumber.replace('-', '')}/{row.primaryDocument}"
    r = _get(url)
    if r is None:
        rec = {"ok": False}
    else:
        t = text_of(r.content)
        a = item1a(t)
        rec = {"ok": True, "full": Counter(TOK.findall(t.lower())), "i1a": Counter(TOK.findall(a.lower())) if a else None,
               "n_chars": len(t), "n_1a": len(a)}
    out.write_bytes(pickle.dumps(rec))
    return rec


def main(deadline: float):
    segs = pd.read_parquet(INTERIM / "cik_segments.parquet")
    ciks = sorted(segs["cik"].dropna().astype(int).unique())
    fl = []
    for i, c in enumerate(ciks):
        fl.append(filings_for(c))
        if (i + 1) % 100 == 0:
            print(f"submissions {i + 1}/{len(ciks)}", flush=True)
    fl = pd.concat(fl, ignore_index=True)
    fl.to_parquet(INTERIM / "lazy_filings.parquet", index=False)
    print("10-K filings to fetch:", len(fl), flush=True)
    done = [0]

    def one(row):
        if time.time() > deadline:
            return None
        rec = process(row)
        done[0] += 1
        if done[0] % 250 == 0:
            print(f"docs {done[0]}/{len(fl)}", flush=True)
        return rec

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(one, fl.itertuples(index=False)))
    n_ok = sum(1 for p in DIR.glob("*.pkl"))
    print("DONE docs cached", n_ok, "of", len(fl), "deadline hit" if time.time() > deadline else "", flush=True)


if __name__ == "__main__":
    import sys
    main(float(sys.argv[1]) if len(sys.argv) > 1 else time.time() + 7200)
