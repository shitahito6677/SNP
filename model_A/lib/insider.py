"""
SEC Insider Transactions Data Sets (Form 3/4/5) — https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
มีตั้งแต่ 2006Q1 (ตรวจ 2026-09-27); ดาวน์โหลดถึง 2023Q2 เท่านั้น (held-out lock: ไม่โหลดไตรมาสหลัง cutoff)
เก็บเฉพาะรายการ non-derivative ของบริษัทใน S&P 500 (CIK จาก cik_segments) เป็น parquet ต่อไตรมาส

ข้อจำกัด: ธง 10b5-1 (Rule 10b5-1 plan) เพิ่งมีในแบบฟอร์มตั้งแต่ 2023 → ตัดรายการตามแผนล่วงหน้าไม่ได้ในช่วงทดสอบ
"""
import io
import time
import zipfile

import pandas as pd
import requests

from lib import guard
from lib.paths import INTERIM, SEC_DIR, SEC_USER_AGENT

DIR = SEC_DIR / "insider"
URLS = ["https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip",
        "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{q}_form345.zip"]


def quarters(start=(2006, 1), end=(2023, 2)):
    y, q = start
    while (y, q) <= end:
        yield f"{y}q{q}"
        q += 1
        if q == 5:
            y, q = y + 1, 1


def fetch(q: str) -> bytes:
    p = DIR / f"{q}_form345.zip"
    if not p.exists():
        for u in URLS:
            r = requests.get(u.format(q=q), headers={"User-Agent": SEC_USER_AGENT}, timeout=300)
            if r.status_code == 200:
                p.write_bytes(r.content)
                break
        time.sleep(0.3)
    return p.read_bytes()


def extract(q: str, ciks: set) -> pd.DataFrame:
    out = DIR / f"{q}_sp500.parquet"
    if out.exists():
        return pd.read_parquet(out)
    z = zipfile.ZipFile(io.BytesIO(fetch(q)))
    rd = lambda n, cols: pd.read_csv(z.open(n), sep="\t", usecols=cols, dtype=str, quoting=3, on_bad_lines="skip")
    sub = rd("SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK"])
    sub["ISSUERCIK"] = pd.to_numeric(sub["ISSUERCIK"], errors="coerce")
    sub = sub[sub["ISSUERCIK"].isin(ciks)]
    own = rd("REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP"])
    own["RPTOWNERCIK"] = pd.to_numeric(own["RPTOWNERCIK"], errors="coerce")
    own = own.sort_values("RPTOWNERCIK").drop_duplicates("ACCESSION_NUMBER")  # joint filing → นับให้เจ้าของคนแรกคนเดียว (กันนับซ้ำ)
    tr = rd("NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD"])
    df = tr.merge(sub, on="ACCESSION_NUMBER").merge(own, on="ACCESSION_NUMBER", how="left")
    df["FILING_DATE"] = pd.to_datetime(df["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
    df["TRANS_DATE"] = pd.to_datetime(df["TRANS_DATE"], format="%d-%b-%Y", errors="coerce")
    for c in ("TRANS_SHARES", "TRANS_PRICEPERSHARE"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["quarter"] = q
    df.to_parquet(out, index=False)
    return df


def load_all(ciks: set) -> pd.DataFrame:
    DIR.mkdir(parents=True, exist_ok=True)
    parts = []
    for q in quarters():
        parts.append(extract(q, ciks))
        print(q, len(parts[-1]), flush=True)
    df = pd.concat(parts, ignore_index=True)
    df = df[df["FILING_DATE"] <= guard.CUTOFF]
    df.to_parquet(INTERIM / "insider_sp500.parquet", index=False)
    return df


if __name__ == "__main__":
    segs = pd.read_parquet(INTERIM / "cik_segments.parquet")
    load_all(set(segs["cik"].dropna().astype(int)))
