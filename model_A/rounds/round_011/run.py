"""Round 011 runner — T3 opportunistic insider buying (HYPOTHESIS.md) — python3 -m rounds.round_011.run"""
import numpy as np
import pandas as pd

from lib import criteria as cr, panel, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_003.run import monthly_universe

ROUND = "011"
OUT = MODEL_A / "rounds" / "round_011"


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """คืน (insider, year) → routine/opportunistic ตาม CMP 2012 (ใช้เฉพาะรายการ P/S)"""
    t = df[df["TRANS_CODE"].isin(["P", "S"]) & df["TRANS_DATE"].notna() & df["RPTOWNERCIK"].notna()].copy()
    t["y"], t["m"] = t["TRANS_DATE"].dt.year, t["TRANS_DATE"].dt.month
    months = t.groupby(["RPTOWNERCIK", "y"])["m"].apply(set)
    rows = []
    for (i, y) in {(i, y + 1) for (i, y) in months.index} | set(months.index):
        prev = [months.get((i, y - k)) for k in (1, 2, 3)]
        if any(p is None for p in prev):
            continue
        routine = bool(prev[0] & prev[1] & prev[2])
        rows.append({"RPTOWNERCIK": i, "y": y, "cls": "routine" if routine else "opportunistic"})
    return pd.DataFrame(rows)


def signal(df: pd.DataFrame, cls: pd.DataFrame, dates, window_m: int = 6) -> pd.DataFrame:
    b = df[(df["TRANS_CODE"] == "P") & df["TRANS_DATE"].notna()].copy()
    b["y"] = b["TRANS_DATE"].dt.year
    b = b.merge(cls, on=["RPTOWNERCIK", "y"], how="inner")
    b = b[b["cls"] == "opportunistic"]
    rows = []
    for R in dates:
        w = b[(b["FILING_DATE"] <= R) & (b["FILING_DATE"] > R - pd.DateOffset(months=window_m))]
        c = w.groupby("ISSUERCIK").size()
        rows += [{"R": R, "cik": int(k), "opp_buys": int(v)} for k, v in c.items()]
    return pd.DataFrame(rows)


def main():
    ins = pd.read_parquet(INTERIM / "insider_sp500.parquet")
    cls = classify(ins)
    ctx = panel.Ctx()
    dfm, um = monthly_universe(ctx)
    mdates = panel.rebalance_dates(ctx, "M")
    sig = signal(ins, cls, mdates)
    u = um.merge(sig, on=["R", "cik"], how="left")
    u["opp_buys"] = u["opp_buys"].fillna(0)
    cov = u.groupby("R").agg(n_U=("yahoo", "size"), n_signal=("opp_buys", lambda s: int((s > 0).sum())))
    cov.to_csv(OUT / "signal_coverage.csv")
    share_lt20 = (cov["n_signal"] < 20).mean()
    print(f"เดือนที่หุ้นมีสัญญาณ < 20 ตัว: {share_lt20:.1%}; median {cov.n_signal.median():.0f}, min {cov.n_signal.min()}, max {cov.n_signal.max()}")
    print(f"insider-year ที่จัดกลุ่มได้: {len(cls)}, opportunistic {(cls.cls == 'opportunistic').mean():.1%}")
    res = []
    # 1) สัญญาณเดี่ยว รายเดือน
    ewm = {R: sorted(g["yahoo"].unique()) for R, g in u.groupby("R")}
    hold1 = {R: sorted(g.loc[g["opp_buys"] > 0, "yahoo"].unique()) for R, g in u.groupby("R")}
    r1 = st.evaluate_trial(f"r{ROUND}_INSIDER_OPP_BUY_M", ROUND, "T3:insider", {"signal": "opportunistic P count 6m > 0", "freq": "M", "weight": "EW"},
                           hold1, ewm, ctx, "rounds/round_011/run.py", notes=f"months with <20 names: {share_lt20:.1%}")
    res.append(r1)
    # 2) tilt บน low accruals รายปี
    adates = panel.rebalance_dates(ctx, "A")
    ua = u[u["R"].isin(adates)].drop_duplicates(["R", "yahoo"])
    ewa = {R: sorted(g["yahoo"]) for R, g in ua.groupby("R")}
    hold2 = {}
    for R, g in ua.groupby("R"):
        names = st.select(g, "Q_LOWACC", 0.2, 50)
        s = g.set_index("yahoo").loc[names, "opp_buys"]
        hold2[R] = {y: (2.0 if s[y] > 0 else 1.0) for y in names}
    r2 = st.evaluate_trial(f"r{ROUND}_LOWACC_INSIDER_TILT", ROUND, "T3:insider", {"base": "r001_Q_LOWACC_overall", "tilt": "2x if opp buys 6m > 0", "freq": "A"},
                           hold2, ewa, ctx, "rounds/round_011/run.py",
                           notes=f"tilted names per rebalance: {np.mean([sum(v > 1 for v in h.values()) for h in hold2.values()]):.1f}")
    res.append(r2)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(OUT / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res}, axis=1).to_parquet(INTERIM / "r011_nav.parquet")
    pd.set_option("display.width", 250)
    print(cov.describe().round(1).to_string())
    print(out[["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew", "S1", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew", "notes"]].round(3).to_string())


if __name__ == "__main__":
    main()
