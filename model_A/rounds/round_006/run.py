"""Round 006 runner — ตระกูล F ML baseline (สเปกใน HYPOTHESIS.md) — python3 -m rounds.round_006.run"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.tree import DecisionTreeRegressor, export_text

from lib import criteria as cr, guard, panel, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_003.run import monthly_universe

ROUND = "006"
FEATS = ["Q_GPA", "Q_ROIC", "Q_LOWACC", "V_BM", "V_EP", "V_EBITEV", "V_FCFP", "I_LOWISS", "I_LOWAG", "A_FSCORE", "A_GSCORE",
         "A_ALTMANZ", "A_SHY", "A_STAB", "A_LOWLEV", "C_MOM", "C_LOWVOL", "C_TREND", "C_HI52"]


def forward_12m(adj, u):
    us = adj["SPY"].dropna().index
    px = adj.loc[us]
    out = []
    for R, g in u.groupby("R"):
        end = R + pd.DateOffset(months=12)
        if end > guard.CUTOFF:
            continue
        i0 = px.index.searchsorted(R, side="right") - 1
        i1 = px.index.searchsorted(end, side="right") - 1
        names = [y for y in g["yahoo"] if y in px.columns]
        seg = px[names].iloc[i0:i1 + 1].ffill()
        f = seg.iloc[-1] / seg.iloc[0] - 1
        out.append(pd.DataFrame({"R": R, "yahoo": f.index, "fwd12": f.values}))
    return pd.concat(out, ignore_index=True)


def main():
    ctx = panel.Ctx()
    dfm, u = monthly_universe(ctx)
    X = u[["R", "yahoo", "sic_group"] + FEATS].copy()
    for c in FEATS:
        X[c] = X.groupby("R")[c].rank(pct=True).fillna(0.5)
    fw = forward_12m(ctx.adj, u)
    fw["y"] = fw.groupby("R")["fwd12"].rank(pct=True)
    data = X.merge(fw[["R", "yahoo", "y"]], on=["R", "yahoo"], how="left")
    annual = panel.rebalance_dates(ctx, "A")
    ew = {R: v for R, v in st.ew_holdings(dfm).items() if R in set(annual)}
    hold = {"F_GBM": {}, "F_TREE2": {}}
    rules = []
    for R in annual:
        g = data[data["R"] == R].drop_duplicates("yahoo")
        train = data[(data["R"] + pd.DateOffset(months=12) <= R) & data["y"].notna()]
        if train["R"].nunique() < 12:
            for k in hold:
                hold[k][R] = sorted(g["yahoo"])  # ยังไม่มีข้อมูลเทรนพอ → EW(U) (ประกาศใน HYPOTHESIS)
            continue
        n = min(len(g), max(50, int(round(0.2 * len(g)))))
        gbm = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, random_state=42).fit(train[FEATS], train["y"])
        p = pd.Series(gbm.predict(g[FEATS]), index=g["yahoo"].values)
        hold["F_GBM"][R] = list(p.sort_values(ascending=False).index[:n])
        tree = DecisionTreeRegressor(max_depth=2, min_samples_leaf=200, random_state=42).fit(train[FEATS], train["y"])
        tp = pd.DataFrame({"yahoo": g["yahoo"].values, "p": tree.predict(g[FEATS])}).sort_values(["p", "yahoo"], ascending=[False, True])
        hold["F_TREE2"][R] = list(tp["yahoo"].iloc[:n])
        rules.append(f"=== {R.date()} (train months {train['R'].nunique()}, rows {len(train)}) ===\n" + export_text(tree, feature_names=FEATS, decimals=3))
    (MODEL_A / "rounds" / "round_006" / "tree_rules.txt").write_text("\n".join(rules))
    cache, res = {}, []
    for k, h in hold.items():
        spec = {"model": k, "q": 0.2, "floor": 50, "freq": "A", "features": FEATS, "walk_forward": "expanding, label-realized"}
        res.append(st.evaluate_trial(f"r{ROUND}_{k}", ROUND, "F:ml", spec, h, ew, ctx, "rounds/round_006/run.py", ew_cache=cache))
        print(k, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(MODEL_A / "rounds" / "round_006" / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res} | {"EW": res[0]["_ew10"]}, axis=1).to_parquet(INTERIM / "r006_nav.parquet")
    cols = ["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew",
            "S1_10", "S1_25", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew"]
    pd.set_option("display.width", 250)
    print(out[cols].round(3).to_string())
    ok = lambda c: out[c].astype(str).str.lower().eq("true")
    print("CANDIDATES:", list(out[ok("S1") & ok("S2") & ok("S3") & ok("S6")]["trial_id"]))


if __name__ == "__main__":
    main()
