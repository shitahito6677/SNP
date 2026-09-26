"""
สัญญาณราคา (AUTORUN round 003) — คำนวณจาก Adj Close ที่ถูกล็อก held-out แล้ว (ใช้เฉพาะราคา ≤ วัน R)

  C_MOM     momentum 12-1: P(R − 21 วันทำการ) / P(R − 252) − 1           (Jegadeesh & Titman 1993)
  C_LOWVOL  −std ของผลตอบแทนรายวัน 252 วันล่าสุด                         (Ang et al. 2006; Baker, Bradley & Wurgler 2011)
  C_TREND   P(R) / ค่าเฉลี่ย 200 วัน − 1                                   (Faber 2007; Han, Zhou & Zhu 2016)
  C_HI52    P(R) / สูงสุด 252 วัน − 1 (ใกล้จุดสูงสุด 52 สัปดาห์ = ดี)      (George & Hwang 2004)
ต้องมีราคาที่ใช้ได้ ≥ 200 วันในหน้าต่าง 252 วัน มิฉะนั้น = ไม่ทราบ
"""

import numpy as np
import pandas as pd


def compute(adj: pd.DataFrame, dates, tickers) -> pd.DataFrame:
    px = adj[[t for t in sorted(set(tickers)) if t in adj.columns]]
    ret = px.pct_change(fill_method=None)
    rows = []
    idx = px.index
    for R in dates:
        i = idx.searchsorted(R, side="right") - 1
        if i < 252:
            continue
        win = px.iloc[i - 251:i + 1]
        n_ok = win.notna().sum()
        p_now = win.iloc[-1]
        mom = px.iloc[i - 21] / px.iloc[i - 252] - 1
        vol = ret.iloc[i - 251:i + 1].std()
        sma = px.iloc[i - 199:i + 1].mean()
        hi = win.max()
        d = pd.DataFrame({"C_MOM": mom, "C_LOWVOL": -vol, "C_TREND": p_now / sma - 1, "C_HI52": p_now / hi - 1})
        d[n_ok < 200] = np.nan
        d["R"], d["yahoo"] = idx[i] if idx[i] == R else R, d.index
        rows.append(d.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)
