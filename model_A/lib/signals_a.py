"""
สัญญาณตระกูล A เพิ่มเติม (AUTORUN round 001) — คำนวณจากตาราง PIT (period_end × field) ณ วัน R

  A_GSCORE   G-score (Mohanram 2005) 8 ข้อ เทียบค่ากลางของกลุ่ม SIC ณ R (คำนวณใน lib.panel หลังรวมทั้ง universe)
             ข้อมูลดิบที่ต้องใช้คำนวณที่นี่: roa, cfo_ta, cfo_gt_ni, roa_std5, sales_growth_std5, rnd_ta, capex_ta, adv_ta
             (R&D / advertising ที่ไม่มี tag = 0 ตาม Mohanram)
  A_ALTMANZ  Z = 1.2 WC/TA + 1.4 RE/TA + 3.3 EBIT/TA + 0.6 MVE/TL + 1.0 Sales/TA  (Altman 1968; สูง = ปลอดภัย)
  A_BENEISHM M = −4.84 + 0.92 DSRI + 0.528 GMI + 0.404 AQI + 0.892 SGI + 0.115 DEPI − 0.172 SGAI + 4.679 TATA − 0.327 LVGI
             (Beneish 1999; flag เมื่อ M > −1.78; คำนวณไม่ได้ = ไม่ flag)
  A_SHY      net payout yield = (ปันผล + ซื้อหุ้นคืน − ออกหุ้น) / market cap (ไม่มี tag = 0)
  A_STAB     −std(ROA) ของงบปีล่าสุด 5 ปี (ต้องมี ≥ 3 ปี) — กำไรเสถียร = ดี
  A_LOWLEV   −(total liabilities / total assets) (ไม่มี Liabilities ใช้ TA − equity)
"""

import numpy as np
import pandas as pd


def _div(a, b):
    return np.nan if pd.isna(a) or pd.isna(b) or b == 0 else a / b


def _z(v):
    return 0.0 if pd.isna(v) else v


def annual_rows(w: pd.DataFrame, t_end) -> pd.DataFrame:
    """งบรายปีย้อนหลังที่ห่างกัน ~1 ปีจาก t_end (period_end ของงบล่าสุด) สูงสุด 5 ปี"""
    out = [w.loc[t_end]]
    ref = t_end
    for _ in range(4):
        lo, hi = ref - pd.Timedelta(days=365 + 40), ref - pd.Timedelta(days=365 - 40)
        c = w[(w.index >= lo) & (w.index <= hi)]
        if c.empty:
            break
        ref = c.index[-1]
        out.append(c.iloc[-1])
    return pd.DataFrame(out)


def compute(w: pd.DataFrame, rs: dict, mcap: float) -> dict:
    t, t1 = rs.get("t"), rs.get("t1")
    nan = {k: np.nan for k in ["A_ALTMANZ", "A_BENEISHM", "A_SHY", "A_STAB", "A_LOWLEV", "g_roa", "g_cfo_ta",
                               "g_cfo_gt_ni", "g_roa_std", "g_sg_std", "g_rnd_ta", "g_capex_ta", "g_adv_ta"]}
    if t is None:
        return nan
    g = lambda r, f: np.nan if r is None else r.get(f, np.nan)
    ta, ta1 = g(t, "total_assets"), g(t1, "total_assets")
    tl = g(t, "liabilities")
    if pd.isna(tl):
        tl = ta - g(t, "equity") if pd.notna(ta) and pd.notna(g(t, "equity")) else np.nan
    out = dict(nan)
    # Altman Z
    wc = g(t, "current_assets") - g(t, "current_liabilities")
    parts = [_div(wc, ta), _div(g(t, "retained_earnings"), ta), _div(g(t, "ebit"), ta), _div(mcap, tl), _div(g(t, "revenue"), ta)]
    out["A_ALTMANZ"] = np.nan if any(pd.isna(p) for p in parts) else \
        1.2 * parts[0] + 1.4 * parts[1] + 3.3 * parts[2] + 0.6 * parts[3] + 1.0 * parts[4]
    # Beneish M
    if t1 is not None:
        rev, rev1 = g(t, "revenue"), g(t1, "revenue")
        dsri = _div(_div(g(t, "receivables"), rev), _div(g(t1, "receivables"), rev1))
        gmi = _div(_div(g(t1, "gross_profit_any"), rev1), _div(g(t, "gross_profit_any"), rev))
        aq = lambda r, tta: 1 - _div(g(r, "current_assets") + g(r, "ppe"), tta)
        aqi = _div(aq(t, ta), aq(t1, ta1))
        sgi = _div(rev, rev1)
        dep = lambda r: _div(g(r, "depreciation"), g(r, "depreciation") + g(r, "ppe"))
        depi = _div(dep(t1), dep(t))
        sgai = _div(_div(g(t, "sga"), rev), _div(g(t1, "sga"), rev1))
        tata = _div(g(t, "net_income") - g(t, "cfo"), ta)
        tl1 = g(t1, "liabilities")
        lvgi = _div(_div(tl, ta), _div(tl1, ta1))
        comp = [dsri, gmi, aqi, sgi, depi, sgai, tata, lvgi]
        out["A_BENEISHM"] = np.nan if any(pd.isna(c) for c in comp) else (
            -4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai
            + 4.679 * tata - 0.327 * lvgi)
    # shareholder yield
    out["A_SHY"] = _div(_z(g(t, "dividends_paid")) + _z(g(t, "buybacks")) - _z(g(t, "stock_issued")), mcap)
    # stability & G-score raw
    hist = annual_rows(w, t.name)
    ta_hist = hist["total_assets"].shift(-1)  # สินทรัพย์ต้นปี = งบปีก่อนหน้า
    roa_hist = (hist["net_income"] / ta_hist).dropna()
    out["A_STAB"] = -roa_hist.std(ddof=1) if len(roa_hist) >= 3 else np.nan
    sg = (hist["revenue"] / hist["revenue"].shift(-1) - 1).dropna()
    out["A_LOWLEV"] = -_div(tl, ta)
    out["g_roa"] = _div(g(t, "net_income"), ta1)
    out["g_cfo_ta"] = _div(g(t, "cfo"), ta1)
    out["g_cfo_gt_ni"] = np.nan if pd.isna(g(t, "cfo")) or pd.isna(g(t, "net_income")) else float(g(t, "cfo") > g(t, "net_income"))
    out["g_roa_std"] = roa_hist.std(ddof=1) if len(roa_hist) >= 3 else np.nan
    out["g_sg_std"] = sg.std(ddof=1) if len(sg) >= 3 else np.nan
    out["g_rnd_ta"] = _div(_z(g(t, "rnd")), ta)
    out["g_capex_ta"] = _div(g(t, "capex"), ta)
    out["g_adv_ta"] = _div(_z(g(t, "advertising")), ta)
    return out


def gscore(df: pd.DataFrame, group_col: str = "sic_group") -> pd.Series:
    """G-score 8 ข้อ: ค่ามากกว่าค่ากลางของกลุ่ม (ข้อ variability: น้อยกว่าค่ากลาง) ณ วันเดียวกัน — ต้องมี ≥ 6 ข้อ"""
    def one(g):
        s = pd.DataFrame(index=g.index)
        for c in ["g_roa", "g_cfo_ta", "g_rnd_ta", "g_capex_ta", "g_adv_ta"]:
            med = g[c].median()
            s[c] = np.where(g[c].isna(), np.nan, (g[c] > med).astype(float))
        s["g_cfo_gt_ni"] = g["g_cfo_gt_ni"]
        for c in ["g_roa_std", "g_sg_std"]:
            med = g[c].median()
            s[c] = np.where(g[c].isna(), np.nan, (g[c] < med).astype(float))
        n = s.notna().sum(axis=1)
        return (s.sum(axis=1) * 8 / n).where(n >= 6)
    return df.groupby(["R", group_col], group_keys=False).apply(one)
