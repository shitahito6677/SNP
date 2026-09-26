"""
สัญญาณ quality / value / investment สำหรับ v2 (ค่า "สูง = ดี" เสมอ — สัญญาณที่ต่ำดีถูกกลับเครื่องหมายแล้ว)

Quality    Q_GPA       gross profit_t / total assets_t                      (Novy-Marx 2013)
           Q_ROIC      EBIT_t / (TA_t − current liabilities_t − cash_t)     (ประมาณ ROIC ด้วย capital employed; ตัวหาร ≤ 0 = ไม่ทราบ)
           Q_LOWACC    −(NI_t − CFO_t) / avg(TA_t, TA_{t-1})                (accruals ต่ำ = ดี)
Value      V_BM        equity_t / market cap_R
           V_EP        NI_t / market cap_R
           V_EBITEV    EBIT_t / EV,  EV = market cap + หนี้ระยะยาว + หนี้ระยะสั้น − เงินสด (EV ≤ 0 = ไม่ทราบ)
           V_FCFP      (CFO_t − capex_t) / market cap_R
Investment I_LOWISS    −ln(shares_t / (shares_{t-1} × split factor))       (ออกหุ้นน้อย = ดี)
           I_LOWAG     −(TA_t / TA_{t-1} − 1)                               (สินทรัพย์โตช้า = ดี)

หนี้ระยะยาวใช้นโยบายเดียวกับ v1 (= 0 เฉพาะเมื่อมีหลักฐาน interest expense = 0, นอกนั้นไม่ทราบ → V_EBITEV ไม่ทราบ)
หนี้ระยะสั้น: DebtCurrent/LongTermDebtCurrent ถ้าไม่มีใช้ ShortTermBorrowings/CommercialPaper ถ้าไม่มีทั้งหมด = 0 (สมมติฐาน ระบุใน PREREG)
"""

import numpy as np
import pandas as pd

from lib import fscore

QUALITY = ["Q_GPA", "Q_ROIC", "Q_LOWACC"]
VALUE = ["V_BM", "V_EP", "V_EBITEV", "V_FCFP"]
INVEST = ["I_LOWISS", "I_LOWAG"]
ALL = QUALITY + VALUE + INVEST


def _g(row, f):
    return np.nan if row is None else row.get(f, np.nan)


def _div(a, b):
    return np.nan if pd.isna(a) or pd.isna(b) or b == 0 else a / b


def raw(rs: dict, mcap: float, split_factor: float = 1.0) -> dict:
    t, t1 = rs.get("t"), rs.get("t1")
    ta, ta1 = _g(t, "total_assets"), _g(t1, "total_assets")
    ce = ta - _g(t, "current_liabilities") - _g(t, "cash")
    ltd, _ = fscore._ltd(t, "evidence")
    dc = _g(t, "debt_current")
    if pd.isna(dc):
        dc = _g(t, "short_borrowings")
    dc = 0.0 if pd.isna(dc) else dc
    ev = mcap + ltd + dc - _g(t, "cash") if pd.notna(mcap) else np.nan
    sh, sh1 = _g(t, "shares"), _g(t1, "shares")
    ratio = _div(sh, sh1 * split_factor if pd.notna(sh1) else np.nan)
    ok_ratio = pd.notna(ratio) and fscore.SHARE_RATIO_BOUNDS[0] <= ratio <= fscore.SHARE_RATIO_BOUNDS[1]
    avg_ta = np.nanmean([ta, ta1]) if pd.notna(ta) and pd.notna(ta1) else np.nan
    return {
        "Q_GPA": _div(_g(t, "gross_profit_any"), ta),
        "Q_ROIC": _div(_g(t, "ebit"), ce) if pd.notna(ce) and ce > 0 else np.nan,
        "Q_LOWACC": -_div(_g(t, "net_income") - _g(t, "cfo"), avg_ta),
        "V_BM": _div(_g(t, "equity"), mcap),
        "V_EP": _div(_g(t, "net_income"), mcap),
        "V_EBITEV": _div(_g(t, "ebit"), ev) if pd.notna(ev) and ev > 0 else np.nan,
        "V_FCFP": _div(_g(t, "cfo") - _g(t, "capex"), mcap),
        "I_LOWISS": -np.log(ratio) if ok_ratio else np.nan,
        "I_LOWAG": -(_div(ta, ta1) - 1) if pd.notna(_div(ta, ta1)) else np.nan,
    }


def add_signals(scores: pd.DataFrame, pit, splits, split_factor_between) -> pd.DataFrame:
    """เติมคอลัมน์สัญญาณ v2 ให้ตาราง scores ของ lib.universe (ใช้ PIT และ market cap ชุดเดียวกับ v1)"""
    out = []
    for r in scores.itertuples(index=False):
        if pd.isna(r.cik):
            out.append({k: np.nan for k in ALL})
            continue
        rs = pit.rows_asof(int(r.cik), r.R)
        sf = 1.0
        if rs["t"] is not None and rs["t1"] is not None and isinstance(r.yahoo, str):
            sf = split_factor_between(splits, r.yahoo, rs["t1"]["shares_date"], rs["t"]["shares_date"])
        out.append(raw(rs, r.mcap_R, sf) if rs["t"] is not None else {k: np.nan for k in ALL})
    return pd.concat([scores.reset_index(drop=True), pd.DataFrame(out)], axis=1)
