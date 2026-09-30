"""Round 004 runner — ตระกูล D (สเปกใน HYPOTHESIS.md) — python3 -m rounds.round_004.run"""
import numpy as np
import pandas as pd

from lib import criteria as cr, panel, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_002.run import composite
from rounds.round_003.run import Q

ROUND = "004"


def pick_bases():
    t = cr.load_trials()
    t = t[t["round"].astype(str).isin(["001", "002", "003"])]
    ok = lambda c: t[c].astype(str).str.lower().eq("true")
    b = t[ok("S6") & (t["S2_share"].astype(float) >= 0.70)].sort_values("dec_sharpe", ascending=False)
    ids = list(b["trial_id"].iloc[:2])
    assert ids == ["r001_Q_LOWACC_overall", "r003_C_SHYQMOM_overall"], ids
    return ids


def ranked(g: pd.DataFrame, base: str) -> pd.DataFrame:
    """คืนหุ้นที่มีคะแนน เรียงจากดีไปแย่ (คอลัมน์ _v)"""
    g = g.copy()
    if base == "r001_Q_LOWACC_overall":
        g["_v"] = g["Q_LOWACC"]
    else:
        g["_v"] = composite(g, [["A_SHY"], Q, ["C_MOM"]], False)
    return g[g["_v"].notna()].sort_values(["_v", "yahoo"], ascending=[False, True])


def build(u, base, variant, freq_dates, q=0.2, floor=50):
    hold, prev = {}, []
    for R in freq_dates:
        g = ranked(u[u["R"] == R], base)
        n = min(len(g), max(floor, int(round(q * len(g)))))
        if variant == "SECCAP":
            cap = max(1, int(np.floor(0.25 * n)))
            names, cnt = [], {}
            for y, grp in zip(g["yahoo"], g["sic_group"]):
                if cnt.get(grp, 0) < cap:
                    names.append(y); cnt[grp] = cnt.get(grp, 0) + 1
                if len(names) == n:
                    break
        elif variant == "BUFFER":
            top30 = list(g["yahoo"].iloc[:int(round(0.30 * len(g)))])
            keep = [y for y in prev if y in top30][:n]
            names = keep + [y for y in g["yahoo"] if y not in keep][:n - len(keep)]
        else:
            names = list(g["yahoo"].iloc[:n])
        prev = names
        if variant == "W_IV":
            sig = (-g.set_index("yahoo").loc[names, "C_LOWVOL"])
            sig = sig.fillna(sig.median())
            hold[R] = (1 / sig).to_dict()
        elif variant == "W_CAP":
            m = g.set_index("yahoo").loc[names, "mcap"]
            hold[R] = m.fillna(m.median()).to_dict()
        else:
            hold[R] = names
    return hold


def main():
    ctx = panel.Ctx()
    from rounds.round_003.run import monthly_universe
    dfm, um = monthly_universe(ctx)
    bases = pick_bases()
    base_freq = {"r001_Q_LOWACC_overall": ("A", ["S", "Q"]), "r003_C_SHYQMOM_overall": ("M", ["Q", "A"])}
    cache, res = {}, []
    for base in bases:
        f0, falts = base_freq[base]
        for variant in ["W_IV", "W_CAP", "F1", "F2", "SECCAP", "BUFFER"]:
            freq = falts[0] if variant == "F1" else falts[1] if variant == "F2" else f0
            dates = panel.rebalance_dates(ctx, freq)
            u = um[um["R"].isin(dates)]
            hold = build(u, base, variant, dates)
            ew = {R: v for R, v in st.ew_holdings(dfm).items() if R in set(dates)}
            spec = {"base": base, "variant": variant, "freq": freq, "q": 0.2, "floor": 50}
            tid = f"r{ROUND}_{base.split('_', 1)[1]}_{variant}"
            res.append(st.evaluate_trial(tid, ROUND, "D:construction", spec, hold, ew, ctx, "rounds/round_004/run.py", ew_cache=cache))
            print(tid, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(MODEL_A / "rounds" / "round_004" / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res}, axis=1).to_parquet(INTERIM / "r004_nav.parquet")
    cols = ["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew",
            "S1_10", "S1_25", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew"]
    pd.set_option("display.width", 250)
    print(out[cols].round(3).to_string())
    ok = lambda c: out[c].astype(str).str.lower().eq("true")
    print("CANDIDATES:", list(out[ok("S1") & ok("S2") & ok("S3") & ok("S6")]["trial_id"]))


if __name__ == "__main__":
    main()
