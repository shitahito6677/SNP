"""
Round 013 runner — BMF20 (HYPOTHESIS.md): เลือก 20 ตัวจาก BM + F-score ด้วย 2 กฎ แล้วประเมิน S1–S3/S6 แบบมาตรฐาน
(Y2_SWITCH ลงก้อนเดียวไม่เติมเงิน = lib.backtest.run ปีละครั้ง) — รันจาก model_A: python3 -m rounds.round_013.run

โหมดการลงทุน 5 แบบ (ข้อมูลอธิบาย) อยู่ใน rounds/round_013/modes.py
"""
import pandas as pd

from lib import criteria as cr, panel, strategy as st, universe
from lib.paths import INTERIM, MODEL_A

ROUND = "013"
OUT = MODEL_A / "rounds" / "round_013"
N_PICK, N_FUNNEL, W_BM = 20, 100, 0.6
RULES = {"funnel": "r013_BMF20_FUNNEL", "weighted": "r013_BMF20_WEIGHTED"}


def bmf_universe(df: pd.DataFrame) -> pd.DataFrame:
    """universe ของ v1 variant main (HYPOTHESIS ข้อ 2) จาก panel รายปี — ตัดซ้ำ yahoo เก็บแถวแรกเหมือน v1"""
    u = df[df["in_U"] & df["V_BM"].notna() & df["A_FSCORE"].notna()]
    u = u.drop_duplicates(["R", "yahoo"]).rename(columns={"V_BM": "BM", "A_FSCORE": "F"})
    return u[["R", "ticker", "yahoo", "cik", "sic", "sic_group", "mcap", "fy_t_end", "BM", "F", "nsig"]].reset_index(drop=True)


def score_year(g: pd.DataFrame) -> pd.DataFrame:
    """คะแนน/อันดับของทั้งสองกฎภายใน universe ของวันเดียว (ทุกตัว ไม่ใช่แค่ 20 ตัวที่เลือก)"""
    g = g.copy()
    n = len(g)
    g["bm_rank"] = g.sort_values(["BM", "yahoo"], ascending=[False, True]).assign(k=range(1, n + 1))["k"].reindex(g.index)
    g["pBM"] = 100 * g["BM"].rank(pct=True, method="average")
    g["pF"] = 100 * g["F"].rank(pct=True, method="average")
    # S1_FUNNEL: 100 ตัว BM สูงสุด → F มาก→น้อย, BM มาก→น้อย, ticker; ตัวนอก 100 ต่อท้ายตามอันดับ BM (ใช้แสดงผลใน export เท่านั้น)
    g["funnel_stage1"] = g["bm_rank"] <= N_FUNNEL
    s1 = g[g["funnel_stage1"]].sort_values(["F", "BM", "yahoo"], ascending=[False, False, True])
    rest = g[~g["funnel_stage1"]].sort_values("bm_rank")
    g.loc[s1.index, "rank_funnel"] = range(1, len(s1) + 1)
    g.loc[rest.index, "rank_funnel"] = range(len(s1) + 1, n + 1)
    # S2_WEIGHTED: 0.6 pBM + 0.4 pF → คะแนนมาก→น้อย, BM มาก→น้อย, ticker
    g["score_weighted"] = W_BM * g["pBM"] + (1 - W_BM) * g["pF"]
    s2 = g.sort_values(["score_weighted", "BM", "yahoo"], ascending=[False, False, True])
    g.loc[s2.index, "rank_weighted"] = range(1, n + 1)
    g["rank_funnel"], g["rank_weighted"] = g["rank_funnel"].astype(int), g["rank_weighted"].astype(int)
    g["sel_funnel"], g["sel_weighted"] = g["rank_funnel"] <= N_PICK, g["rank_weighted"] <= N_PICK
    g["n_universe"] = n
    return g


def scores(df: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([score_year(g) for _, g in bmf_universe(df).groupby("R")], ignore_index=True)


def holdings(sc: pd.DataFrame, rule: str) -> dict:
    s = sc[sc[f"sel_{rule}"]].sort_values(["R", f"rank_{rule}"])
    return {R: list(g["yahoo"]) for R, g in s.groupby("R")}


def v1_p3_and_ew() -> dict:
    """รายชื่อ v1 main (P3 และ EW ของ universe v1) จาก v1_scores.parquet ผ่านโค้ด v1 เดิม"""
    port = universe.portfolios(pd.read_parquet(INTERIM / "v1_scores.parquet"), "main")
    return {"P3": {R: v["P3"] for R, v in port.items()}, "EW_v1u": {R: v["EW"] for R, v in port.items()}}


def main():
    ctx = panel.Ctx()
    df = panel.build(panel.rebalance_dates(ctx, "A"), ctx, "annual")
    sc = scores(df)
    v1 = v1_p3_and_ew()
    # universe ต้องตรงกับ universe ของ v1 ทุกปี (HYPOTHESIS ข้อ 2)
    for R, g in sc.groupby("R"):
        assert sorted(g["yahoo"]) == v1["EW_v1u"][R], f"{R.date()}: universe ไม่ตรงกับ v1"
    names = ctx.name_of
    sc["name"] = sc["cik"].map(names)
    sc.to_csv(OUT / "scores.csv", index=False)
    for rule in RULES:
        p = sc[sc[f"sel_{rule}"]].sort_values(["R", f"rank_{rule}"])
        p = p.assign(score=p["rank_funnel"] if rule == "funnel" else p["score_weighted"].round(4))
        cols = ["R", "yahoo", "name", "sic_group", "BM", "F", "bm_rank", "pBM", "pF", "score", f"rank_{rule}", "n_universe"]
        p[cols].rename(columns={"yahoo": "ticker", f"rank_{rule}": "rank"}).to_csv(OUT / f"picks_{rule}.csv", index=False)
    print("universe ต่อปี:", sc.groupby("R").size().to_dict(), flush=True)

    ew = st.ew_holdings(df)  # EW ของ U(d) ตาม PREREG_AUTORUN ข้อ 2 (ตัวเดียวกับ round 001/004/010)
    res = []
    for rule, tid in RULES.items():
        h = holdings(sc, rule)
        assert all(len(v) == N_PICK for v in h.values()), f"{rule}: จำนวนหุ้นไม่ใช่ 20 ทุกปี"
        spec = {"rule": rule, "n": N_PICK, "funnel_bm_top": N_FUNNEL if rule == "funnel" else None,
                "w_bm": W_BM if rule == "weighted" else None, "universe": "v1 main (BM & F present)", "freq": "A", "weight": "EW"}
        res.append(st.evaluate_trial(tid, ROUND, "BMF20:value+fscore", spec, h, ew, ctx, "rounds/round_013/run.py",
                                     notes="user idea (BMF20.md); S6 fails by construction (20 names)"))
        print(tid, "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(OUT / "results.csv", index=False)

    # ตัวเทียบ (ไม่ใช่ trial): v1 P3 และ EW ของ universe v1 — ต้องได้ NAV เดิมของ v1 เป๊ะ
    ref = pd.read_parquet(INTERIM / "v1_nav.parquet")
    navs = {r["trial_id"]: r["_nav10"] for r in res} | {"EW": res[0]["_ew10"]}
    for k, col in (("P3", "main|P3"), ("EW_v1u", "main|EW")):
        navs[k] = st.run_nav(v1[k], ctx.adj, 0.001)
        err = float((navs[k].reindex(ref[col].dropna().index) / ref[col].dropna() - 1).abs().max())
        assert err < 1e-9, f"{k}: NAV ไม่ตรงกับ v1_nav.parquet ({err:.2e})"
        print(k, "NAV ตรงกับ v1 เดิม (max rel diff", f"{err:.1e})", flush=True)
    pd.concat(navs, axis=1).to_parquet(INTERIM / "r013_nav.parquet")
    pd.set_option("display.width", 250)
    print(out[["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew",
               "S1_10", "S1_25", "S2_share", "DSR", "S6_avg_n", "S6_min_n", "info_sharpe", "info_sharpe_ew", "info_cagr", "info_cagr_ew"]]
          .round(3).to_string())


if __name__ == "__main__":
    main()
