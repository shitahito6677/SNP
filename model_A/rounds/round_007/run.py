"""Round 007 runner — universe top-1500 (สเปกใน HYPOTHESIS.md) — python3 -m rounds.round_007.run"""
import pandas as pd

from lib import criteria as cr, panel, panel1500 as p15, signals_price as sp, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_002.run import composite, Q, V, SAFE

ROUND = "007"
SINGLES = ["Q_GPA", "Q_ROIC", "Q_LOWACC", "V_BM", "V_EP", "V_EBITEV", "V_FCFP", "I_LOWISS", "I_LOWAG",
           "A_FSCORE", "A_GSCORE", "A_ALTMANZ", "A_SHY", "A_STAB", "A_LOWLEV"]
COMPS = {"B_QV": [Q, V], "B_QUAL": [Q, SAFE], "B_SHYQ": [["A_SHY"], Q]}
PRICE = ["C_MOM", "C_LOWVOL"]


def holdings(u, name):
    hold = {}
    for R, g in u.groupby("R"):
        g = g.copy()
        if name in COMPS:
            g["_c"] = composite(g, COMPS[name], False)
            hold[R] = st.select(g, "_c", 0.2, 50)
        else:
            hold[R] = st.select(g, name, 0.2, 50)
    return hold


def with_price(u, adj):
    ps = sp.compute(adj, sorted(u["R"].unique()), u["yahoo"].unique())
    return u.merge(ps, on=["R", "yahoo"], how="left")


def eval50(res, hold, ew, ctx):
    n50, e50 = st.run_nav(hold, ctx.adj, 0.005), st.run_nav(ew, ctx.adj, 0.005)
    d, e, s = (cr.win_metrics(x, ctx.rf, cr.DEC) for x in (n50, e50, ctx.spy))
    res["dec50_sharpe"], res["dec50_sharpe_ew"], res["dec50_cagr"], res["dec50_cagr_ew"] = d["Sharpe"], e["Sharpe"], d["CAGR"], e["CAGR"]
    res["S1_50"] = cr.s1_check(d, e, s)
    res["S1"] = bool(res["S1_10"] and res["S1_25"] and res["S1_50"])
    res["notes"] = f"S1 needs 10/25/50 bps (DEVIATIONS); S1_50={res['S1_50']}; dec50 Sharpe {d['Sharpe']:.3f} vs EW {e['Sharpe']:.3f}"
    return res


def main():
    ctx = p15.Ctx1500()
    dates = panel.rebalance_dates(ctx, "A")
    df = p15.build(dates, ctx)
    u = with_price(df[df["in_U"].fillna(False).astype(bool)].drop_duplicates(["R", "yahoo"]), ctx.adj)
    ew = {R: sorted(g["yahoo"]) for R, g in u.groupby("R")}
    cache, res = {}, []
    for name in SINGLES + list(COMPS) + PRICE:
        hold = holdings(u, name)
        spec = {"universe": "top1500_mcap_liquid", "signal": name, "rank": "overall", "q": 0.2, "floor": 50, "freq": "A", "costs_bps": [10, 25, 50]}
        r = st.evaluate_trial(f"r{ROUND}_U1500_{name}", ROUND, "U1500", spec, hold, ew, ctx, "rounds/round_007/run.py", ew_cache=cache)
        res.append(eval50(r, hold, ew, ctx))
        print(name, "done", flush=True)
    # เทียบข้าง S&P 500 (U เดิม, panel รายปี) — C_MOM/C_LOWVOL รายปีเป็นสเปกใหม่ (นับ trial); ตัวอื่นประเมินซ้ำที่ 50 bps (ไม่นับ)
    pctx = panel.Ctx()
    dfa = panel.build(panel.rebalance_dates(pctx, "A"), pctx, "annual")
    ua = with_price(dfa[dfa["in_U"]].drop_duplicates(["R", "yahoo"]), pctx.adj)
    ewa = st.ew_holdings(dfa)
    side, cache2 = [], {}
    for name in SINGLES + list(COMPS) + PRICE:
        hold = holdings(ua, name)
        r = st.evaluate_trial(f"r{ROUND}_SP500_{name}", ROUND, "SP500_side", {"universe": "SP500", "signal": name}, hold, ewa, pctx,
                              "rounds/round_007/run.py", ew_cache=cache2)
        r = eval50(r, hold, ewa, pctx)
        side.append(r)
        if name in PRICE:
            res.append(r)
        print("SP500", name, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    extra = pd.DataFrame([{k: r[k] for k in ["trial_id", "dec50_sharpe", "dec50_sharpe_ew", "dec50_cagr", "dec50_cagr_ew", "S1_50"]} for r in res + side])
    out = out.merge(extra.drop_duplicates("trial_id"), on="trial_id", how="left")
    out.to_csv(MODEL_A / "rounds" / "round_007" / "results.csv", index=False)
    sd = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in side])
    sd.to_csv(MODEL_A / "rounds" / "round_007" / "sp500_side_by_side.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res} | {"EW_U1500": res[0]["_ew10"]}, axis=1).to_parquet(INTERIM / "r007_nav.parquet")
    cols = ["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew",
            "S1_10", "S1_25", "S1_50", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew", "dec50_sharpe", "dec50_sharpe_ew"]
    pd.set_option("display.width", 300)
    print(out[cols].round(3).to_string())
    print(sd[["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "info_sharpe", "info_sharpe_ew", "S1_10", "S1_25", "S1_50"]].round(3).to_string())
    ok = lambda c: out[c].astype(str).str.lower().eq("true")
    print("CANDIDATES:", list(out[ok("S1") & ok("S2") & ok("S3") & ok("S6")]["trial_id"]))


if __name__ == "__main__":
    main()
