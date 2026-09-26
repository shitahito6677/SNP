"""Round 002 runner — ตระกูล B คะแนนรวม (สเปกใน HYPOTHESIS.md) — python3 -m rounds.round_002.run"""
import numpy as np
import pandas as pd

from lib import criteria as cr, panel, strategy as st
from lib.paths import INTERIM, MODEL_A

ROUND = "002"
Q = ["Q_GPA", "Q_ROIC", "Q_LOWACC"]
V = ["V_BM", "V_EP", "V_EBITEV", "V_FCFP"]
SAFE = ["A_LOWLEV", "A_STAB", "A_ALTMANZ"]
INV = ["I_LOWISS", "I_LOWAG"]
COMPOSITES = {"B_QV": [Q, V], "B_QUAL": [Q, SAFE], "B_FV": [["A_FSCORE"], V], "B_SHYQ": [["A_SHY"], Q], "B_QVI": [Q, V, INV]}


def pillar_scores(g: pd.DataFrame, pillars, neutral: bool) -> pd.DataFrame:
    out = pd.DataFrame(index=g.index)
    for i, cols in enumerate(pillars):
        ranks = pd.concat([(st.neutral_rank(g[g[c].notna()], c) if neutral else g[c].rank(pct=True)).rename(c) for c in cols], axis=1)
        out[f"p{i}"] = ranks.reindex(g.index).mean(axis=1)
    return out


def composite(g, pillars, neutral):
    p = pillar_scores(g, pillars, neutral)
    return p.mean(axis=1).where(p.notna().all(axis=1))


def main():
    ctx = panel.Ctx()
    df = panel.build(panel.rebalance_dates(ctx, "A"), ctx, "annual")
    u = df[df["in_U"]].drop_duplicates(["R", "yahoo"])
    ew = st.ew_holdings(df)
    cache, res = {}, []
    for name in list(COMPOSITES) + ["B_QARP"]:
        for neutral in (False, True):
            hold = {}
            for R, g in u.groupby("R"):
                g = g.copy()
                if name == "B_QARP":
                    ql = composite(g, [Q, SAFE], neutral)
                    val = composite(g, [V], neutral)
                    both = g[ql.notna() & val.notna()]
                    n = min(len(both), max(50, int(round(0.2 * len(both)))))
                    pool = both[ql.loc[both.index] >= ql.loc[both.index].median()].copy()
                    pool["_v"] = val.loc[pool.index]
                    hold[R] = list(pool.sort_values(["_v", "yahoo"], ascending=[False, True])["yahoo"].iloc[:n])
                else:
                    g["_c"] = composite(g, COMPOSITES[name], neutral)
                    hold[R] = st.select(g, "_c", 0.2, 50, neutral=False)
            spec = {"composite": name, "rank": "sector" if neutral else "overall", "q": 0.2, "floor": 50, "freq": "A", "weight": "EW"}
            tid = f"r{ROUND}_{name}_{spec['rank']}"
            res.append(st.evaluate_trial(tid, ROUND, "B:composite", spec, hold, ew, ctx, "rounds/round_002/run.py", ew_cache=cache))
            print(tid, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(MODEL_A / "rounds" / "round_002" / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res} | {"EW": res[0]["_ew10"]}, axis=1).to_parquet(INTERIM / "r002_nav.parquet")
    cols = ["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew",
            "S1_10", "S1_25", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew"]
    pd.set_option("display.width", 250)
    print(out[cols].round(3).to_string())
    ok = lambda c: out[c].astype(str).str.lower().eq("true")
    print("CANDIDATES:", list(out[ok("S1") & ok("S2") & ok("S3") & ok("S6")]["trial_id"]))


if __name__ == "__main__":
    main()
