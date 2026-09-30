"""T0 — วินิจฉัยว่าทำไม low accruals แพ้ช่วง 2011–2016 (diagnostic: ไม่นับเป็น trial, ห้ามใช้แก้กฎ) — python3 -m explore2.t0_diag"""
import numpy as np
import pandas as pd

from lib import backtest as bt, french, panel, strategy as st
from lib.paths import MODEL_A

OUT = MODEL_A / "explore2" / "t0"
OUT.mkdir(parents=True, exist_ok=True)
ALLSIG = ["Q_GPA", "Q_ROIC", "Q_LOWACC", "V_BM", "V_EP", "V_EBITEV", "V_FCFP", "I_LOWISS", "I_LOWAG", "A_FSCORE", "A_SHY", "A_LOWLEV"]
ENERGY = {"Oil & gas extraction", "Petroleum refining"}


def run_pair(u, ctx):
    hold = {R: st.select(g, "Q_LOWACC", 0.2, 50) for R, g in u.groupby("R")}
    ew = {R: sorted(g["yahoo"].unique()) for R, g in u.groupby("R")}
    a, e = bt.run(hold, ctx.adj, st.guard.CUTOFF), bt.run(ew, ctx.adj, st.guard.CUTOFF)
    return a, e


def yearly(a, e):
    fa = a["fwd"].groupby("R").fwd.mean()
    fe = e["fwd"].groupby("R").fwd.mean()
    return pd.DataFrame({"LOWACC": fa, "EW": fe, "excess": fa - fe})


def main():
    ctx = panel.Ctx()
    df = panel.build(panel.rebalance_dates(ctx, "A"), ctx, "annual")
    u = df[df["in_U"]].drop_duplicates(["R", "yahoo"])
    res = {}
    a, e = run_pair(u, ctx)
    y = yearly(a, e)
    y["window"] = np.where(y.index < "2017-01-01", "2011-2016", "2017-2022")
    res["1_yearly_excess"] = y
    # sector: holdings share and excess by SIC group (per window)
    f = a["fwd"].merge(u[["R", "yahoo", "sic_group"]], on=["R", "yahoo"])
    fe = e["fwd"].merge(u[["R", "yahoo", "sic_group"]], on=["R", "yahoo"])
    f["window"] = np.where(f.R < "2017-01-01", "2011-2016", "2017-2022")
    fe["window"] = np.where(fe.R < "2017-01-01", "2011-2016", "2017-2022")
    sec = f.groupby(["window", "sic_group"]).agg(n=("fwd", "size"), mean_fwd=("fwd", "mean"))
    sec["share_%"] = sec["n"] / sec.groupby(level=0)["n"].transform("sum") * 100
    ews = fe.groupby(["window", "sic_group"]).agg(ew_n=("fwd", "size"), ew_mean_fwd=("fwd", "mean"))
    ews["ew_share_%"] = ews["ew_n"] / ews.groupby(level=0)["ew_n"].transform("sum") * 100
    s = sec.join(ews, how="outer")
    s["overweight_pt"] = s["share_%"] - s["ew_share_%"]
    s["contrib_vs_ew"] = (s["share_%"].fillna(0) * s["mean_fwd"].fillna(0) - s["ew_share_%"].fillna(0) * s["ew_mean_fwd"].fillna(0)) / 100
    res["1b_sector"] = s.round(4).sort_values(["window", "contrib_vs_ew"])
    # 2 rank IC
    fw = e["fwd"].merge(u[["R", "yahoo", "Q_LOWACC"]], on=["R", "yahoo"]).dropna()
    res["2_rank_ic"] = fw.groupby("R").apply(lambda g: g["Q_LOWACC"].corr(g["fwd"], method="spearman")).rename("IC").to_frame()
    # 3 coverage
    res["3_coverage"] = u.groupby("R").agg(n_U=("yahoo", "size"), n_signal=("Q_LOWACC", "count"))
    res["3_coverage"]["missing_%"] = (1 - res["3_coverage"].n_signal / res["3_coverage"].n_U) * 100
    # 4 complete-data only
    uc = u[u[ALLSIG].notna().all(axis=1)]
    a4, e4 = run_pair(uc, ctx)
    y4 = yearly(a4, e4)
    # 5 ex-energy
    ux = u[~u["sic_group"].isin(ENERGY)]
    a5, e5 = run_pair(ux, ctx)
    y5 = yearly(a5, e5)
    rf = ctx.rf
    rows = []
    for name, (aa, ee, n) in {"base": (a, e, u), "complete_data_only": (a4, e4, uc), "ex_energy": (a5, e5, ux)}.items():
        for w, win in (("2011-2016", (pd.Timestamp("2011-06-30"), pd.Timestamp("2017-06-30"))), ("2017-2022", (pd.Timestamp("2017-06-30"), st.guard.CUTOFF))):
            ma = bt.metrics(bt.window(bt.monthly(aa["nav"]), *win), rf)
            me = bt.metrics(bt.window(bt.monthly(ee["nav"]), *win), rf)
            rows.append({"variant": name, "window": w, "Sharpe": ma["Sharpe"], "Sharpe_EW": me["Sharpe"], "CAGR": ma["CAGR"], "CAGR_EW": me["CAGR"],
                         "avg_universe": n.groupby("R").size().mean()})
    res["4_5_variants"] = pd.DataFrame(rows).round(4)
    res["4_yearly_complete"], res["5_yearly_exenergy"] = y4, y5
    # 6 French US factors
    fr = french.load("US")
    rows = []
    for w, (s0, s1) in {"2011-07..2017-06": ("2011-07", "2017-06"), "2017-07..2023-06": ("2017-07", "2023-06")}.items():
        x = fr.loc[s0:s1]
        rows.append({"window": w, **{f"{k}_ann_%": x[k].mean() * 12 * 100 for k in ["RMW", "CMA", "HML", "MOM", "Mkt-RF"]}})
    res["6_french_us"] = pd.DataFrame(rows).round(2)
    for k, v in res.items():
        v.to_csv(OUT / f"{k}.csv")
    pd.set_option("display.width", 250)
    for k, v in res.items():
        print("===", k); print(v.round(4).to_string())


if __name__ == "__main__":
    main()
