"""Round 009 runner — T2 factor momentum (HYPOTHESIS.md) — python3 -m rounds.round_009.run"""
import numpy as np
import pandas as pd

from lib import backtest as bt, criteria as cr, french, panel, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_003.run import monthly_universe

ROUND = "009"
OUT = MODEL_A / "rounds" / "round_009"
SIGS = ["Q_LOWACC", "V_EP", "Q_GPA", "A_SHY", "C_MOM"]
FACT = ["SMB", "HML", "RMW", "CMA", "MOM"]


def stage1():
    rows = []
    for region in french.REGIONS:
        f = french.load(region)[FACT]
        trail = (1 + f).rolling(12).apply(np.prod, raw=True) - 1
        sel = (trail > 0).shift(1)  # ตัดสินสิ้นเดือนก่อน ใช้เดือนนี้
        fm = (f.where(sel.fillna(False).astype(bool))).mean(axis=1).fillna(0.0).where(trail.shift(1).notna().any(axis=1))
        eq = f.mean(axis=1)
        d = pd.concat([fm.rename("FMOM"), eq.rename("EQUAL")], axis=1).dropna()
        for k in ("FMOM", "EQUAL"):
            x = d[k]
            rows.append({"region": region, "series": k, "start": d.index.min().date(), "months": len(x), "mean_ann_%": x.mean() * 1200,
                         "Sharpe": x.mean() / x.std() * np.sqrt(12), "t": x.mean() / x.std() * np.sqrt(len(x))})
        diff = d["FMOM"] - d["EQUAL"]
        rows.append({"region": region, "series": "FMOM-EQUAL", "start": d.index.min().date(), "months": len(diff), "mean_ann_%": diff.mean() * 1200,
                     "Sharpe": diff.mean() / diff.std() * np.sqrt(12), "t": diff.mean() / diff.std() * np.sqrt(len(diff))})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage1_french.csv", index=False)
    return out


def stage2():
    ctx = panel.Ctx()
    dfm, um = monthly_universe(ctx)
    dates = panel.rebalance_dates(ctx, "A")
    u = um[um["R"].isin(dates)].drop_duplicates(["R", "yahoo"])
    ew = {R: sorted(g["yahoo"]) for R, g in u.groupby("R")}
    fwd = bt.run(ew, ctx.adj, st.guard.CUTOFF)["fwd"]
    uf = u.merge(fwd, on=["R", "yahoo"], how="left")
    hold, log = {}, []
    for i, R in enumerate(dates):
        g = u[u["R"] == R].copy()
        chosen = []
        if i > 0:
            prev = uf[uf["R"] == dates[i - 1]]
            for s in SIGS:
                p = prev[prev[s].notna() & prev["fwd"].notna()]
                q = pd.qcut(p[s].rank(method="first"), 5, labels=False)
                spread = p.loc[q == 4, "fwd"].mean() - p.loc[q == 0, "fwd"].mean()
                log.append({"R": R.date(), "signal": s, "prior_year_spread": spread, "used": spread > 0})
                if spread > 0:
                    chosen.append(s)
        if chosen:
            ranks = pd.concat([g[s].rank(pct=True) for s in chosen], axis=1)
            g["_c"] = ranks.mean(axis=1).where(ranks.notna().any(axis=1))
            hold[R] = st.select(g, "_c", 0.2, 50)
        else:
            hold[R] = sorted(g["yahoo"])
    pd.DataFrame(log).to_csv(OUT / "stage2_signal_selection.csv", index=False)
    spec = {"signals": SIGS, "select": "prior-year Q5-Q1 spread > 0", "rank": "overall", "q": 0.2, "floor": 50, "freq": "A", "weight": "EW"}
    r = st.evaluate_trial(f"r{ROUND}_FMOM_SIGNALS", ROUND, "T2:factor_momentum", spec, hold, ew, ctx, "rounds/round_009/run.py")
    t = st.record([r])
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(OUT / "results.csv", index=False)
    pd.concat({"r009_FMOM_SIGNALS": r["_nav10"], "EW": r["_ew10"]}, axis=1).to_parquet(INTERIM / "r009_nav.parquet")
    return out, pd.DataFrame(log)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    print(stage1().round(3).to_string())
    out, log = stage2()
    print(log.pivot(index="R", columns="signal", values="prior_year_spread").round(3).to_string())
    print(out[["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew", "S1", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew"]].round(3).to_string())
