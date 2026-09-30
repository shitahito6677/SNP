"""
ตัวคุมความเสี่ยงระดับตลาด (AUTORUN round 005) — ตัดสินใจทุกสิ้นเดือนด้วยข้อมูล ≤ วันนั้น แล้วถือน้ำหนักทั้งเดือนถัดไป

  trend    : w = 1 ถ้าราคาสิ้นเดือน > ค่าเฉลี่ย 10 เดือน (รวมเดือนปัจจุบัน) มิฉะนั้น 0                (Faber 2007)
  voltarget: w = min(1, 0.15 / ความผันผวน 63 วันทำการ (annualized))                                   (Moreira & Muir 2017)
  ddstop   : w = 0 ถ้า drawdown จากจุดสูงสุด 12 เดือน ≤ −15% และราคา < ค่าเฉลี่ย 10 เดือน มิฉะนั้น 1
ส่วนที่ไม่ลงทุน = เงินสดได้ rf; ต้นทุน = cost × |Δw| ทุกครั้งที่ปรับ
"""

import numpy as np
import pandas as pd


def weights(px: pd.Series, rule: str) -> pd.Series:
    """น้ำหนัก ณ สิ้นเดือน (index = วันทำการสุดท้ายของเดือน) คำนวณจากราคาถึงวันนั้น"""
    px = px.dropna()
    me = px.groupby([px.index.year, px.index.month]).tail(1)
    if rule == "trend":
        return (me > me.rolling(10).mean()).astype(float).where(me.rolling(10).count() == 10)
    if rule == "voltarget":
        vol = px.pct_change().rolling(63).std() * np.sqrt(252)
        return (0.15 / vol.loc[me.index]).clip(upper=1.0)
    if rule == "ddstop":
        hi = me.rolling(12, min_periods=12).max()
        sma = me.rolling(10).mean()
        w = pd.Series(1.0, index=me.index)
        w[(me / hi - 1 <= -0.15) & (me < sma)] = 0.0
        return w.where(hi.notna() & sma.notna())
    raise ValueError(rule)


def daily_weights(px: pd.Series, rule: str) -> pd.Series:
    """น้ำหนักรายวัน: ใช้น้ำหนักที่ตัดสิน ณ สิ้นเดือนก่อนหน้า (ไม่มองอนาคต)"""
    w = weights(px, rule)
    return w.reindex(px.index).ffill().shift(1)


def apply(risky_nav: pd.Series, rule: str, rf_monthly: pd.Series, cost: float, start=None) -> pd.Series:
    nav = risky_nav.dropna()
    r = nav.pct_change()
    w = daily_weights(nav, rule).fillna(1.0)  # ก่อนมีข้อมูลพอ = ลงทุนเต็ม
    rf_d = (rf_monthly.reindex(nav.index, method="ffill") / 21).fillna(0)
    ov = w * r + (1 - w) * rf_d
    dw = w.diff().abs().fillna(0)
    ov = ov - cost * dw
    out = (1 + ov.fillna(0)).cumprod()
    if start is not None:
        out = out[out.index >= pd.Timestamp(start)]
        out = out / out.iloc[0]
    return out, w
