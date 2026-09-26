"""
Backtest แบบ rebalance ปีละครั้ง, equal-weight, buy-and-hold ภายในปี (PREREG v1 ข้อ 5–6)

อุปมา: ทุกสิ้น มิ.ย. แบ่งเงินใส่ "ตะกร้า" หุ้นละเท่า ๆ กัน แล้วปล่อยไว้ทั้งปี ตะกร้าไหนหุ้นหายจากตลาด (ถูกซื้อ/delist)
ก็เก็บเป็นเงินสดไว้จนถึงรอบถัดไป ปลายปีเทตะกร้าแล้วจัดใหม่ เสียค่าธรรมเนียมตามปริมาณที่ต้องซื้อขาย
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.optimize import brentq

COST_PER_SIDE = 0.001  # 10 bps


def run(holdings: dict, adj: pd.DataFrame, end: pd.Timestamp, cost: float = COST_PER_SIDE) -> dict:
    """holdings: {R: [yahoo,...]} ; คืน nav (daily Series), turnover/n ต่อรอบ, fwd (ผลตอบแทนต่อหุ้นต่อรอบ)"""
    Rs = sorted(holdings)
    assert adj.index.max() <= end, "โหลดราคาเกินวันสิ้นสุดที่อนุญาต (held-out guard)"
    nav_parts, stats, fwd_rows = [], [], []
    value, w_old = 1.0, {}
    for k, R in enumerate(Rs):
        stop = Rs[k + 1] if k + 1 < len(Rs) else end
        names = holdings[R]
        n = len(names)
        w_new = {y: 1.0 / n for y in names} if n else {}
        turnover = sum(abs(w_new.get(y, 0) - w_old.get(y, 0)) for y in set(w_new) | set(w_old))
        if not w_old:
            turnover = sum(w_new.values())  # ซื้อครั้งแรกจากเงินสด
        value *= (1 - cost * turnover)
        if n == 0:
            idx = adj.loc[R:stop].index
            nav_parts.append(pd.Series(value, index=idx))
            stats.append({"R": R, "n": 0, "turnover": turnover})
            w_old = {}
            continue
        entry = adj.loc[:R, names].ffill().iloc[-1]
        assert entry.notna().all(), f"{R}: ไม่มีราคาเข้าของ {list(entry[entry.isna()].index)}"
        px = adj.loc[R:stop, names].ffill()
        px.loc[R] = entry  # กรณี R ไม่มีข้อมูลของบางตัว (ใช้ราคาล่าสุด ≤ R)
        rel = px / entry
        path = value * rel.mean(axis=1)
        nav_parts.append(path)
        end_rel = rel.iloc[-1]
        w_old = (end_rel / end_rel.sum()).to_dict()
        fwd_rows += [{"R": R, "yahoo": y, "fwd": float(end_rel[y] - 1)} for y in names]
        value = float(path.iloc[-1])
        stats.append({"R": R, "n": n, "turnover": turnover})
    nav = pd.concat(nav_parts)
    nav = nav[~nav.index.duplicated(keep="last")]
    return {"nav": nav, "stats": pd.DataFrame(stats), "fwd": pd.DataFrame(fwd_rows)}


def monthly(series: pd.Series) -> pd.Series:
    m = series.resample("ME").last()
    return m.pct_change().dropna()


def window(r: pd.Series, start, end) -> pd.Series:
    """ผลตอบแทนรายเดือนของเดือนที่สิ้นสุดใน (start, end] — start/end = วัน rebalance"""
    return r[(r.index > pd.Timestamp(start) + pd.offsets.MonthEnd(0)) & (r.index <= pd.Timestamp(end) + pd.offsets.MonthEnd(0))]


def metrics(r: pd.Series, rf: pd.Series, daily: pd.Series = None) -> dict:
    ex = r - rf.reindex(r.index).fillna(0)
    T = len(r)
    out = {
        "months": T,
        "CAGR": (1 + r).prod() ** (12 / T) - 1 if T else np.nan,
        "vol": r.std() * np.sqrt(12),
        "Sharpe": ex.mean() * 12 / (ex.std() * np.sqrt(12)) if ex.std() > 0 else np.nan,
    }
    if daily is not None and len(daily):
        d = daily / daily.iloc[0]
        out["maxDD"] = float((d / d.cummax() - 1).min())
    return out


def nw_tstat(x: pd.Series) -> tuple:
    """Newey-West t-stat ของค่าเฉลี่ย (lag = floor(4 (T/100)^(2/9)) ตาม PREREG)"""
    x = x.dropna()
    lag = int(np.floor(4 * (len(x) / 100) ** (2 / 9)))
    res = sm.OLS(x.values, np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lag})
    return float(res.tvalues[0]), lag


def dca(daily_nav: pd.Series, start, end) -> dict:
    """เติมเงิน 1 หน่วยทุกวันทำการแรกของเดือนใน (start, end] ซื้อที่ NAV วันนั้น → final/invested และ IRR ต่อปี"""
    nav = daily_nav[(daily_nav.index > pd.Timestamp(start)) & (daily_nav.index <= pd.Timestamp(end))]
    buys = nav.groupby([nav.index.year, nav.index.month]).head(1)
    units = (1.0 / buys).sum()
    final = units * nav.iloc[-1]
    invested = len(buys)
    t = np.array([(d - buys.index[0]).days / 365.25 for d in buys.index])
    T_end = (nav.index[-1] - buys.index[0]).days / 365.25
    f = lambda r: sum((1 + r) ** (T_end - ti) for ti in t) - final
    irr = brentq(f, -0.99, 5.0)
    return {"dca_final_over_invested": final / invested, "dca_IRR": irr, "lumpsum_multiple": nav.iloc[-1] / daily_nav[daily_nav.index <= pd.Timestamp(start)].iloc[-1]}
