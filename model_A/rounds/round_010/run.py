"""Round 010 runner — T5 value+momentum+quality (HYPOTHESIS.md) — python3 -m rounds.round_010.run"""
import pandas as pd

from lib import criteria as cr, panel, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_002.run import composite
from rounds.round_003.run import monthly_universe

ROUND = "010"


def main():
    ctx = panel.Ctx()
    dfm, um = monthly_universe(ctx)
    res = []
    for freq in ("A", "Q"):
        dates = panel.rebalance_dates(ctx, freq)
        u = um[um["R"].isin(dates)].drop_duplicates(["R", "yahoo"])
        ew = {R: sorted(g["yahoo"]) for R, g in u.groupby("R")}
        hold = {}
        for R, g in u.groupby("R"):
            g = g.copy()
            g["_c"] = composite(g, [["Q_LOWACC"], ["V_EP"], ["C_MOM"]], True)
            hold[R] = st.select(g, "_c", 0.2, 50)
        spec = {"signals": ["Q_LOWACC", "V_EP", "C_MOM"], "rank": "sector", "q": 0.2, "floor": 50, "freq": freq, "weight": "EW"}
        res.append(st.evaluate_trial(f"r{ROUND}_VMQ_sector_{freq}", ROUND, "T5:value_mom_quality", spec, hold, ew, ctx, "rounds/round_010/run.py"))
        print(freq, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(MODEL_A / "rounds" / "round_010" / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res}, axis=1).to_parquet(INTERIM / "r010_nav.parquet")
    pd.set_option("display.width", 250)
    print(out[["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew", "S1", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew"]].round(3).to_string())


if __name__ == "__main__":
    main()
