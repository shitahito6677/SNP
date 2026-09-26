"""
Piotroski F-score 9 ข้อ (Piotroski 2000) จากงบ point-in-time (lib.pit) — คืนทั้งคะแนนรายข้อและ "คำนวณได้ไหม"

สัญญาณ (1 = ดี, 0 = ไม่ดี, NaN = คำนวณไม่ได้เพราะข้อมูลขาด):
  Profitability  F_ROA      NI_t / TA_{t-1} > 0
                 F_CFO      CFO_t / TA_{t-1} > 0
                 F_dROA     ROA_t > ROA_{t-1}           (ROA_{t-1} = NI_{t-1} / TA_{t-2})
                 F_ACCRUAL  CFO_t / TA_{t-1} > ROA_t
  Leverage/Liq.  F_dLEVER   LTD/avg(TA) ลดลง (หรือ = 0 ทั้งสองปี)
                 F_dLIQUID  CA/CL เพิ่มขึ้น
                 F_EQ       ไม่ออกหุ้นใหม่: shares_t <= shares_{t-1} × split factor ระหว่างสองงวด
  Efficiency     F_dMARGIN  GM_t > GM_{t-1}             (GM = gross profit / revenue)
                 F_dTURN    revenue_t/TA_{t-1} > revenue_{t-1}/TA_{t-2}

นโยบายข้อมูลขาด (ผู้ใช้กำหนดหลัง v0 — ล็อกใน PREREG.md):
  ltd_policy="evidence" (หลัก): ไม่มี tag หนี้ระยะยาว → = 0 ก็ต่อเมื่อ interest expense ถูกรายงานและ = 0 ในปีนั้น
                                นอกนั้น = ไม่ทราบ (NaN)
  ltd_policy="zero"     (sensitivity): ไม่มี tag หนี้ระยะยาว → = 0 เสมอ
  score_policy="rescale" (หลัก): ต้องคำนวณได้ >= 8 ใน 9 ข้อ แล้ว F = ผลรวม × 9 / จำนวนข้อที่คำนวณได้
  score_policy="zero"    (sensitivity): ข้อที่คำนวณไม่ได้ = 0 (ต้องมีงบปี t ก่อน)
"""

import numpy as np
import pandas as pd

SIGNALS = ["F_ROA", "F_CFO", "F_dROA", "F_ACCRUAL", "F_dLEVER", "F_dLIQUID", "F_EQ", "F_dMARGIN", "F_dTURN"]
MIN_AVAILABLE = 8
SHARE_RATIO_BOUNDS = (0.5, 2.0)  # หลังปรับ split แล้ว หุ้นเปลี่ยนเกินช่วงนี้ = ข้อมูลน่าสงสัย → F_EQ คำนวณไม่ได้


def _g(row, f):
    return np.nan if row is None else row.get(f, np.nan)


def _ltd(row, policy):
    v = _g(row, "lt_debt")
    if pd.notna(v) or row is None:
        return v, "reported" if pd.notna(v) else "no_row"
    ie = _g(row, "interest_expense")
    if policy == "zero":
        return 0.0, "assumed_zero"
    if pd.notna(ie) and ie == 0:
        return 0.0, "zero_by_evidence"
    return np.nan, "unknown_has_interest" if pd.notna(ie) else "unknown_no_interest_tag"


def _gt(a, b):
    return np.nan if pd.isna(a) or pd.isna(b) else float(a > b)


def _div(a, b):
    return np.nan if pd.isna(a) or pd.isna(b) or b == 0 else a / b


def signals(rs: dict, split_factor: float = 1.0, ltd_policy: str = "evidence") -> dict:
    """rs = {"t","t1","t2"} จาก PIT.rows_asof ; split_factor = ผลคูณ split ระหว่าง period_end ของ t1 กับ t"""
    t, t1, t2 = rs.get("t"), rs.get("t1"), rs.get("t2")
    ta_t, ta_1, ta_2 = _g(t, "total_assets"), _g(t1, "total_assets"), _g(t2, "total_assets")
    roa_t = _div(_g(t, "net_income"), ta_1)
    roa_1 = _div(_g(t1, "net_income"), ta_2)
    cfo_t = _div(_g(t, "cfo"), ta_1)
    ltd_t, st_t = _ltd(t, ltd_policy)
    ltd_1, st_1 = _ltd(t1, ltd_policy)
    lev_t = _div(ltd_t, np.nanmean([ta_t, ta_1]) if pd.notna(ta_t) and pd.notna(ta_1) else np.nan)
    lev_1 = _div(ltd_1, np.nanmean([ta_1, ta_2]) if pd.notna(ta_1) and pd.notna(ta_2) else np.nan)
    liq_t = _div(_g(t, "current_assets"), _g(t, "current_liabilities"))
    liq_1 = _div(_g(t1, "current_assets"), _g(t1, "current_liabilities"))
    sh_t, sh_1 = _g(t, "shares"), _g(t1, "shares")
    sh_1_adj = sh_1 * split_factor if pd.notna(sh_1) else np.nan
    ratio = _div(sh_t, sh_1_adj)
    gm_t = _div(_g(t, "gross_profit_any"), _g(t, "revenue"))
    gm_1 = _div(_g(t1, "gross_profit_any"), _g(t1, "revenue"))
    turn_t = _div(_g(t, "revenue"), ta_1)
    turn_1 = _div(_g(t1, "revenue"), ta_2)

    out = {
        "F_ROA": _gt(roa_t, 0),
        "F_CFO": _gt(cfo_t, 0),
        "F_dROA": _gt(roa_t, roa_1),
        "F_ACCRUAL": _gt(cfo_t, roa_t),
        "F_dLEVER": np.nan if pd.isna(lev_t) or pd.isna(lev_1) else float(lev_t < lev_1 or (lev_t == 0 and lev_1 == 0)),
        "F_dLIQUID": _gt(liq_t, liq_1),
        "F_EQ": np.nan if pd.isna(ratio) or not (SHARE_RATIO_BOUNDS[0] <= ratio <= SHARE_RATIO_BOUNDS[1])
                else float(sh_t <= sh_1_adj),
        "F_dMARGIN": _gt(gm_t, gm_1),
        "F_dTURN": _gt(turn_t, turn_1),
    }
    out["ltd_status_t"], out["ltd_status_t1"] = st_t, st_1
    out["share_ratio_adj"] = ratio
    return out


def score(sig: dict, score_policy: str = "rescale") -> tuple:
    """คืน (F, n_available) — F = NaN ถ้าใช้ไม่ได้ตามนโยบาย"""
    vals = [sig[s] for s in SIGNALS]
    n = int(sum(pd.notna(v) for v in vals))
    if score_policy == "rescale":
        return (float(np.nansum(vals)) * 9 / n if n >= MIN_AVAILABLE else np.nan), n
    if score_policy == "zero":
        return float(np.nansum(vals)), n
    raise ValueError(score_policy)
