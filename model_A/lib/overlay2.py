"""
ตัวกรองแนวโน้มระดับตลาด (EXPLORE2 T1 / PREREG_OVERLAY.md)
  A (Faber): สิ้นเดือน ราคา < SMA 10 เดือน → เงินสด
  B (TSMOM): ผลตอบแทน 12 เดือน − ผลตอบแทนเงินสดสะสม 12 เดือน < 0 → เงินสด
เงินสดได้ ^IRX; ต้นทุน cost × |Δw|; ตัดสินสิ้นเดือน ถือทั้งเดือนถัดไป (ไม่มองอนาคต)
"""
import numpy as np
import pandas as pd

from lib import guard
from lib.paths import PRICES_DIR


def irx_monthly() -> pd.Series:
    s = guard.clip(pd.read_parquet(PRICES_DIR / "irx_long.parquet")["^IRX"].dropna())
    m = s.resample("ME").last()
    return (m.shift(1) / 100 / 12).fillna(0)  # ผลตอบแทนเงินสดของเดือนนั้น (อัตรา ณ สิ้นเดือนก่อน)


def weights_monthly(px: pd.Series, rule: str, rf_m: pd.Series, n: int = None) -> pd.Series:
    me = px.dropna().resample("ME").last().dropna()
    if rule == "A":
        k = n or 10
        sma = me.rolling(k).mean()
        return (me >= sma).astype(float).where(sma.notna())
    if rule == "B":
        k = n or 12
        ret = me / me.shift(k) - 1
        rfc = (1 + rf_m.reindex(me.index).fillna(0)).rolling(k).apply(np.prod, raw=True) - 1
        return ((ret - rfc) >= 0).astype(float).where(ret.notna())
    raise ValueError(rule)


def apply(px: pd.Series, rule: str, cost: float = 0.001, n: int = None):
    """คืน (nav รายวันของ overlay, nav buy-and-hold, น้ำหนักรายเดือน)"""
    px = px.dropna()
    rf_m = irx_monthly()
    w_m = weights_monthly(px, rule, rf_m, n)
    # น้ำหนักรายวัน = น้ำหนักที่ตัดสิน ณ สิ้นเดือนก่อนหน้า
    w_d = w_m.reindex(px.index, method="ffill").shift(1)
    first_me = px.groupby([px.index.year, px.index.month]).tail(1).index
    w_d = w_d.where(w_d.notna(), 1.0)
    rf_d = rf_m.reindex(px.index, method="ffill").fillna(0) / px.groupby([px.index.year, px.index.month]).transform("size")
    r = px.pct_change().fillna(0)
    ov = w_d * r + (1 - w_d) * rf_d - cost * w_d.diff().abs().fillna(0)
    return (1 + ov).cumprod(), px / px.iloc[0], w_m


def stats(nav: pd.Series, rf_m: pd.Series) -> dict:
    m = nav.resample("ME").last().pct_change().dropna()
    ex = m - rf_m.reindex(m.index).fillna(0)
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    return {"CAGR": (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1, "Sharpe": ex.mean() / ex.std() * np.sqrt(12),
            "MaxDD": float((nav / nav.cummax() - 1).min()), "years": yrs}
