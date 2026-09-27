"""
Universe "top 1500 by market cap" (AUTORUN round 007) — ไม่มีรายชื่อ S&P 400/600 ย้อนหลังที่ตรวจได้ จึงสร้างจากข้อมูลของเราเอง

ขั้นตอน:
  1. pool(): ผู้สมัคร = top 3,000 ต่อปีตาม dei:EntityPublicFloat (SEC frames API, ปีปฏิทิน Q2) ปี 2009–2022 รวมกัน
     (frames = ค่าที่ filed ล่าสุด → ใช้แค่คัดผู้สมัครแบบกว้าง; สมาชิกจริงตัดสินแบบ PIT ใน panel)
  2. ticker ของแต่ละ CIK: ticker ปัจจุบัน (SEC) → ถ้าไม่มีใช้ prefix ของไฟล์ XBRL ใน 10-K ล่าสุด (ชื่อ ณ เวลานั้น)
"""

import json
import time

import pandas as pd
import requests

from lib.paths import INTERIM, SEC_DIR, SEC_USER_AGENT

FRAMES = SEC_DIR / "frames"
URL = "https://data.sec.gov/api/xbrl/frames/dei/EntityPublicFloat/USD/CY{y}Q{q}I.json"


def frames_float(years=range(2009, 2023)) -> pd.DataFrame:
    FRAMES.mkdir(parents=True, exist_ok=True)
    rows = []
    # public float วัด ณ สิ้นไตรมาส 2 ของ "ปีบัญชี" แต่ละบริษัท → ตกคนละไตรมาสปฏิทิน (Apple = มี.ค. = CY Q1)
    # บั๊กที่พบก่อนประเมิน round 007: ใช้แค่ CY Q2 ทำให้บริษัทที่ปีบัญชีไม่จบ ธ.ค. (เช่น AAPL) หายจาก pool → ใช้ครบ 4 ไตรมาส
    for y in years:
        for q in (1, 2, 3, 4):
            p = FRAMES / f"dei_EntityPublicFloat_USD_CY{y}Q{q}I.json"
            if not p.exists():
                r = requests.get(URL.format(y=y, q=q), headers={"User-Agent": SEC_USER_AGENT}, timeout=120)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                p.write_bytes(r.content)
                time.sleep(0.2)
            d = json.loads(p.read_text())
            df = pd.DataFrame(d["data"])
            df["year"] = y
            rows.append(df[["cik", "entityName", "loc", "end", "val", "year"]])
    f = pd.concat(rows, ignore_index=True)
    # 1 ค่าต่อบริษัทต่อปี (ค่าล่าสุดของปีนั้น)
    return f.sort_values("end").groupby(["cik", "year"], as_index=False).last()


def pool(top: int = 3000) -> pd.DataFrame:
    p = INTERIM / "pool1500.parquet"
    if p.exists():
        return pd.read_parquet(p)
    f = frames_float()
    f = f[f["val"] > 0]
    f["rank"] = f.groupby("year")["val"].rank(ascending=False, method="first")
    sel = f[f["rank"] <= top]
    out = sel.groupby("cik").agg(name=("entityName", "last"), years=("year", "nunique"), max_float=("val", "max")).reset_index()
    out.to_parquet(p, index=False)
    return out


def tickers_for(ciks, rss: pd.DataFrame, cik_ticker: dict) -> pd.DataFrame:
    k10 = rss[rss["form"].isin({"10-K", "10-K/A", "10-KT"}) & rss["prefix"].notna()].sort_values("filed")
    last_prefix = k10.groupby("cik")["prefix"].last()
    rows = []
    for c in ciks:
        cur = cik_ticker.get(c)
        pre = last_prefix.get(c)
        rows.append({"cik": c, "ticker_current": cur, "ticker_prefix": pre.upper() if isinstance(pre, str) else None,
                     "ticker": cur if cur else (pre.upper() if isinstance(pre, str) else None)})
    return pd.DataFrame(rows)
