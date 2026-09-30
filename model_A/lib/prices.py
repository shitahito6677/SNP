"""
ราคารายวันจาก yfinance (เก็บทั้ง Close และ Adj Close — Adj Close ปรับ split + dividend แล้ว)

ข้อจำกัดสำคัญ (README ของ fja05680 ยืนยัน): Yahoo เก็บเฉพาะหุ้นที่ยังซื้อขายอยู่ หุ้นที่ถูกซื้อกิจการ/
ล้มละลาย/เปลี่ยน ticker ส่วนใหญ่จะดึงไม่ได้ → เป็นต้นเหตุหลักของ survivorship bias ในโปรเจคนี้
ticker ที่ถูกนำไปใช้ใหม่ (ticker reuse) อาจได้ราคาของ "บริษัทใหม่" ที่ใช้ชื่อเดียวกัน ต้องตรวจช่วงวันที่เสมอ
"""

import time

import pandas as pd
import yfinance as yf

from lib import guard
from lib.paths import PRICES_DIR

CLOSE_FILE = PRICES_DIR / "close.parquet"
ADJ_FILE = PRICES_DIR / "adj_close.parquet"
STATUS_FILE = PRICES_DIR / "download_status.csv"


def download(yahoo_tickers, start="2008-01-01", end=None, batch=50) -> None:
    """ดาวน์โหลดเป็น batch แล้ว cache เป็น wide parquet (index=Date, columns=yahoo ticker)
    ticker ที่ cache แล้วจะข้าม — บันทึกสถานะต่อ ticker (จำนวนวันที่ได้) ใน download_status.csv"""
    close = pd.read_parquet(CLOSE_FILE) if CLOSE_FILE.exists() else pd.DataFrame()
    adj = pd.read_parquet(ADJ_FILE) if ADJ_FILE.exists() else pd.DataFrame()
    status = pd.read_csv(STATUS_FILE) if STATUS_FILE.exists() else pd.DataFrame(columns=["yahoo", "n_days"])
    todo = [t for t in sorted(set(yahoo_tickers)) if t not in set(status["yahoo"])]
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        df = yf.download(chunk, start=start, end=end, auto_adjust=False, actions=False,
                         progress=False, threads=True, group_by="column")
        c = df["Close"].reindex(columns=chunk) if not df.empty else pd.DataFrame(columns=chunk)
        a = df["Adj Close"].reindex(columns=chunk) if not df.empty else pd.DataFrame(columns=chunk)
        close = pd.concat([close, c], axis=1)
        adj = pd.concat([adj, a], axis=1)
        status = pd.concat([status, pd.DataFrame({"yahoo": chunk, "n_days": [int(c[t].notna().sum()) for t in chunk]})])
        close.sort_index().to_parquet(CLOSE_FILE)
        adj.sort_index().to_parquet(ADJ_FILE)
        status.to_csv(STATUS_FILE, index=False)
        print(f"{i + len(chunk)}/{len(todo)} downloaded", flush=True)
        time.sleep(1)


def load_adj_close(end=None) -> pd.DataFrame:
    """ถูกล็อก held-out: คืนข้อมูลถึง guard.CUTOFF เท่านั้น (เว้นแต่ FINAL_EVAL=1)"""
    guard.check_end(end)
    return guard.clip(pd.read_parquet(ADJ_FILE).sort_index()).loc[:end]


def load_close(end=None) -> pd.DataFrame:
    guard.check_end(end)
    return guard.clip(pd.read_parquet(CLOSE_FILE).sort_index()).loc[:end]


def load_status() -> pd.DataFrame:
    return pd.read_csv(STATUS_FILE)


SPLITS_FILE = PRICES_DIR / "splits.parquet"


def download_splits(yahoo_tickers) -> pd.DataFrame:
    """ประวัติ split ต่อ ticker (yahoo, date, ratio) — ใช้แปลงราคา split-adjusted กลับเป็นราคาจริง ณ วันนั้น
    (จำเป็นสำหรับ market cap = ราคาจริง × จำนวนหุ้นจาก SEC ณ วันนั้น)"""
    have = pd.read_parquet(SPLITS_FILE) if SPLITS_FILE.exists() else pd.DataFrame(columns=["yahoo", "date", "ratio"])
    done_file = PRICES_DIR / "splits_done.csv"
    done = set(pd.read_csv(done_file)["yahoo"]) if done_file.exists() else set()
    todo = [t for t in sorted(set(yahoo_tickers)) if t not in done]
    rows = []
    for i, t in enumerate(todo):
        try:
            s = yf.Ticker(t).splits
            for d, r in s.items():
                rows.append({"yahoo": t, "date": pd.Timestamp(d).tz_localize(None).normalize(), "ratio": float(r)})
        except Exception as e:  # noqa: BLE001 — ticker ที่ Yahoo ไม่มี ให้บันทึกว่าลองแล้ว
            print(f"splits {t}: {e}", flush=True)
        done.add(t)
        if (i + 1) % 100 == 0 or i == len(todo) - 1:
            have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
            rows = []
            have.to_parquet(SPLITS_FILE, index=False)
            pd.Series(sorted(done), name="yahoo").to_csv(done_file, index=False)
            print(f"splits {i + 1}/{len(todo)}", flush=True)
    return have


def load_splits() -> pd.DataFrame:
    """รวม cache split เดิม (Ticker.splits) กับ v2 (batch download) — v2 เติม split ที่ Yahoo คืนค่าว่างแบบเงียบในรอบดาวน์โหลดใหญ่
    (ตรวจแล้ว: สำหรับชุดหุ้น S&P 500 เดิม ไม่มี split ใดใน v2 ที่ขาดจาก cache เดิม → ผล v1/round 001–006 ไม่เปลี่ยน)"""
    parts = [pd.read_parquet(f) for f in (SPLITS_FILE, PRICES_DIR / "splits_v2.parquet") if f.exists()]
    if not parts:
        return pd.DataFrame(columns=["yahoo", "date", "ratio"])
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["ratio"] = df["ratio"].astype(float).round(6)
    return df.drop_duplicates(["yahoo", "date", "ratio"]).reset_index(drop=True)


def split_factor_after(splits: pd.DataFrame, yahoo: str, date: pd.Timestamp) -> float:
    """ผลคูณของ split ratio ที่เกิด "หลัง" date — ราคาจริง ณ date = Close(split-adjusted) × factor นี้"""
    s = splits[(splits["yahoo"] == yahoo) & (splits["date"] > date)]
    return float(s["ratio"].prod()) if len(s) else 1.0


INTL_FILE = PRICES_DIR / "intl_index_close.parquet"


def load_intl_index() -> pd.DataFrame:
    """ดัชนีต่างประเทศ (price index, ไม่รวมปันผล) — ถูกล็อก held-out เช่นเดียวกัน"""
    return guard.clip(pd.read_parquet(INTL_FILE).sort_index())


SPLITS2_FILE = PRICES_DIR / "splits_v2.parquet"


def download_splits_v2(yahoo_tickers, batch: int = 50) -> pd.DataFrame:
    """ประวัติ split แบบ batch ผ่าน yf.download(actions=True) — แทน download_splits ที่ Yahoo คืนค่าว่างแบบเงียบ
    (บั๊กที่พบใน round 007: COKE/CHDN/BBSI มี split จริงแต่ cache ว่าง) — บันทึกทุก batch และ ticker ที่ไม่มีข้อมูลราคาเลย"""
    have = pd.read_parquet(SPLITS2_FILE) if SPLITS2_FILE.exists() else pd.DataFrame(columns=["yahoo", "date", "ratio"])
    done_file = PRICES_DIR / "splits_v2_done.csv"
    done = set(pd.read_csv(done_file)["yahoo"]) if done_file.exists() else set()
    todo = [t for t in sorted(set(yahoo_tickers)) if t not in done]
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        d = yf.download(chunk, start="2000-01-01", actions=True, auto_adjust=False, progress=False, threads=True, group_by="column")
        if d.empty or "Stock Splits" not in d:
            print("empty batch", i, flush=True)
            continue
        s = d["Stock Splits"].reindex(columns=chunk)
        got = d["Close"].reindex(columns=chunk).notna().any()
        rows = [{"yahoo": t, "date": pd.Timestamp(dt).tz_localize(None).normalize() if pd.Timestamp(dt).tzinfo else pd.Timestamp(dt).normalize(),
                 "ratio": float(v)} for t in chunk for dt, v in s[t].items() if pd.notna(v) and v not in (0, 1)]
        have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
        done |= set(t for t in chunk if got[t])  # ticker ที่ไม่มีราคาเลย (ดึงไม่ได้) จะถูกลองใหม่รอบหน้า
        have.to_parquet(SPLITS2_FILE, index=False)
        pd.Series(sorted(done), name="yahoo").to_csv(done_file, index=False)
        print(f"splits_v2 {min(i + batch, len(todo))}/{len(todo)}", flush=True)
    return have
