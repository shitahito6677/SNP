"""
EXPLORE2 — ผู้เข้ารอบ 5 อันดับแรก ใน 3 แบบการลงทุน (ข้อมูลอธิบายเท่านั้น ไม่ใช้เลือกกฎ):
  1) lump-sum: ลงก้อนเดียว 30 มิ.ย. 2017 แล้วปรับพอร์ตตามกฎ (NAV net 10 bps)
  2) DCA: เติมเงินเท่ากันทุกวันทำการแรกของเดือน ก.ค. 2017 – มิ.ย. 2023 ซื้อที่ NAV ของกฎ
  3) buy-once: ซื้อพอร์ตของกฎ ณ รอบ มิ.ย. 2017 ครั้งเดียว ถือไม่ปรับจนถึง 30 มิ.ย. 2023 (หุ้นที่หายจากตลาด = เงินสด)
python3 -m explore2.top5_modes
"""
import numpy as np
import pandas as pd

from lib import backtest as bt, criteria as cr, guard, panel, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_003.run import monthly_universe
from rounds.round_004.run import build

OUT = MODEL_A / "explore2" / "top5"
START = pd.Timestamp("2017-06-30")
PLAIN = {
    "r004_Q_LOWACC_overall_W_CAP": "accruals ต่ำ 20% แรก ถือตามขนาดบริษัท ปีละครั้ง",
    "r004_C_SHYQMOM_overall_W_CAP": "คืนเงินผู้ถือหุ้น+คุณภาพกำไร+แรงส่งราคา 20% แรก ถือตามขนาด รายเดือน",
    "r004_Q_LOWACC_overall_BUFFER": "accruals ต่ำ 20% แรก ถือเท่ากัน มีบัฟเฟอร์ 30% ปีละครั้ง",
    "r001_Q_LOWACC_overall": "accruals ต่ำ 20% แรก ถือเท่ากัน ปีละครั้ง",
    "r011_LOWACC_INSIDER_TILT": "accruals ต่ำ 20% แรก ให้น้ำหนัก 2 เท่ากับหุ้นที่ผู้บริหารซื้อแบบ opportunistic",
    "r004_Q_LOWACC_overall_W_IV": "accruals ต่ำ 20% แรก ถือมากในหุ้นที่แกว่งน้อย ปีละครั้ง",
}


def top5() -> list:
    t = cr.load_trials()
    ok = lambda c: t[c].astype(str).str.lower().eq("true")
    t = t.assign(order_=range(len(t)), k1=t["dec_sharpe"].round(6), k2=t["dec_cagr"].round(6), k3=t["dec_maxdd"].round(6))
    c = t[ok("S1") & ok("S2") & ok("S6")].sort_values(["k1", "order_"], ascending=[False, True])
    c = c[~c["family"].astype(str).str.startswith("U1500")]
    c = c.drop_duplicates(subset=["k1", "k2", "k3"], keep="first")  # ผลเท่ากันทุกหลัก (SECCAP = r001) → เก็บ trial ที่ทดสอบก่อน
    return list(c["trial_id"].iloc[:5])


def holdings(tid, ctx, dfm, um):
    if tid.startswith("r004_") or tid == "r001_Q_LOWACC_overall":
        base = "r003_C_SHYQMOM_overall" if "SHYQMOM" in tid else "r001_Q_LOWACC_overall"
        variant = tid.rsplit("_", 1)[1] if tid.startswith("r004_") else "EW"
        variant = {"CAP": "W_CAP", "IV": "W_IV"}.get(variant, variant)
        dates = panel.rebalance_dates(ctx, "M" if "SHYQMOM" in tid else "A")
        return build(um[um["R"].isin(dates)], base, variant, dates)
    if tid == "r011_LOWACC_INSIDER_TILT":
        from rounds.round_011.run import classify, signal
        ins = pd.read_parquet(INTERIM / "insider_sp500.parquet")
        adates = panel.rebalance_dates(ctx, "A")
        u = um[um["R"].isin(adates)].merge(signal(ins, classify(ins), adates), on=["R", "cik"], how="left")
        u["opp_buys"] = u["opp_buys"].fillna(0)
        u = u.drop_duplicates(["R", "yahoo"])
        out = {}
        for R, g in u.groupby("R"):
            names = st.select(g, "Q_LOWACC", 0.2, 50)
            s = g.set_index("yahoo").loc[names, "opp_buys"]
            out[R] = {y: (2.0 if s[y] > 0 else 1.0) for y in names}
        return out
    raise KeyError(f"ยังไม่มีตัวสร้าง holdings ของ {tid}")


def modes(nav: pd.Series) -> dict:
    nav = nav[nav.index <= guard.CUTOFF]
    d = bt.dca(nav, START, guard.CUTOFF)
    m = bt.monthly(nav[nav.index >= START])
    return {"lumpsum_x": d["lumpsum_multiple"], "lumpsum_cagr": d["lumpsum_multiple"] ** (1 / 6) - 1,
            "dca_x": d["dca_final_over_invested"], "dca_irr": d["dca_IRR"], "months": len(m)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = panel.Ctx()
    dfm, um = monthly_universe(ctx)
    ids = top5()
    print("top5:", ids)
    ea = {R: v for R, v in st.ew_holdings(dfm).items() if R in set(panel.rebalance_dates(ctx, "A"))}
    rows = []
    bench = {"EW (ปีละครั้ง)": ea, "SPY": None}
    for name, h in list(bench.items()) + [(i, None) for i in ids]:
        if name == "SPY":
            nav = ctx.spy
            once = ctx.spy
        else:
            h = h if h is not None else holdings(name, ctx, dfm, um)
            nav = st.run_nav(h, ctx.adj, 0.001)
            if name != "EW (ปีละครั้ง)":  # ต้องได้ NAV ตรงกับที่บันทึกตอนรัน round นั้น
                ref = pd.read_parquet(INTERIM / f"{name[:4]}_nav.parquet")[name].dropna()
                assert np.allclose(nav.reindex(ref.index).values, ref.values, rtol=1e-9), f"{name}: NAV ไม่ตรงกับ round เดิม"
            R0 = max(R for R in h if R <= START)
            assert (START - R0).days < 40, (name, R0)
            once = st.run_nav({R0: h[R0]}, ctx.adj, 0.001)
        r = {"trial_id": name, "plain": PLAIN.get(name, name)}
        r.update(modes(nav))
        o = modes(once)
        r["buyonce_x"], r["buyonce_cagr"] = o["lumpsum_x"], o["lumpsum_cagr"]
        rows.append(r)
        print(name, {k: round(v, 3) for k, v in r.items() if isinstance(v, float)}, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "top5_modes.csv", index=False)
    lines = ["| กฎ | ลงก้อนเดียว ปรับตามกฎ: เงิน 1 → | ต่อปี | DCA รายเดือน: มูลค่าสุดท้าย/เงินที่ใส่ | DCA IRR ต่อปี | ซื้อครั้งเดียว มิ.ย. 2017 ไม่ปรับ: เงิน 1 → | ต่อปี |",
             "|---|---|---|---|---|---|---|"]
    for r in df.itertuples():
        lab = r.plain if r.plain == r.trial_id else f"{r.plain}<br>`{r.trial_id}`"
        lines.append(f"| {lab} | {r.lumpsum_x:.2f} | {r.lumpsum_cagr:.1%} | {r.dca_x:.2f} | {r.dca_irr:.1%} | {r.buyonce_x:.2f} | {r.buyonce_cagr:.1%} |")
    (OUT / "top5_modes.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
