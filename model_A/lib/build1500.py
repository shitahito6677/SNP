"""
สร้างข้อมูลสำหรับ universe top-1500 (round 007) — idempotent, cache ทุกขั้น
รัน: python3 -m lib.build1500   (จาก model_A) — log ความคืบหน้าทุก 250 บริษัท
"""

import time

import pandas as pd
import requests
import yfinance as yf

from lib import audit, cik_map, sec_facts, sec_rss, universe1500 as u15
from lib.build_data import fetch_companyfacts
from lib.paths import INTERIM, PRICES_DIR

P_CLOSE, P_ADJ, P_VOL, P_STATUS = (PRICES_DIR / f"u1500_{k}.parquet" for k in ("close", "adj", "vol", "status"))


def fetch_parallel(ciks, workers: int = 4):
    """ดาวน์โหลด companyfacts แบบขนาน — แต่ละ worker พัก 0.5 วินาที/คำขอ → รวม ≤ 8 คำขอ/วินาที (< 10 ตาม SEC fair access)"""
    from concurrent.futures import ThreadPoolExecutor
    from lib.paths import COMPANYFACTS_DIR, SEC_USER_AGENT
    todo = [c for c in ciks if not (COMPANYFACTS_DIR / f"CIK{c:010d}.json.gz").exists()]
    done = [0]

    def one(c):
        s = requests.Session()
        s.headers["User-Agent"] = SEC_USER_AGENT
        ok = sec_facts.fetch(c, s)
        time.sleep(0.5)
        done[0] += 1
        if done[0] % 250 == 0:
            print(f"fetched {done[0]}/{len(todo)}", flush=True)
        return c, ok

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, todo))
    return [c for c, ok in res if not ok]


def facts():
    pl = INTERIM / "annual_long_1500.parquet"
    if pl.exists():
        return pd.read_parquet(pl)
    pool = u15.pool()
    ciks = sorted(pool["cik"].astype(int))
    fetch_parallel(ciks)
    missing = fetch_companyfacts(ciks)  # ตรวจซ้ำ (cache) + บันทึก 404
    pd.Series(missing, name="cik").to_csv(INTERIM / "companyfacts_404_1500.csv", index=False)
    parts = []
    for i, c in enumerate(ciks):
        if c in missing:
            continue
        parts.append(sec_facts.first_filed_annual(c))
        if (i + 1) % 250 == 0:
            print(f"facts {i + 1}/{len(ciks)}", flush=True)
    long = pd.concat(parts, ignore_index=True)
    long.to_parquet(pl, index=False)
    return long


def tickers():
    p = INTERIM / "tickers1500.parquet"
    if p.exists():
        return pd.read_parquet(p)
    cur = cik_map.load_current_map()
    inv = {}
    for tk, c in cur.items():
        inv.setdefault(c, []).append(tk)
    ct = {c: audit.common_ticker(v) for c, v in inv.items()}
    t = u15.tickers_for(sorted(u15.pool()["cik"].astype(int)), sec_rss.load_all(), ct)
    t.to_parquet(p, index=False)
    return t


def prices(batch: int = 60):
    t = tickers()
    names = set()
    for c in ("ticker_current", "ticker_prefix"):
        names |= {x.replace(".", "-") for x in t[c].dropna()}
    names |= {"SPY", "^IRX"}
    status = pd.read_parquet(P_STATUS) if P_STATUS.exists() else pd.DataFrame(columns=["yahoo", "n_days"])
    todo = sorted(names - set(status["yahoo"]))
    frames = {k: (pd.read_parquet(p) if p.exists() else pd.DataFrame()) for k, p in (("close", P_CLOSE), ("adj", P_ADJ), ("vol", P_VOL))}
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        try:
            d = yf.download(chunk, start="2008-01-01", auto_adjust=False, actions=False, progress=False, threads=True,
                            group_by="column")
        except Exception as e:  # noqa: BLE001
            print("batch error", e, flush=True)
            continue
        for k, col in (("close", "Close"), ("adj", "Adj Close"), ("vol", "Volume")):
            x = d[col].reindex(columns=chunk) if not d.empty else pd.DataFrame(columns=chunk)
            frames[k] = pd.concat([frames[k], x], axis=1)
        status = pd.concat([status, pd.DataFrame({"yahoo": chunk, "n_days": [int(frames["close"][c].notna().sum()) for c in chunk]})])
        for k, p in (("close", P_CLOSE), ("adj", P_ADJ), ("vol", P_VOL)):
            frames[k].sort_index().to_parquet(p)
        status.to_parquet(P_STATUS)
        print(f"prices {min(i + batch, len(todo))}/{len(todo)}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    t0 = time.time()
    long = facts()
    print("facts rows", len(long), "ciks", long["cik"].nunique(), round(time.time() - t0), flush=True)
    t = tickers()
    print("tickers: current", t["ticker_current"].notna().sum(), "prefix-only", (t["ticker_current"].isna() & t["ticker_prefix"].notna()).sum(),
          "none", t["ticker"].isna().sum(), flush=True)
    prices()
    print("DONE", round(time.time() - t0), flush=True)


def splits():
    """ประวัติ split ของทุก ticker ที่มีราคา (จำเป็นต่อ market cap แบบ PIT — บทเรียนบั๊ก v1)"""
    from lib import prices as P
    st = pd.read_parquet(P_STATUS)
    names = list(st.loc[st["n_days"] > 0, "yahoo"])
    return P.download_splits(names)


def retry_prices(passes: int = 3, batch: int = 20, pause: float = 3.0):
    """ดาวน์โหลดซ้ำ ticker ที่ได้ 0 วัน (บั๊กที่พบ: batch ใหญ่ล้มเหลวแบบเงียบ — TSLA/GOOG/JPM/UNH/SPY ได้ 0 วัน)
    และใช้ข้อมูลจาก price store หลัก (ตรวจแล้วใน v0) สำหรับ ticker ที่มีอยู่แล้ว"""
    from lib import prices as P
    status = pd.read_parquet(P_STATUS)
    frames = {k: pd.read_parquet(p) for k, p in (("close", P_CLOSE), ("adj", P_ADJ), ("vol", P_VOL))}
    main_close, main_adj = pd.read_parquet(P.CLOSE_FILE), pd.read_parquet(P.ADJ_FILE)
    for p_ in range(passes):
        zero = sorted(status.loc[status["n_days"] == 0, "yahoo"])
        print(f"pass {p_ + 1}: zero-day tickers {len(zero)}", flush=True)
        if not zero:
            break
        for i in range(0, len(zero), batch):
            chunk = zero[i:i + batch]
            try:
                d = yf.download(chunk, start="2008-01-01", auto_adjust=False, actions=False, progress=False, threads=False,
                                group_by="column")
            except Exception as e:  # noqa: BLE001
                print("error", e, flush=True)
                time.sleep(pause * 5)
                continue
            if d.empty:
                time.sleep(pause * 3)
                continue
            for k, col in (("close", "Close"), ("adj", "Adj Close"), ("vol", "Volume")):
                x = d[col].reindex(columns=chunk)
                for c in chunk:
                    if x[c].notna().any():
                        frames[k][c] = x[c].reindex(frames[k].index.union(x.index))
            for c in chunk:
                n = int(frames["close"][c].notna().sum()) if c in frames["close"] else 0
                status.loc[status["yahoo"] == c, "n_days"] = n
            time.sleep(pause)
        for k, p in (("close", P_CLOSE), ("adj", P_ADJ), ("vol", P_VOL)):
            frames[k].sort_index().to_parquet(p)
        status.to_parquet(P_STATUS)
    # เติม close/adj จาก store หลักถ้ายังว่าง
    for c in status.loc[status["n_days"] == 0, "yahoo"]:
        if c in main_close.columns and main_close[c].notna().any():
            frames["close"][c] = main_close[c].reindex(frames["close"].index)
            frames["adj"][c] = main_adj[c].reindex(frames["adj"].index)
            status.loc[status["yahoo"] == c, "n_days"] = int(main_close[c].notna().sum())
    for k, p in (("close", P_CLOSE), ("adj", P_ADJ), ("vol", P_VOL)):
        frames[k].sort_index().to_parquet(p)
    status.to_parquet(P_STATUS)
    print("still zero:", int((status["n_days"] == 0).sum()), "with data:", int((status["n_days"] > 0).sum()), flush=True)
