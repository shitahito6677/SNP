"""
ฟังก์ชันตรวจความครอบคลุมของข้อมูล (ใช้ใน v0_data_audit.ipynb)

นิยามหลัก:
  rebalance date R = วันทำการสุดท้ายของเดือนมิถุนายนแต่ละปี (PREREG ที่ผู้ใช้ยืนยันแล้ว)
  งบที่ "ใช้ได้" ณ R = ตาม lib.pit.PIT (เลือกทีละ field เฉพาะค่าที่ filed <= R - 1 วัน,
                         งบปีล่าสุดต้องไม่เก่ากว่า 18 เดือน)
"""

import re

import numpy as np
import pandas as pd

from lib import fscore

# ข้อมูลที่ต้องมีเพื่อคำนวณ F-score ครบ 9 ข้อ (t = ปีล่าสุด, t1 = ปีก่อน, t2 = สองปีก่อน)
FSCORE_NEEDS = {
    "net_income": ["t", "t1"],
    "cfo": ["t"],
    "total_assets": ["t", "t1", "t2"],   # ROA ใช้สินทรัพย์ต้นปี → ΔROA ต้องมีถึง t-2
    "lt_debt": ["t", "t1"],
    "current_assets": ["t", "t1"],
    "current_liabilities": ["t", "t1"],
    "shares": ["t", "t1"],
    "revenue": ["t", "t1"],
    "gross_profit_any": ["t", "t1"],     # GrossProfit หรือ revenue - cogs
}
BM_NEEDS = {"equity": ["t"], "shares": ["t"]}

FIN_SIC = (6000, 6799)  # ธนาคาร/ประกัน/การเงิน/REIT ตาม SIC (proxy ของ GICS Financials+Real Estate)


def rebalance_dates(price_index: pd.DatetimeIndex, years) -> list:
    out = []
    for y in years:
        d = price_index[(price_index.year == y) & (price_index.month == 6)]
        if len(d):
            out.append(d.max())
    return out


def field_ok(rows: dict, needs: dict) -> dict:
    out = {}
    for f, ks in needs.items():
        out[f] = all(rows.get(k) is not None and pd.notna(rows[k].get(f, np.nan)) for k in ks)
    return out


def is_financial(sic) -> bool:
    return pd.notna(sic) and FIN_SIC[0] <= int(sic) <= FIN_SIC[1]


def cik_for(segs: pd.DataFrame, ticker: str, R: pd.Timestamp):
    """หา cik ของ ticker จาก segment (lib.cik_map) ที่ครอบวัน R"""
    m = segs[(segs["ticker"] == ticker) & (segs["valid_from"] <= R) & ((segs["valid_to"].isna()) | (segs["valid_to"] >= R))]
    if m.empty or pd.isna(m["cik"].iloc[0]):
        return None
    return int(m["cik"].iloc[0])


def build_panel(hist, segs, pit, adj, close, splits, Rs, to_yahoo, sic_of: dict, cik_ticker: dict,
                split_factor_after) -> pd.DataFrame:
    """1 แถวต่อ (R, ticker สมาชิก ณ R) พร้อม flag ความครบของข้อมูลแต่ละส่วน
    sic_of: cik -> SIC ล่าสุด (จาก SEC RSS) ใช้แยกกลุ่มการเงิน"""
    rows = []
    for R in Rs:
        members = hist[hist["date"] <= R].iloc[-1]["tickers"]
        R1 = R + pd.DateOffset(years=1)
        for t in members:
            cik = cik_for(segs, t, R)
            sic = sic_of.get(cik) if cik is not None else None
            rs = pit.rows_asof(cik, R) if cik is not None else {"t": None, "t1": None, "t2": None}
            shares = rs["t"].get("shares", np.nan) if rs["t"] is not None else np.nan
            sratio = rs["t"].get("shares_ratio", np.nan) if rs["t"] is not None else np.nan
            sdate = rs["t"].get("shares_date", None) if rs["t"] is not None else None
            pr = choose_price(t, cik, R, shares, sratio, adj, close, splits, cik_ticker, to_yahoo, split_factor_after,
                              sdate)
            fwd = adj[pr["yahoo"]].loc[R:R1] if pr["yahoo"] else None
            row = {"R": R, "ticker": t, "cik": cik, "sic": sic,
                   "financial": is_financial(sic),
                   "has_cik": cik is not None,
                   "has_price_R": pr["yahoo"] is not None,
                   **pr,
                   "fwd_days": int(fwd.notna().sum()) if fwd is not None else 0}
            row["has_fy_t"] = rs["t"] is not None
            if rs["t"] is not None:
                row["fy_t_end"] = rs["t"].name
                row["shares_t"] = shares
                row["shares_ratio"] = sratio
            ok = field_ok(rs, FSCORE_NEEDS)
            row.update({f"f_{k}": v for k, v in ok.items()})
            row["fscore_complete"] = all(ok.values())
            ok_ltd0 = dict(ok)
            if rs["t"] is not None and rs["t1"] is not None:
                ok_ltd0["lt_debt"] = True  # สมมติ: ไม่มี tag หนี้ระยะยาว = ไม่มีหนี้ (ต้องให้ผู้ใช้ตัดสิน)
            row["fscore_complete_ltd0"] = all(ok_ltd0.values())
            # ความพร้อมของสัญญาณ F-score รายข้อ ภายใต้นโยบายหนี้ 2 แบบ (ดู lib/fscore.py) — ไม่ได้ใช้ผลตอบแทน
            if rs["t"] is not None and rs["t1"] is not None and pr["yahoo"]:
                sf = split_factor_between(splits, pr["yahoo"], rs["t1"]["shares_date"], rs["t"]["shares_date"])
            else:
                sf = 1.0
            for pol in ("evidence", "zero"):
                sg = fscore.signals(rs, sf, ltd_policy=pol)
                _, n_av = fscore.score(sg, "rescale")
                row[f"n_sig_{pol}"] = n_av if rs["t"] is not None else 0
                if pol == "evidence":
                    row.update({f"av_{k}": pd.notna(sg[k]) for k in fscore.SIGNALS})
                    row["ltd_status_t"], row["ltd_status_t1"] = sg["ltd_status_t"], sg["ltd_status_t1"]
            row["bm_complete"] = all(field_ok(rs, BM_NEEDS).values()) and pd.notna(row["mcap_R"])
            rows.append(row)
    return pd.DataFrame(rows)


MIN_MCAP = 1e9  # สมาชิก S&P 500 ควรมี market cap ≥ $1B — ต่ำกว่านี้ = สงสัยว่าราคาเป็นของบริษัทอื่น (ticker reuse)
MIN_PRICE = 1.0  # ราคาจริง < $1 = หุ้นเพนนี (เช่น CPWR หลังถูก Ocean Thermal ใช้ ticker ต่อ); ไม่ใช้ $2 เพราะ AIG มิ.ย. 2009 ซื้อขายจริง ~$1.16


def common_ticker(tickers) -> str:
    """เลือก ticker หุ้นสามัญจากรายชื่อ ticker ปัจจุบันของ CIK (ตัด preferred -P*, warrant -W*, rights -R*)"""
    if not tickers:
        return None
    ok = [t for t in tickers if not re.search(r"-(P[A-Z]?|WT?|R[I]?|U)$", t) and not re.search(r"(P[A-Z]|W|L|M|N|O)$", t[4:])]
    return (ok or [None])[0]


def choose_price(t, cik, R, shares, shares_ratio, adj, close, splits, cik_ticker: dict, to_yahoo, split_factor_after,
                 shares_date=None):
    """เลือกแหล่งราคา ณ วัน R จาก 2 ผู้สมัคร: ticker ตาม fja (ชื่อ ณ เวลานั้น) และ ticker ปัจจุบันของ CIK (กรณีเปลี่ยนชื่อ)
    ราคาต้องมีค่าภายใน 5 วันทำการก่อน R และต้องไม่ใช่ "บริษัทอื่นที่ใช้ ticker ซ้ำ" ซึ่งตัดสินจาก
      (ก) ราคาจริง (ย้อน split) < MIN_PRICE → หุ้นเพนนี ไม่ใช่สมาชิก S&P 500
      (ข) market cap < MIN_MCAP โดยที่จำนวนหุ้นจาก 2 แหล่ง (dei, us-gaap) สอดคล้องกัน (ต่างกันไม่เกิน 2 เท่า)
    ถ้าจำนวนหุ้น 2 แหล่งขัดกัน → ไม่ใช้ market cap ตัดสิน แต่ flag ไว้ (shares_suspect)"""
    # ลำดับ: ticker ปัจจุบันของ CIK ก่อน (CIK = ตัวตนของบริษัท) แล้วค่อย ticker ตาม fja
    # บทเรียน v1: ราคา Yahoo ของ "IR" ปี 2017-2019 เป็นของ Gardner Denver (เจ้าของ ticker ปัจจุบัน) ไม่ใช่
    # Ingersoll-Rand plc (สมาชิกจริง, ปัจจุบันคือ TT) และ market cap ยังเกิน $1B จึงหลุดการตรวจ mcap
    fja_y = to_yahoo(t)
    ct = cik_ticker.get(cik) if cik is not None else None
    cands = [("cik", to_yahoo(ct))] if ct and to_yahoo(ct) != fja_y else []
    cands.append(("fja", fja_y))
    consistent = pd.notna(shares_ratio) and 0.5 <= shares_ratio <= 2
    result = {"price_src": None, "yahoo": None, "raw_price": np.nan, "mcap_R": np.nan, "price_flag": "no_price"}
    for src, y in cands:
        if y not in close.columns:
            continue
        px = close[y].loc[:R].tail(5).dropna()
        if px.empty:
            continue
        raw = float(px.iloc[-1]) * split_factor_after(splits, y, px.index[-1])
        sh = shares
        if pd.notna(sh) and shares_date is not None and pd.notna(shares_date):
            sh = sh * split_factor_between(splits, y, shares_date, px.index[-1])  # split หลังวันนับหุ้น ถึงวันราคา
        mcap = raw * sh if pd.notna(sh) and sh > 0 else np.nan
        if raw < MIN_PRICE:
            reject = f"penny_{src}"
        elif pd.notna(mcap) and mcap < MIN_MCAP and consistent:
            reject = f"mcap_small_{src}"
        else:
            flag = "ok" if pd.notna(mcap) and (consistent or pd.isna(shares_ratio)) and mcap >= MIN_MCAP else \
                   ("ok_no_shares" if pd.isna(mcap) else "ok_shares_suspect")
            return {"price_src": src, "yahoo": y, "raw_price": raw,
                    "mcap_R": mcap if flag == "ok" else np.nan, "price_flag": flag}
        if result["price_flag"] == "no_price":
            result.update(price_flag=reject, raw_price=raw, mcap_R=mcap)
    return result


def split_factor_between(splits: pd.DataFrame, yahoo: str, d0, d1) -> float:
    """ผลคูณ split ratio ที่เกิดในช่วง (d0, d1] — ใช้ปรับจำนวนหุ้นปีก่อนให้เทียบกับปีนี้ได้ (F_EQ)"""
    s = splits[(splits["yahoo"] == yahoo) & (splits["date"] > d0) & (splits["date"] <= d1)]
    return float(s["ratio"].prod()) if len(s) else 1.0


# กลุ่มอุตสาหกรรมจาก SIC (SEC ไม่มี GICS ย้อนหลัง — ใช้ SIC ของ SEC เป็น proxy และระบุไว้ทุกครั้งที่รายงาน)
SIC_GROUPS = [
    ((100, 999), "Agriculture"), ((1000, 1299), "Mining (metals/coal)"), ((1300, 1399), "Oil & gas extraction"),
    ((1400, 1499), "Mining (other)"), ((1500, 1799), "Construction"), ((2000, 2099), "Food & beverage mfg"),
    ((2800, 2836), "Chemicals & pharma"), ((2837, 2899), "Chemicals (other)"), ((2900, 2999), "Petroleum refining"),
    ((3500, 3599), "Machinery & computers"), ((3600, 3699), "Electronics & semis"), ((3700, 3799), "Transport equipment"),
    ((3800, 3899), "Instruments & medical devices"), ((2100, 3999), "Other manufacturing"),
    ((4000, 4799), "Transportation"), ((4800, 4899), "Communications"), ((4900, 4999), "Utilities"),
    ((5000, 5199), "Wholesale"), ((5200, 5999), "Retail"), ((6000, 6799), "Finance/insurance/REIT"),
    ((7000, 7299), "Services (hotels/personal)"), ((7300, 7399), "Business services & software"),
    ((7400, 7999), "Services (other)"), ((8000, 8099), "Health services"), ((8100, 8999), "Services (professional)"),
]


def sic_group(sic) -> str:
    if pd.isna(sic):
        return "unknown SIC"
    s = int(sic)
    for (lo, hi), name in SIC_GROUPS:
        if lo <= s <= hi:
            return name
    return "other"
