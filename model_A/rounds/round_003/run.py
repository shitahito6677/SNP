"""Round 003 runner — ตระกูล C (สเปกใน HYPOTHESIS.md) — python3 -m rounds.round_003.run"""
import pandas as pd

from lib import criteria as cr, panel, signals_price as sp, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_002.run import composite

ROUND = "003"
Q = ["Q_GPA", "Q_ROIC", "Q_LOWACC"]
V = ["V_BM", "V_EP", "V_EBITEV", "V_FCFP"]
SINGLE = ["C_MOM", "C_LOWVOL", "C_TREND", "C_HI52"]
COMBOS = {"C_QMOM": [Q, ["C_MOM"]], "C_SHYQMOM": [["A_SHY"], Q, ["C_MOM"]],
          "C_QLOWVOL": [Q, ["C_LOWVOL"]], "C_VMOM": [V, ["C_MOM"]]}


def monthly_universe(ctx):
    df = panel.build(panel.rebalance_dates(ctx, "M"), ctx, "monthly")
    u = df[df["in_U"]].drop_duplicates(["R", "yahoo"])
    p = INTERIM / "price_signals_monthly.parquet"
    if p.exists():
        ps = pd.read_parquet(p)
    else:
        ps = sp.compute(ctx.adj, sorted(u["R"].unique()), u["yahoo"].unique())
        ps.to_parquet(p, index=False)
    return df, u.merge(ps, on=["R", "yahoo"], how="left")


def main():
    ctx = panel.Ctx()
    df, u = monthly_universe(ctx)
    ew = st.ew_holdings(df)
    cache, res = {}, []
    for name in SINGLE + list(COMBOS):
        for neutral in (False, True):
            hold = {}
            for R, g in u.groupby("R"):
                if name in SINGLE:
                    hold[R] = st.select(g, name, 0.2, 50, neutral)
                else:
                    g = g.copy()
                    g["_c"] = composite(g, COMBOS[name], neutral)
                    hold[R] = st.select(g, "_c", 0.2, 50, neutral=False)
            spec = {"signal": name, "rank": "sector" if neutral else "overall", "q": 0.2, "floor": 50, "freq": "M", "weight": "EW"}
            tid = f"r{ROUND}_{name}_{spec['rank']}"
            res.append(st.evaluate_trial(tid, ROUND, "C:price" if name in SINGLE else "C:fund_x_price", spec, hold, ew, ctx,
                                         "rounds/round_003/run.py", ew_cache=cache))
            print(tid, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(MODEL_A / "rounds" / "round_003" / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res} | {"EW_M": res[0]["_ew10"]}, axis=1).to_parquet(INTERIM / "r003_nav.parquet")
    cols = ["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew",
            "S1_10", "S1_25", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew"]
    pd.set_option("display.width", 250)
    print(out[cols].round(3).to_string())
    ok = lambda c: out[c].astype(str).str.lower().eq("true")
    print("CANDIDATES:", list(out[ok("S1") & ok("S2") & ok("S3") & ok("S6")]["trial_id"]))


if __name__ == "__main__":
    main()
