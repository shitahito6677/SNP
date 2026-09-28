"""
ดึง/อัปเดตราคารายวัน (OHLCV + Adj Close) ของ universe sandbox v2 ด้วย yfinance

    python3 -m sandbox.v2.scripts.update_prices                  # อัปเดตเฉพาะ ticker ที่ยังไม่มี/ยังไม่ถึงวันล่าสุด
    python3 -m sandbox.v2.scripts.update_prices --retry-missing  # ลองตัวที่เคยหาไม่เจออีกรอบ
    python3 -m sandbox.v2.scripts.update_prices --refresh-universe  # ดึงรายชื่อ S&P 500 จาก Wikipedia ใหม่
    python3 -m sandbox.v2.scripts.update_prices --backfill-only  # PRICE_START เลื่อนเร็วขึ้น → เติมเฉพาะช่วงต้นที่ยังไม่มี
                                                                 # (แถวเดิมไม่เปลี่ยนแม้แต่ไบต์เดียว, universe เดิม)

Universe = S&P 500 ปัจจุบัน (snapshot Wikipedia เก็บใน data/sp500_snapshot.csv พร้อม GICS sector)
         ∪ ทุก ticker ที่ปรากฏใน export ของ Model A ในรอบที่ยังมีผลต่อช่วงราคา (R ≥ PRICE_START − 400 วัน)
         ∪ SPY + 11 sector ETF + ^IRX

Incremental: ticker ที่ `checked_through` ≥ วันทำการล่าสุด และเริ่ม ≤ PRICE_START แล้ว = ข้าม (ไม่ดึงซ้ำ)
ตัวที่ต้องอัปเดตจะดึงใหม่ทั้งช่วง (ไม่ต่อท้าย) เพราะ Adj Close ของ Yahoo ถูกปรับย้อนหลังทุกครั้งที่มีปันผล —
ต่อท้ายข้อมูลคนละ basis จะทำให้ผลตอบแทนตรงรอยต่อผิด (จำนวน request เท่ากันอยู่แล้ว: yfinance 1 request/batch)
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import io
import json
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg

SNAPSHOT = cfg.DATA / "sp500_snapshot.csv"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UA = "SNP-research-sandbox-v2/1.0 (local research tool)"
BATCH = 40
SLEEP_SEC = 3.0
COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def to_yahoo(sym: str) -> str:
    return sym.strip().upper().replace(".", "-")


def fetch_snapshot() -> pd.DataFrame:
    import requests

    r = requests.get(WIKI_URL, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    t = pd.read_html(io.StringIO(r.text))[0]
    out = pd.DataFrame({
        "symbol": t["Symbol"].astype(str),
        "yahoo": t["Symbol"].astype(str).map(to_yahoo),
        "name": t["Security"].astype(str),
        "gics_sector": t["GICS Sector"].astype(str),
        "gics_sub_industry": t["GICS Sub-Industry"].astype(str),
        "cik": t["CIK"],
    })
    out["snapshot_date"] = datetime.now(timezone.utc).date().isoformat()
    out.to_csv(SNAPSHOT, index=False)
    print(f"Wikipedia snapshot: {len(out)} ตัว → {SNAPSHOT.relative_to(cfg.REPO)}")
    return out


def model_a_tickers(min_R: pd.Timestamp) -> set:
    """ticker (yahoo) ทุกตัวที่อยู่ใน export ของ Model A ในรอบ R ≥ min_R (ทั้งไฟล์แบนเดิมและโฟลเดอร์ version)"""
    root = cfg.MODEL_EXPORT_ROOTS["A"]
    found = set()
    for p in glob.glob(str(root / "scores_rule*.csv")):
        s = pd.read_csv(p, usecols=["R", "yahoo"], parse_dates=["R"])
        found |= set(s.loc[s["R"] >= min_R, "yahoo"].dropna().astype(str))
    for p in glob.glob(str(root / "*" / "signals.parquet")):
        s = pd.read_parquet(p, columns=["date", "ticker"])
        found |= set(s.loc[pd.to_datetime(s["date"]) >= min_R, "ticker"].dropna().astype(str))
    # "?XYZ" = สมาชิกที่ Model A หา ticker Yahoo ไม่เจอ (applicable=False) — ไม่มีราคาให้ดึงอยู่แล้ว
    return {to_yahoo(t) for t in found if not t.startswith("?")}


def build_universe(refresh: bool) -> dict:
    snap = fetch_snapshot() if (refresh or not SNAPSHOT.exists()) else pd.read_csv(SNAPSHOT)
    uni = {}
    for r in snap.itertuples():
        uni[r.yahoo] = {"name": r.name, "sector": r.gics_sector, "sub_industry": r.gics_sub_industry,
                        "sources": ["sp500_current"], "kind": "stock"}
    min_R = pd.Timestamp(cfg.PRICE_START) - pd.Timedelta(days=400)
    for t in sorted(model_a_tickers(min_R)):
        if t in uni:
            uni[t]["sources"].append("model_A_export")
        else:
            uni[t] = {"name": None, "sector": "Unknown", "sub_industry": None, "sources": ["model_A_export"], "kind": "stock"}
    etf_sector = {v: k for k, v in cfg.SECTOR_ETFS.items()}
    for t in cfg.EXTRA_SYMBOLS:
        uni[t] = {"name": t, "sector": etf_sector.get(t, "Benchmark" if t == cfg.BENCHMARK else "Rate"),
                  "sub_industry": None, "sources": ["extra"], "kind": "etf" if t != cfg.RISK_FREE else "rate"}
    return uni


def latest_trading_day() -> pd.Timestamp:
    import yfinance as yf

    h = yf.Ticker(cfg.BENCHMARK).history(period="10d", auto_adjust=False)
    return pd.Timestamp(h.index.max().date())


def download(tickers: list, start: str, end: str | None = None) -> dict:
    import yfinance as yf

    out = {}
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        print(f"  batch {i // BATCH + 1}/{(len(tickers) - 1) // BATCH + 1}: {len(batch)} ticker", flush=True)
        df = yf.download(batch, start=start, end=end, auto_adjust=False, actions=False, progress=False,
                         group_by="ticker", threads=False)
        for t in batch:
            try:
                d = df[t] if isinstance(df.columns, pd.MultiIndex) else df
            except KeyError:
                out[t] = None
                continue
            d = d[[c for c in COLS if c in d.columns]].dropna(how="all")
            d = d[d["Close"].notna()] if "Close" in d else d.iloc[0:0]
            out[t] = d if len(d) else None
        if i + BATCH < len(tickers):
            time.sleep(SLEEP_SEC)
    return out


def frame_hash(d: pd.DataFrame) -> str:
    x = d[["Close", "Adj Close"]].round(6)
    b = x.index.strftime("%Y-%m-%d").str.cat(sep="|").encode() + np.ascontiguousarray(x.to_numpy(np.float64)).tobytes()
    return hashlib.sha256(b).hexdigest()


def backfill(old: dict) -> dict:
    """เติมราคาช่วง [PRICE_START, วันแรกที่มี) ให้ ticker เดิม — ไม่แตะแถวที่มีอยู่แล้ว (ผลการทดลองเก่ารันซ้ำได้ค่าเดิม)

    รอยต่อ: ดึงเกินวันแรกเดิมไป ~2 สัปดาห์เพื่อเทียบช่วงทับกัน
    - Close ดิบ (ปรับ split แล้ว) ต้องตรงกัน — ไม่ตรง = มี split/แก้ข้อมูลระหว่างสองครั้งที่ดึง → ไม่เติม (บันทึกเหตุผล)
    - Adj Close ของ Yahoo ปรับย้อนหลังทุกครั้งที่มีปันผลใหม่ → คูณช่วงที่เติมด้วยอัตราส่วน (เดิม/ใหม่) ในช่วงทับ ให้ basis เดียวกับข้อมูลเดิม"""
    start = pd.Timestamp(cfg.PRICE_START)
    tickers = {t: dict(r) for t, r in old["tickers"].items()}
    todo, first = [], {}
    for t, r in tickers.items():
        f = cfg.PRICES_DIR / f"{t}.parquet"
        if r.get("status") == "missing" or not f.exists() or r.get("requested_start", "9") <= cfg.PRICE_START:
            continue
        first[t] = pd.read_parquet(f).index.min()
        todo.append(t)
    print(f"backfill: {len(todo)} ticker · ช่วง {start.date()} → วันแรกเดิม (ส่วนใหญ่ {pd.Series(first).mode().iloc[0].date() if first else '-'})", flush=True)
    end = str((max(first.values()) + pd.Timedelta(days=15)).date()) if first else None
    got = download(todo, cfg.PRICE_START, end) if todo else {}
    added, notes = 0, {}
    for t in todo:
        f = cfg.PRICES_DIR / f"{t}.parquet"
        cur = pd.read_parquet(f)
        new = got.get(t)
        rec = tickers[t]
        if new is None or not len(new):
            rec["requested_start"] = cfg.PRICE_START  # Yahoo ไม่มีข้อมูลก่อนหน้า (IPO ทีหลัง) — ของเดิมคือทั้งหมดที่มี
            continue
        new = new[~new.index.duplicated(keep="last")].sort_index()
        new.index = pd.DatetimeIndex(new.index.date, name=cur.index.name or "date")
        ov = cur.index.intersection(new.index)
        pre = new[new.index < cur.index.min()]
        if not len(pre):
            rec["requested_start"] = cfg.PRICE_START
            continue
        if len(ov) < 3:
            notes[t] = f"ช่วงทับกับข้อมูลเดิมมีแค่ {len(ov)} วัน — ไม่เติม (ตรวจรอยต่อไม่ได้)"
            continue
        dc = (new.loc[ov, "Close"] / cur.loc[ov, "Close"] - 1).abs().max()
        if not np.isfinite(dc) or dc > 1e-4:
            notes[t] = f"Close ช่วงทับไม่ตรงกับข้อมูลเดิม (ต่างสูงสุด {dc:.2%}) — อาจมี split ระหว่างสองครั้งที่ดึง → ไม่เติม"
            continue
        ratio = (cur.loc[ov, "Adj Close"] / new.loc[ov, "Adj Close"]).median()
        pre = pre.copy()
        if abs(ratio - 1) > 1e-9:
            pre["Adj Close"] = pre["Adj Close"] * ratio
            notes[t] = f"Adj Close ช่วงที่เติม × {ratio:.8f} ให้ basis ตรงกับข้อมูลเดิม (Yahoo ปรับปันผลย้อนหลังระหว่างสองครั้งที่ดึง)"
        pre = pre[cur.columns]
        for c in cur.columns:  # คง dtype เดิม (เช่น Volume int64) ถ้าช่วงที่เติมไม่มีค่าว่าง
            if pre[c].dtype != cur[c].dtype and pre[c].notna().all():
                pre[c] = pre[c].astype(cur[c].dtype)
        both = pd.concat([pre, cur])
        old_vals, new_vals = cur.to_numpy(np.float64), both.loc[cur.index].to_numpy(np.float64)
        assert np.array_equal(old_vals, new_vals, equal_nan=True), t  # แถวเดิมต้องเหมือนเดิมทุกค่า
        both.to_parquet(f)
        rec.update(requested_start=cfg.PRICE_START, start=str(both.index.min().date()), rows=int(len(both)), hash=frame_hash(both))
        added += len(pre)
    print(f"backfill: เติม {added:,} แถว · หมายเหตุ {len(notes)} ticker", flush=True)
    return tickers, notes


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--retry-missing", action="store_true")
    ap.add_argument("--refresh-universe", action="store_true")
    ap.add_argument("--backfill-only", action="store_true", help="เติมเฉพาะช่วงต้น (PRICE_START เร็วขึ้น) ไม่แตะแถวเดิม/universe")
    args = ap.parse_args(argv)
    if args.backfill_only:
        return main_backfill()

    cfg.PRICES_DIR.mkdir(parents=True, exist_ok=True)
    old = json.loads(cfg.UNIVERSE_MANIFEST.read_text()) if cfg.UNIVERSE_MANIFEST.exists() else {"tickers": {}}
    old_t = old.get("tickers", {})
    uni = build_universe(args.refresh_universe)
    last_day = latest_trading_day()
    start = pd.Timestamp(cfg.PRICE_START)
    print(f"universe {len(uni)} ตัว | PRICE_START {start.date()} | วันทำการล่าสุด {last_day.date()}")

    todo = []
    for t in sorted(uni):
        o = old_t.get(t)
        f = cfg.PRICES_DIR / f"{t}.parquet"
        if o and o.get("status") == "missing" and not args.retry_missing and o.get("requested_start", "9") <= cfg.PRICE_START:
            continue
        if o and f.exists() and o.get("checked_through", "") >= str(last_day.date()) and o.get("requested_start", "9") <= cfg.PRICE_START:
            continue
        todo.append(t)
    print(f"ต้องดึง {len(todo)} ตัว (ข้าม {len(uni) - len(todo)} ตัวที่เป็นปัจจุบันแล้ว)")

    got = download(todo, cfg.PRICE_START) if todo else {}
    tickers = {}
    for t, meta in uni.items():
        rec = dict(old_t.get(t, {}))
        rec.update({k: meta[k] for k in ("name", "sector", "sub_industry", "sources", "kind")})
        if t in got:
            d = got[t]
            if d is None and (cfg.PRICES_DIR / f"{t}.parquet").exists():
                # ดึงไม่สำเร็จรอบนี้แต่มีข้อมูลเดิม → เก็บของเดิมไว้ ไม่ลบ (อาจเป็น error ชั่วคราวของ Yahoo)
                rec["last_fetch_error"] = f"{last_day.date()}: yfinance ไม่คืนข้อมูลรอบนี้ — ใช้ข้อมูลเดิม"
                tickers[t] = rec
                continue
            rec["requested_start"] = cfg.PRICE_START
            rec["checked_through"] = str(last_day.date())
            if d is None:
                rec.update(status="missing", start=None, end=None, rows=0, hash=None,
                           reason="yfinance ไม่คืนข้อมูล (น่าจะ delist/เปลี่ยน ticker) — ตัดทิ้งตามที่ผู้ใช้อนุญาต")
                (cfg.PRICES_DIR / f"{t}.parquet").unlink(missing_ok=True)
            else:
                d = d[~d.index.duplicated(keep="last")].sort_index()
                d.index = pd.DatetimeIndex(d.index.date, name="date")
                d.to_parquet(cfg.PRICES_DIR / f"{t}.parquet")
                rec.update(start=str(d.index.min().date()), end=str(d.index.max().date()), rows=int(len(d)),
                           hash=frame_hash(d), reason=None)
        if rec.get("status") != "missing" and rec.get("start"):
            full = rec["start"] <= str((start + pd.Timedelta(days=7)).date()) and rec["end"] >= str((last_day - pd.Timedelta(days=7)).date())
            rec["status"] = "ok" if full else "partial"
            if not full:
                why = []
                if rec["start"] > str((start + pd.Timedelta(days=7)).date()):
                    why.append(f"เริ่ม {rec['start']} (เข้า index/IPO หลัง PRICE_START)")
                if rec["end"] < str((last_day - pd.Timedelta(days=7)).date()):
                    why.append(f"จบ {rec['end']} (delist/ถูกซื้อ/เปลี่ยน ticker)")
                rec["reason"] = "; ".join(why)
        tickers[t] = rec

    h = hashlib.sha256("".join(f"{t}:{tickers[t].get('hash')}" for t in sorted(tickers)).encode()).hexdigest()
    counts = pd.Series([r.get("status") for r in tickers.values()]).value_counts().to_dict()
    snap_date = pd.read_csv(SNAPSHOT, usecols=["snapshot_date"]).iloc[0, 0]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "price_start": cfg.PRICE_START,
        "latest_trading_day": str(last_day.date()),
        "sp500_snapshot_date": snap_date,
        "sp500_snapshot_source": WIKI_URL,
        "data_hash": h,
        "counts": counts,
        "fetched_this_run": len(todo),
        "tickers": tickers,
    }
    cfg.UNIVERSE_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=False))
    print(f"สถานะ: {counts} | data_hash {h[:12]}… → {cfg.UNIVERSE_MANIFEST.relative_to(cfg.REPO)}")

    from sandbox.v2.scripts import data_quality
    data_quality.main()
    return manifest


def main_backfill():
    old = json.loads(cfg.UNIVERSE_MANIFEST.read_text())
    tickers, notes = backfill(old)
    start = pd.Timestamp(cfg.PRICE_START)
    last_day = pd.Timestamp(old["latest_trading_day"])
    for t, rec in tickers.items():  # สถานะ ok/partial เทียบกับ PRICE_START ใหม่ (เกณฑ์เดียวกับ main)
        if rec.get("status") == "missing" or not rec.get("start"):
            continue
        full = rec["start"] <= str((start + pd.Timedelta(days=7)).date()) and rec["end"] >= str((last_day - pd.Timedelta(days=7)).date())
        rec["status"] = "ok" if full else "partial"
        why = []
        if rec["start"] > str((start + pd.Timedelta(days=7)).date()):
            why.append(f"เริ่ม {rec['start']} (เข้า index/IPO หลัง PRICE_START)")
        if rec["end"] < str((last_day - pd.Timedelta(days=7)).date()):
            why.append(f"จบ {rec['end']} (delist/ถูกซื้อ/เปลี่ยน ticker)")
        rec["reason"] = "; ".join(why) or None
        if t in notes:
            rec["backfill_note"] = notes[t]
    h = hashlib.sha256("".join(f"{t}:{tickers[t].get('hash')}" for t in sorted(tickers)).encode()).hexdigest()
    counts = pd.Series([r.get("status") for r in tickers.values()]).value_counts().to_dict()
    manifest = dict(old, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), price_start=cfg.PRICE_START,
                    data_hash=h, counts=counts, fetched_this_run=len(tickers), tickers=tickers,
                    backfill={"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "price_start": cfg.PRICE_START,
                              "notes": notes})
    cfg.UNIVERSE_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=False))
    print(f"สถานะ: {counts} | data_hash {h[:12]}…")
    from sandbox.v2.scripts import data_quality
    data_quality.main()
    return manifest


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
