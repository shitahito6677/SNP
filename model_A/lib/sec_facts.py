"""
งบการเงินจาก SEC XBRL companyfacts API (https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json)

หลัก point-in-time (SPEC ข้อ 3 + ผู้ใช้กำหนดใน Phase 0):
  - ใช้ "ค่าที่ filed ครั้งแรก" ของแต่ละ (tag, งวด) — ถ้าบริษัทแก้งบย้อนหลัง (restate) เราไม่ใช้ค่าที่แก้
    เพราะ ณ วันตัดสินใจในอดีต นักลงทุนยังไม่เห็นค่าใหม่นั้น
  - วันที่ที่ใช้ได้ = `filed` (วันยื่นจริง) ไม่ใช่ `end` (วันสิ้นงวดบัญชี)
อุปมา: เหมือนสอบโดยใช้ได้แค่ "หนังสือพิมพ์ฉบับที่ออกแล้ว ณ วันนั้น" ห้ามใช้ฉบับแก้คำผิดที่ออกทีหลัง
"""

import gzip
import json
import time

import pandas as pd
import requests

from lib.paths import COMPANYFACTS_DIR, SEC_USER_AGENT

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "10-KT/A"}

# field → รายชื่อ tag เรียงตามลำดับความสำคัญ (ต่อบริษัท-ปี เลือก tag แรกที่มีค่า)
# kind: "duration" = ค่าสะสมทั้งปี (งบกำไรขาดทุน/กระแสเงินสด), "instant" = ค่า ณ วันสิ้นงวด (งบดุล)
FIELDS = {
    "net_income": ("duration", ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]),
    "cfo": ("duration", ["NetCashProvidedByUsedInOperatingActivities",
                         "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
    "revenue": ("duration", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                             "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax",
                             "SalesRevenueGoodsNet", "SalesRevenueServicesNet"]),
    "gross_profit": ("duration", ["GrossProfit"]),
    "cogs": ("duration", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
                          "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
                          "CostOfServices"]),  # บริษัทบริการ (เพิ่มหลัง v0 รอบแรก)
    "total_assets": ("instant", ["Assets"]),
    "current_assets": ("instant", ["AssetsCurrent"]),
    "current_liabilities": ("instant", ["LiabilitiesCurrent"]),
    "lt_debt": ("instant", ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations",
                            "LongTermDebt", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"]),
    "equity": ("instant", ["StockholdersEquity",
                           "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "shares_out": ("instant", ["CommonStockSharesOutstanding"]),
    # ใช้เป็นหลักฐานว่า "ไม่มีหนี้" เมื่อไม่มี tag หนี้ระยะยาว (ผู้ใช้กำหนดหลัง v0: หนี้ = 0 ได้เฉพาะเมื่อมีหลักฐาน)
    "interest_expense": ("duration", ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                                      "InterestAndDebtExpense"]),
    # fallback จำนวนหุ้น: บริษัทหลาย class (เช่น META, BRK) รายงานหุ้นคงเหลือแยกตาม class ซึ่ง companyfacts ไม่รวม
    "shares_wavg": ("duration", ["WeightedAverageNumberOfSharesOutstandingBasic"]),
}
DEI_SHARES = "EntityCommonStockSharesOutstanding"


def fetch(cik: int, session: requests.Session = None) -> bool:
    """ดาวน์โหลด companyfacts ของ cik เก็บเป็น .json.gz (cache) — คืน False ถ้า SEC ไม่มีข้อมูล (404)"""
    out = COMPANYFACTS_DIR / f"CIK{cik:010d}.json.gz"
    if out.exists():
        return True
    session = session or requests.Session()
    session.headers["User-Agent"] = SEC_USER_AGENT
    for attempt in range(4):
        r = session.get(URL.format(cik=cik), timeout=120)
        if r.status_code in (200, 404):
            break
        time.sleep(2 * (attempt + 1))
    time.sleep(0.15)  # < 10 req/s ตาม SEC fair-access policy
    if r.status_code == 404:
        return False
    r.raise_for_status()
    out.write_bytes(gzip.compress(r.content))
    return True


def load_raw(cik: int) -> dict:
    p = COMPANYFACTS_DIR / f"CIK{cik:010d}.json.gz"
    return json.loads(gzip.decompress(p.read_bytes())) if p.exists() else None


def _records(facts: dict, taxonomy: str, tag: str, unit: str) -> pd.DataFrame:
    try:
        recs = facts["facts"][taxonomy][tag]["units"][unit]
    except KeyError:
        return pd.DataFrame()
    df = pd.DataFrame(recs)
    if "start" not in df.columns:
        df["start"] = None
    df["tag"] = tag
    return df


def first_filed_annual(cik: int) -> pd.DataFrame:
    """ตาราง long: cik, field, tag, fy_end, val, filed — ค่ารายปีที่ filed ครั้งแรกจากฟอร์ม 10-K
    fy_end = วันสิ้นงวดบัญชี, filed = วันที่ค่านี้ถูกเปิดเผยครั้งแรก (ใช้ตัดสินใจได้หลังวันนี้เท่านั้น)"""
    facts = load_raw(cik)
    if facts is None:
        return pd.DataFrame()
    rows = []
    for field, (kind, tags) in FIELDS.items():
        unit = "shares" if field.startswith("shares") else "USD"
        for tag in tags:
            df = _records(facts, "us-gaap", tag, unit)
            if df.empty:
                continue
            df = df[df["form"].isin(ANNUAL_FORMS)].copy()
            df["end"] = pd.to_datetime(df["end"])
            df["filed"] = pd.to_datetime(df["filed"])
            if kind == "duration":
                df = df[df["start"].notna()]
                dur = (df["end"] - pd.to_datetime(df["start"])).dt.days
                df = df[(dur >= 350) & (dur <= 380)]
            else:
                df = df[df["start"].isna()]
            if df.empty:
                continue
            g = df.sort_values(["end", "filed"]).groupby("end")
            first = g.first().reset_index()
            # เก็บค่าที่ filed ครั้งสุดท้ายไว้ด้วย เพื่อวัดว่ามีการ restate บ่อยแค่ไหน (ไม่ใช้ในการตัดสินใจ)
            last = g.last()[["val", "filed"]].rename(columns={"val": "val_last", "filed": "filed_last"}).reset_index()
            df = first.merge(last, on="end")
            df["field"] = field
            rows.append(df[["field", "tag", "end", "val", "filed", "form", "accn", "val_last", "filed_last"]])
    # dei:EntityCommonStockSharesOutstanding (หน้าปกงบ) เป็น fallback ของจำนวนหุ้น
    dei = _records(facts, "dei", DEI_SHARES, "shares")
    if not dei.empty:
        dei = dei[dei["form"].isin(ANNUAL_FORMS)].copy()
        dei["end"] = pd.to_datetime(dei["end"])
        dei["filed"] = pd.to_datetime(dei["filed"])
        # ค่าหน้าปกผูกกับ filing ไม่ใช่งวด — ใช้ accn เดียวกันกับ 10-K และรวมทุก class ของหุ้น
        dei = dei.groupby(["accn", "filed", "form"], as_index=False).agg(val=("val", "sum"), end=("end", "max"))
        dei["field"], dei["tag"] = "shares_cover", DEI_SHARES
        rows.append(dei[["field", "tag", "end", "val", "filed", "form", "accn"]])
    if not rows:
        return pd.DataFrame()
    long = pd.concat(rows, ignore_index=True)
    long.insert(0, "cik", cik)
    return long.rename(columns={"end": "period_end"})


def annual_wide(long: pd.DataFrame) -> pd.DataFrame:
    """long → wide 1 แถวต่อ (cik, fy_end) ใช้ tag แรกตามลำดับความสำคัญที่มีค่าในปีนั้น
    fy_end ของแต่ละบริษัทนิยามจาก period_end ของ total_assets (instant ณ สิ้นปีบัญชีใน 10-K)"""
    if long.empty:
        return pd.DataFrame()
    prio = {f: {t: i for i, t in enumerate(tags)} for f, (_, tags) in FIELDS.items()}
    x = long[long["field"] != "shares_cover"].copy()
    x["prio"] = [prio[f].get(t, 99) for f, t in zip(x["field"], x["tag"])]
    x = x.sort_values("prio").groupby(["cik", "field", "period_end"], as_index=False).first()
    val = x.pivot_table(index=["cik", "period_end"], columns="field", values="val", aggfunc="first")
    filed = x.pivot_table(index=["cik", "period_end"], columns="field", values="filed", aggfunc="max")
    val["filed_max"] = filed.max(axis=1)  # วันที่ทุก field ในแถวนี้เปิดเผยครบแล้ว
    return val.reset_index()


def tenk_profile(cik: int) -> tuple:
    """(DataFrame[accn, filed] ของ 10-K ไม่ซ้ำ, median total assets) — ใช้เลือก CIK ใน lib.cik_map.build_segments
    accn ใช้ตรวจ combined filing: filing เดียวกันของบริษัทแม่+ลูก จะมี accn เดียวกันใน companyfacts ของทั้งคู่"""
    empty = pd.DataFrame({"accn": pd.Series(dtype=str), "filed": pd.Series(dtype="datetime64[ns]")})
    facts = load_raw(cik)
    if facts is None:
        return empty, None
    frames = []
    for tax, tag, unit in (("us-gaap", "Assets", "USD"), ("dei", DEI_SHARES, "shares")):
        df = _records(facts, tax, tag, unit)
        if not df.empty:
            frames.append(df)
    if not frames:
        return empty, None
    df = pd.concat(frames, ignore_index=True)
    df = df[df["form"].isin(ANNUAL_FORMS)]
    fil = df.drop_duplicates("accn")[["accn", "filed"]].assign(filed=lambda d: pd.to_datetime(d["filed"]))
    fil = fil.sort_values("filed").reset_index(drop=True)
    a = pd.to_numeric(df.loc[df["tag"] == "Assets", "val"], errors="coerce").median()
    return fil, (None if pd.isna(a) else float(a))


def public_float(cik: int) -> pd.DataFrame:
    """dei:EntityPublicFloat (มูลค่าหุ้นที่ถือโดยคนนอก ณ วันทำการสุดท้ายของไตรมาส 2 ของบริษัท) — ใช้ "ตรวจ" market cap
    ที่เราคำนวณเท่านั้น ไม่ใช้ตัดสินใจลงทุน (ค่านี้เปิดเผยทีหลังในงบปีถัดไป)"""
    facts = load_raw(cik)
    if facts is None:
        return pd.DataFrame()
    df = _records(facts, "dei", "EntityPublicFloat", "USD")
    if df.empty:
        return df
    df = df[df["form"].isin(ANNUAL_FORMS)].copy()
    df["end"] = pd.to_datetime(df["end"])
    return df.sort_values("filed").groupby("end", as_index=False).first()[["end", "val"]].assign(cik=cik)
