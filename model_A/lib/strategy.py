"""
เลือกหุ้นตามสเปก → backtest ที่ 10 และ 25 bps → ประเมินเกณฑ์ → บันทึก trial (ใช้ร่วมกันทุก round)
"""

import numpy as np
import pandas as pd

from lib import backtest as bt, criteria as cr, guard

MIN_GROUP = 10


def neutral_rank(g: pd.DataFrame, col: str) -> pd.Series:
    """percentile rank ภายในกลุ่ม SIC (กลุ่มที่มี < 10 ตัวรวมเป็น 'other')"""
    grp = g["sic_group"].where(g.groupby("sic_group")["sic_group"].transform("size") >= MIN_GROUP, "other")
    return g.groupby(grp)[col].rank(pct=True)


def select(g: pd.DataFrame, col: str, q: float = 0.2, floor: int = 50, neutral: bool = False, top: bool = True) -> list:
    """g = panel ของวันเดียว (เฉพาะ in_U); เลือก top q (ขั้นต่ำ floor ตัว) ของ col ที่มีค่า; เสมอกันเรียงด้วย yahoo"""
    c = g[g[col].notna()].drop_duplicates("yahoo").copy()
    if c.empty:
        return []
    c["_v"] = neutral_rank(c, col) if neutral else c[col]
    c = c.sort_values(["_v", "yahoo"], ascending=[not top, True])
    n = min(len(c), max(floor, int(round(q * len(c)))))
    return list(c["yahoo"].iloc[:n])


def ew_holdings(panel: pd.DataFrame) -> dict:
    u = panel[panel["in_U"]]
    return {R: sorted(g["yahoo"].unique()) for R, g in u.groupby("R")}


def run_nav(holdings: dict, adj: pd.DataFrame, cost: float) -> pd.Series:
    return bt.run(holdings, adj, guard.CUTOFF, cost=cost)["nav"]


def evaluate_trial(trial_id, round_, family, spec, holdings, ew_hold, ctx, evaluator, notes="", ew_cache=None) -> dict:
    """คืน dict ของผล + เก็บ NAV ไว้ใช้ต่อ; ew_cache = {(freq_key, cost): nav} ใช้ซ้ำ EW"""
    adj = ctx.adj
    n10 = run_nav(holdings, adj, 0.001)
    n25 = run_nav(holdings, adj, 0.0025)
    key = tuple(sorted(ew_hold))
    if ew_cache is not None and (key, 10) in ew_cache:
        e10, e25 = ew_cache[(key, 10)], ew_cache[(key, 25)]
    else:
        e10, e25 = run_nav(ew_hold, adj, 0.001), run_nav(ew_hold, adj, 0.0025)
        if ew_cache is not None:
            ew_cache[(key, 10)], ew_cache[(key, 25)] = e10, e25
    counts = pd.Series({R: len(v) for R, v in holdings.items()})
    res = cr.evaluate(n10, e10, n25, e25, ctx.spy, ctx.rf, counts)
    res.update(round=round_, trial_id=trial_id, family=family, spec=spec, evaluator=evaluator, notes=notes)
    res["_nav10"], res["_ew10"] = n10, e10
    return res


def record(results: list) -> pd.DataFrame:
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]
    return cr.append_trials(rows)
