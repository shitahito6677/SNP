"""
เกณฑ์ S1/S2/S3/S6 ตาม PREREG_AUTORUN.md + การบันทึก trial ลง model_A/trials.csv

อุปมา: เหมือนสนามสอบที่ตั้งเกณฑ์ไว้ก่อนเห็นข้อสอบ — ทุกครั้งที่ "ลองสอบ" (trial) ต้องจดไว้ ยิ่งลองมาก เกณฑ์ S3 ยิ่งเข้ม
"""

import json

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

from lib import backtest as bt
from lib.paths import MODEL_A

TRIALS = MODEL_A / "trials.csv"
INFO = (pd.Timestamp("2011-06-30"), pd.Timestamp("2017-06-30"))
DEC = (pd.Timestamp("2017-06-30"), pd.Timestamp("2023-06-30"))
EULER = 0.5772156649

COLS = ["round", "trial_id", "family", "spec", "evaluator",
        "dec_sharpe", "dec_cagr", "dec_maxdd", "dec_sharpe_ew", "dec_cagr_ew", "dec_maxdd_ew", "dec_sharpe_spy",
        "dec_active_sr_m", "dec_active_skew", "dec_active_kurt", "dec_active_ann", "dec_nw_t",
        "info_sharpe", "info_cagr", "info_sharpe_ew", "info_cagr_ew",
        "dec25_sharpe", "dec25_cagr", "dec25_maxdd", "dec25_sharpe_ew", "dec25_cagr_ew", "dec25_maxdd_ew",
        "S1_10", "S1_25", "S1", "S2_share", "S2", "S6_avg_n", "S6_min_n", "S6", "notes"]


def win_metrics(nav: pd.Series, rf: pd.Series, w) -> dict:
    r = bt.window(bt.monthly(nav), *w)
    d = nav[(nav.index >= w[0]) & (nav.index <= w[1])]
    return bt.metrics(r, rf, d) | {"r": r}


def s1_check(m, ew, spy) -> bool:
    return bool(m["Sharpe"] >= ew["Sharpe"] + 0.15 and m["Sharpe"] >= spy["Sharpe"] + 0.15
                and m["CAGR"] >= ew["CAGR"] + 0.02 and m["maxDD"] >= ew["maxDD"] - 0.05)


def s2_share(r: pd.Series, r_ew: pd.Series, window: int = 36) -> float:
    a = (1 + r).rolling(window).apply(np.prod, raw=True)
    b = (1 + r_ew).rolling(window).apply(np.prod, raw=True)
    m = pd.concat([a, b], axis=1).dropna()
    return float((m.iloc[:, 0] > m.iloc[:, 1]).mean()) if len(m) else np.nan


def evaluate(nav10, ew10, nav25, ew25, spy, rf, counts: pd.Series) -> dict:
    """nav*/ew* = daily NAV ของกลยุทธ์/EW ที่ต้นทุน 10 และ 25 bps; counts = จำนวนหุ้นต่อรอบ (design period)"""
    d, e, s = win_metrics(nav10, rf, DEC), win_metrics(ew10, rf, DEC), win_metrics(spy, rf, DEC)
    i, ie = win_metrics(nav10, rf, INFO), win_metrics(ew10, rf, INFO)
    act = (d["r"] - e["r"]).dropna()
    out = {
        "dec_sharpe": d["Sharpe"], "dec_cagr": d["CAGR"], "dec_maxdd": d["maxDD"],
        "dec_sharpe_ew": e["Sharpe"], "dec_cagr_ew": e["CAGR"], "dec_maxdd_ew": e["maxDD"], "dec_sharpe_spy": s["Sharpe"],
        "dec_active_sr_m": act.mean() / act.std(), "dec_active_skew": float(skew(act)),
        "dec_active_kurt": float(kurtosis(act, fisher=False)), "dec_active_ann": act.mean() * 12,
        "dec_nw_t": bt.nw_tstat(act)[0],
        "info_sharpe": i["Sharpe"], "info_cagr": i["CAGR"], "info_sharpe_ew": ie["Sharpe"], "info_cagr_ew": ie["CAGR"],
    }
    out["S1_10"] = s1_check(d, e, s)
    if nav25 is not None:
        d25, e25 = win_metrics(nav25, rf, DEC), win_metrics(ew25, rf, DEC)
        out.update({"dec25_sharpe": d25["Sharpe"], "dec25_cagr": d25["CAGR"], "dec25_maxdd": d25["maxDD"],
                    "dec25_sharpe_ew": e25["Sharpe"], "dec25_cagr_ew": e25["CAGR"], "dec25_maxdd_ew": e25["maxDD"]})
        out["S1_25"] = s1_check(d25, e25, s)
    else:
        out["S1_25"] = False
    out["S1"] = out["S1_10"] and out["S1_25"]
    out["S2_share"] = s2_share(d["r"], e["r"])
    out["S2"] = bool(out["S2_share"] >= 0.70)
    out["S6_avg_n"], out["S6_min_n"] = float(counts.mean()), int(counts.min())
    out["S6"] = bool(out["S6_avg_n"] >= 30 and out["S6_min_n"] >= 20)
    return out


def dsr(sr_hat: float, T: int, g3: float, g4: float, N: int, V: float) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado 2014) — ค่าทั้งหมดเป็นหน่วยรายเดือน"""
    if N < 2 or not np.isfinite(V) or V <= 0:
        return np.nan
    sr0 = np.sqrt(V) * ((1 - EULER) * norm.ppf(1 - 1 / N) + EULER * norm.ppf(1 - 1 / (N * np.e)))
    den = np.sqrt(max(1 - g3 * sr_hat + (g4 - 1) / 4 * sr_hat ** 2, 1e-12))
    return float(norm.cdf((sr_hat - sr0) * np.sqrt(T - 1) / den))


def load_trials() -> pd.DataFrame:
    return pd.read_csv(TRIALS) if TRIALS.exists() else pd.DataFrame(columns=COLS)


def append_trials(rows: list) -> pd.DataFrame:
    t = load_trials()
    new = pd.DataFrame(rows)
    for c in COLS:
        if c not in new:
            new[c] = np.nan
    new["spec"] = new["spec"].apply(lambda x: x if isinstance(x, str) else json.dumps(x, sort_keys=True))
    dup = set(t["trial_id"]) & set(new["trial_id"])
    assert not dup, f"trial_id ซ้ำ: {sorted(dup)[:5]}"
    t = pd.concat([t, new[COLS]], ignore_index=True)
    t.to_csv(TRIALS, index=False)
    return t


def s3_for(trial_id: str, trials: pd.DataFrame = None, T: int = 72) -> dict:
    """DSR ของ trial ที่ระบุ ใช้ N = จำนวน trial สะสมทั้งหมดใน trials.csv และ V = ความแปรปรวนของ active SR ข้าม trial"""
    t = load_trials() if trials is None else trials
    row = t[t["trial_id"] == trial_id].iloc[0]
    sr = t["dec_active_sr_m"].astype(float).dropna()
    val = dsr(float(row["dec_active_sr_m"]), T, float(row["dec_active_skew"]), float(row["dec_active_kurt"]),
              len(t), float(sr.var(ddof=1)))
    return {"DSR": val, "N": len(t), "V": float(sr.var(ddof=1)), "S3": bool(val >= 0.95) if pd.notna(val) else False}
