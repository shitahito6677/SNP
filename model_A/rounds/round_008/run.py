"""Round 008 runner — T1 ตัวกรองแนวโน้ม (PREREG_OVERLAY.md) — python3 -m rounds.round_008.run"""
import pandas as pd

from lib import criteria as cr, guard, overlay2 as ov, panel, prices, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_003.run import monthly_universe
from rounds.round_004.run import build as build_r004

ROUND = "008"
OUT = MODEL_A / "rounds" / "round_008"


def index_level():
    intl = prices.load_intl_index()
    adj = prices.load_adj_close()
    series = {t: intl[t] for t in ["^GSPC", "^DJI", "^IXIC", "^N225", "^FTSE", "^GDAXI", "^HSI", "^STI", "EEM"]}
    series["TDEX.BK"], series["THD"] = adj["TDEX.BK"], adj["THD"]
    rf = ov.irx_monthly()
    rows = []
    for name, px in series.items():
        px = px.dropna()
        for rule in ("A", "B"):
            o, bh, w = ov.apply(px, rule, 0.001)
            so, sb = ov.stats(o, rf), ov.stats(bh, rf)
            rows.append({"market": name, "rule": rule, "start": px.index.min().date(), "end": px.index.max().date(), "years": round(sb["years"], 1),
                         "CAGR_overlay": so["CAGR"], "CAGR_bh": sb["CAGR"], "CAGR_lost": so["CAGR"] - sb["CAGR"],
                         "Sharpe_overlay": so["Sharpe"], "Sharpe_bh": sb["Sharpe"], "MaxDD_overlay": so["MaxDD"], "MaxDD_bh": sb["MaxDD"],
                         "DD_reduction_pt": (so["MaxDD"] - sb["MaxDD"]) * 100, "time_in_cash_%": (1 - w.mean()) * 100,
                         "pass": bool(so["Sharpe"] > sb["Sharpe"] and (so["MaxDD"] - sb["MaxDD"]) * 100 >= 10)})
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "index_level.csv", index=False)
    lab = d.groupby("rule")["pass"].agg(passed="sum", markets="size")
    lab["share"] = lab.passed / lab.markets
    lab["label_ลดความเสี่ยงได้จริง"] = lab.share >= 0.70
    lab.to_csv(OUT / "index_level_label.csv")
    return d, lab


def portfolio_level():
    ctx = panel.Ctx()
    dfm, um = monthly_universe(ctx)
    ew = st.ew_holdings(dfm)
    ew10, ew25 = st.run_nav(ew, ctx.adj, 0.001), st.run_nav(ew, ctx.adj, 0.0025)
    dates = panel.rebalance_dates(ctx, "A")
    base_h = build_r004(um[um["R"].isin(dates)], "r001_Q_LOWACC_overall", "W_CAP", dates)
    b10, b25 = st.run_nav(base_h, ctx.adj, 0.001), st.run_nav(base_h, ctx.adj, 0.0025)
    n_ew = pd.Series({R: len(v) for R, v in ew.items()})
    n_b = pd.Series({R: len(v) for R, v in base_h.items()})
    res = []
    for asset, (a10, a25, cnt) in {"EW": (ew10, ew25, n_ew), "LOWACC_WCAP": (b10, b25, n_b)}.items():
        for rule in ("A", "B"):
            if asset == "EW" and rule == "A":
                continue  # = r005_trend_EW (สูตรเดียวกัน) ไม่นับซ้ำ
            o10, _, w = ov.apply(a10, rule, 0.001)
            o25, _, _ = ov.apply(a25, rule, 0.0025)
            wm = w.reindex(cnt.index, method="ffill").fillna(1.0) if asset == "EW" else w.reindex(pd.DatetimeIndex(cnt.index), method="ffill").fillna(1.0)
            # S6 ตามตัวอักษร: จำนวนหุ้น × 1[w>0] ทุกสิ้นเดือน
            mc = pd.Series(cnt.reindex(w.index, method="ffill").values, index=w.index) * (w.fillna(1.0) > 0)
            mc = mc.loc["2011-06-30":"2023-05-31"].dropna()
            e = cr.evaluate(o10, ew10, o25, ew25, ctx.spy, ctx.rf, mc)
            e.update(round=ROUND, trial_id=f"r{ROUND}_{rule}_{asset}", family="E:overlay(T1)", spec={"rule": rule, "asset": asset, "cash": "^IRX"},
                     evaluator="rounds/round_008/run.py", notes=f"time in cash {(1 - w.loc['2011-06':'2023-05'].mean()) * 100:.1f}%")
            e["_nav10"] = o10
            res.append(e)
            print(e["trial_id"], "done", flush=True)
    t = st.record(res)
    out = t[t["round"].astype(str) == ROUND].copy()
    s3 = [cr.s3_for(i, t) for i in out["trial_id"]]
    out["DSR"], out["S3"], out["N_trials"] = [x["DSR"] for x in s3], [x["S3"] for x in s3], len(t)
    out.to_csv(OUT / "results.csv", index=False)
    pd.concat({r["trial_id"]: r["_nav10"] for r in res} | {"EW_M": ew10, "LOWACC_WCAP": b10}, axis=1).to_parquet(INTERIM / "r008_nav.parquet")
    return out


if __name__ == "__main__":
    d, lab = index_level()
    pd.set_option("display.width", 250)
    print(d.round(3).to_string()); print(lab)
    out = portfolio_level()
    print(out[["trial_id", "dec_sharpe", "dec_sharpe_ew", "dec_sharpe_spy", "dec_cagr", "dec_cagr_ew", "dec_maxdd", "dec_maxdd_ew", "S1", "S2_share", "DSR", "S6_min_n", "notes"]].round(3).to_string())
