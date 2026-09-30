"""Round 005 runner — ตระกูล E (สเปกใน HYPOTHESIS.md) — python3 -m rounds.round_005.run"""
import numpy as np
import pandas as pd

from lib import criteria as cr, guard, overlay as ov, panel, s5, strategy as st
from lib.paths import INTERIM, MODEL_A

ROUND = "005"


def main():
    ctx = panel.Ctx()
    dfm = panel.build(panel.rebalance_dates(ctx, "M"), ctx, "monthly")
    ew_hold = st.ew_holdings(dfm)
    ew10, ew25 = st.run_nav(ew_hold, ctx.adj, 0.001), st.run_nav(ew_hold, ctx.adj, 0.0025)
    n_u = pd.Series({R: len(v) for R, v in ew_hold.items()})
    n_sp = dfm.groupby("R").size()  # จำนวนสมาชิก S&P 500 ณ วันนั้น
    spy = ctx.spy.loc["2011-06-30":guard.CUTOFF]
    res, s5rows = [], []
    for asset, (r10, r25, counts) in {"SPY": (spy, spy, n_sp), "EW": (ew10, ew25, n_u)}.items():
        for rule in ["trend", "voltarget", "ddstop"]:
            # คำนวณน้ำหนักจากประวัติเต็มก่อน 2011-06 (SPY มีตั้งแต่ 2008) เพื่อให้มีค่าเฉลี่ย 10 เดือนตั้งแต่ต้น
            base10 = ctx.spy.loc[:guard.CUTOFF] if asset == "SPY" else r10
            base25 = ctx.spy.loc[:guard.CUTOFF] if asset == "SPY" else r25
            n10, w = ov.apply(base10, rule, ctx.rf, 0.001, start="2011-06-30")
            n25, _ = ov.apply(base25, rule, ctx.rf, 0.0025, start="2011-06-30")
            wm = w.reindex(counts.index, method="ffill").fillna(1.0)
            cnt = counts * (wm > 0)
            e = cr.evaluate(n10, ew10, n25, ew25, ctx.spy, ctx.rf, cnt.loc[:"2023-05-31"])
            tid = f"r{ROUND}_{rule}_{asset}"
            e.update(round=ROUND, trial_id=tid, family="E:overlay", spec={"rule": rule, "asset": asset},
                     evaluator="rounds/round_005/run.py", notes=f"share of months fully in cash: {(wm == 0).mean():.3f}")
            e["_nav10"] = n10
            res.append(e)
            chk = s5.overlay_check(lambda s, r=rule: ov.daily_weights(s, r).fillna(1.0))
            chk["trial_id"] = tid
            s5rows.append(chk)
            print(tid, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    s5df = pd.concat(s5rows, ignore_index=True)
    s5df.to_csv(MODEL_A / "rounds" / "round_005" / "s5_indices.csv", index=False)
    out["S5_better_count"] = [int(s5df[s5df.trial_id == i].better.sum()) for i in out.trial_id]
    out.to_csv(MODEL_A / "rounds" / "round_005" / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res} | {"EW_M": ew10.loc["2011-06-30":] / ew10.loc["2011-06-30":].iloc[0], "SPY": spy / spy.iloc[0]}, axis=1).to_parquet(INTERIM / "r005_nav.parquet")
    cols = ["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew",
            "S1_10", "S1_25", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "S5_better_count", "info_sharpe", "info_sharpe_ew", "notes"]
    pd.set_option("display.width", 250)
    print(out[cols].round(3).to_string())
    print(s5df.round(3).to_string())
    ok = lambda c: out[c].astype(str).str.lower().eq("true")
    print("CANDIDATES:", list(out[ok("S1") & ok("S2") & ok("S3") & ok("S6")]["trial_id"]))


if __name__ == "__main__":
    main()
