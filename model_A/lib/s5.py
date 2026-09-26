"""
S5 — ด่านตรวจข้ามตลาด/ข้ามยุค (PREREG_AUTORUN ข้อ 4) — ใช้ตรวจ ไม่ใช้จูน

factor_check({"RMW": 0.5, "HML": 0.5}) → ค่าเฉลี่ยผลตอบแทนรายเดือนของ factor combo ใน 6 ชุด และผ่านเมื่อ > 0 ใน ≥ 4 ชุด
overlay_check(rule) → Sharpe ของ overlay เทียบ buy-and-hold ใน 6 ดัชนี (rf = 0) ผ่านเมื่อดีกว่า ≥ 4 ชุด
"""

import numpy as np
import pandas as pd

from lib import french, prices

FACTOR_SETS = [
    ("US 1963-2010", "US", "1963-07-01", "2010-12-31"),
    ("Developed ex US", "Developed_ex_US", None, None),
    ("Europe", "Europe", None, None),
    ("Japan", "Japan", None, None),
    ("Asia Pacific ex Japan", "Asia_Pacific_ex_Japan", None, None),
    ("Emerging", "Emerging", None, None),
]
INDEX_SETS = [("^GSPC 1970-2010", "^GSPC", "1970-01-01", "2010-12-31"), ("^N225", "^N225", None, None),
              ("^FTSE", "^FTSE", None, None), ("^GDAXI", "^GDAXI", None, None), ("^HSI", "^HSI", None, None),
              ("^STI", "^STI", None, None)]


def factor_check(combo: dict) -> pd.DataFrame:
    rows = []
    for label, region, a, b in FACTOR_SETS:
        f = french.load(region)
        if a:
            f = f.loc[a:b]
        s = sum(w * f[k] for k, w in combo.items()).dropna()
        rows.append({"set": label, "start": s.index.min().date(), "end": s.index.max().date(), "months": len(s),
                     "mean_monthly": s.mean(), "t": s.mean() / s.std() * np.sqrt(len(s)), "positive": bool(s.mean() > 0)})
    out = pd.DataFrame(rows)
    out.attrs["pass"] = int(out["positive"].sum()) >= 4
    return out


def _sharpe_daily(r: pd.Series) -> float:
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan


def overlay_check(rule) -> pd.DataFrame:
    """rule(price_series) → Series น้ำหนักหุ้น (0..1) ณ แต่ละวัน ใช้ข้อมูลถึงวันนั้น (ผลตอบแทนวันถัดไปใช้น้ำหนักวันนี้)"""
    px = prices.load_intl_index()
    rows = []
    for label, tk, a, b in INDEX_SETS:
        s = px[tk].dropna()
        if a:
            s = s.loc[a:b]
        r = s.pct_change()
        w = rule(s).shift(1)
        ov = (w * r).dropna()
        bh = r.loc[ov.index]
        rows.append({"set": label, "start": s.index.min().date(), "end": s.index.max().date(),
                     "sharpe_overlay": _sharpe_daily(ov), "sharpe_buyhold": _sharpe_daily(bh),
                     "better": bool(_sharpe_daily(ov) > _sharpe_daily(bh))})
    out = pd.DataFrame(rows)
    out.attrs["pass"] = int(out["better"].sum()) >= 4
    return out
