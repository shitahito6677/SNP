"""Round 012 runner — T4 Lazy Prices (HYPOTHESIS.md) — python3 -m rounds.round_012.run"""
import math
import pickle

import numpy as np
import pandas as pd

from lib import criteria as cr, panel, strategy as st
from lib.lazyprices import DIR
from lib.paths import INTERIM, MODEL_A
from rounds.round_003.run import monthly_universe

ROUND = "012"
OUT = MODEL_A / "rounds" / "round_012"


def cos(a, b):
    if not a or not b:
        return np.nan
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    return dot / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))


def jac(a, b):
    if not a or not b:
        return np.nan
    A, B = set(a), set(b)
    return len(A & B) / len(A | B)


def similarities() -> pd.DataFrame:
    fl = pd.read_parquet(INTERIM / "lazy_filings.parquet").sort_values(["cik", "filingDate"])
    rows = []
    for cik, g in fl.groupby("cik"):
        prev = None
        for r in g.itertuples(index=False):
            p = DIR / f"{cik}_{r.accessionNumber}.pkl"
            rec = pickle.loads(p.read_bytes()) if p.exists() else {"ok": False}
            if not rec.get("ok"):
                continue
            if prev is not None and 270 <= (r.filingDate - prev[0]).days <= 460:
                rows.append({"cik": cik, "filed": r.filingDate, "cos_full": cos(rec["full"], prev[1]["full"]),
                             "jac_full": jac(rec["full"], prev[1]["full"]),
                             "cos_1a": cos(rec["i1a"], prev[1]["i1a"]), "jac_1a": jac(rec["i1a"], prev[1]["i1a"])})
            prev = (r.filingDate, rec)
    s = pd.DataFrame(rows)
    s.to_parquet(INTERIM / "lazy_similarity.parquet", index=False)
    return s


def main():
    fl = pd.read_parquet(INTERIM / "lazy_filings.parquet")
    cached = sum(1 for _ in DIR.glob("*.pkl"))
    sim = similarities()
    cov = {"filings_listed": len(fl), "docs_cached": cached, "pairs": len(sim), "pairs_with_1a": int(sim["cos_1a"].notna().sum()),
           "corr_cos_jac_full": sim[["cos_full", "jac_full"]].corr().iloc[0, 1], "corr_cos_jac_1a": sim[["cos_1a", "jac_1a"]].corr().iloc[0, 1]}
    print(cov)
    ctx = panel.Ctx()
    dfm, um = monthly_universe(ctx)
    res = []
    for col in ("cos_full", "cos_1a"):
        s = sim[["cik", "filed", col]].dropna().sort_values("filed")
        hold = {}
        for R, g in um.groupby("R"):
            ss = s[(s["filed"] <= R - pd.Timedelta(days=1)) & (s["filed"] > R - pd.DateOffset(months=15))].groupby("cik")[col].last()
            g = g.drop_duplicates("yahoo").copy()
            g["_s"] = g["cik"].map(ss)
            hold[R] = st.select(g, "_s", 0.2, 50)
        ew = {R: sorted(g["yahoo"].unique()) for R, g in um.groupby("R")}
        cov[f"months_lt50_{col}"] = float(np.mean([len(h) < 50 for h in hold.values()]))
        res.append(st.evaluate_trial(f"r{ROUND}_LAZY_{col.upper()}", ROUND, "T4:lazy_prices", {"similarity": col, "hold": "top quintile (floor 50)", "freq": "M", "weight": "EW"},
                                     hold, ew, ctx, "rounds/round_012/run.py", notes=f"docs {cached}/{len(fl)}"))
        print(col, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(OUT / "results.csv", index=False)
    pd.Series(cov).to_csv(OUT / "coverage.csv")
    pd.concat({r["trial_id"]: r["_nav10"] for r in res}, axis=1).to_parquet(INTERIM / "r012_nav.parquet")
    print(cov)
    pd.set_option("display.width", 250)
    print(out[["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew", "S1", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew"]].round(3).to_string())


if __name__ == "__main__":
    main()
