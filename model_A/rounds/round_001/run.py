"""Round 001 runner — ตระกูล A สัญญาณเดี่ยว (สเปกใน HYPOTHESIS.md) — รันจาก model_A: python3 -m rounds.round_001.run"""
import json
import pandas as pd

from lib import criteria as cr, panel, strategy as st
from lib.paths import INTERIM, MODEL_A

ROUND = "001"
SIGNALS = ["Q_GPA", "Q_ROIC", "Q_LOWACC", "V_BM", "V_EP", "V_EBITEV", "V_FCFP", "I_LOWISS", "I_LOWAG",
           "A_FSCORE", "A_GSCORE", "A_ALTMANZ", "A_SHY", "A_STAB", "A_LOWLEV"]
FILTERS = {"F_ALTMAN": lambda g: g["A_ALTMANZ"] < 1.81,
           "F_BENEISH": lambda g: g["A_BENEISHM"] > -1.78,
           "F_BOTH": lambda g: (g["A_ALTMANZ"] < 1.81) | (g["A_BENEISHM"] > -1.78)}


def main():
    ctx = panel.Ctx()
    df = panel.build(panel.rebalance_dates(ctx, "A"), ctx, "annual")
    u = df[df["in_U"]]
    ew = st.ew_holdings(df)
    cache, res = {}, []
    for sig in SIGNALS:
        for neutral in (False, True):
            hold = {R: st.select(g, sig, 0.2, 50, neutral) for R, g in u.groupby("R")}
            spec = {"signal": sig, "rank": "sector" if neutral else "overall", "q": 0.2, "floor": 50, "freq": "A", "weight": "EW"}
            tid = f"r{ROUND}_{sig}_{spec['rank']}"
            res.append(st.evaluate_trial(tid, ROUND, "A:single", spec, hold, ew, ctx, "rounds/round_001/run.py", ew_cache=cache))
            print(tid, "done", flush=True)
    for name, flag in FILTERS.items():
        hold = {R: sorted(g.loc[~flag(g).fillna(False), "yahoo"].unique()) for R, g in u.groupby("R")}
        spec = {"filter": name, "freq": "A", "weight": "EW"}
        tid = f"r{ROUND}_{name}"
        res.append(st.evaluate_trial(tid, ROUND, "A:filter", spec, hold, ew, ctx, "rounds/round_001/run.py", ew_cache=cache))
        print(tid, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"] = [x["DSR"] for x in s3]
    out["S3"] = [x["S3"] for x in s3]
    out["N_trials"] = len(t)
    out.to_csv(MODEL_A / "rounds" / "round_001" / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res} | {"EW": res[0]["_ew10"]}, axis=1).to_parquet(INTERIM / "r001_nav.parquet")
    cols = ["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew",
            "S1_10", "S1_25", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew"]
    pd.set_option("display.width", 250)
    print(out[cols].round(3).to_string())
    cand = out[out["S1"].astype(bool) & out["S2"].astype(bool) & out["S3"].astype(bool) & out["S6"].astype(bool)]
    print("CANDIDATES:", list(cand["trial_id"]))


if __name__ == "__main__":
    main()
