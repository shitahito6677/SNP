"""Survivorship coverage ของ universe top-1500 (แบบ v0) — ทำก่อนดูผลกลยุทธ์; python3 -m rounds.round_007.coverage"""
import pandas as pd

from lib import panel1500 as p15, sec_facts, universe1500 as u15
from lib.paths import MODEL_A


def main():
    ctx = p15.Ctx1500()
    dates = [d for d in ctx.spy.groupby([ctx.spy.index.year, ctx.spy.index.month]).tail(1).index if d.month == 6 and d.year <= 2022 and d.year >= 2011]
    df = p15.build(dates, ctx)
    pool = u15.pool()
    fl = pd.concat([sec_facts.public_float(int(c)) for c in pool["cik"]], ignore_index=True)
    rows = []
    for R in dates:
        recent = set(ctx.rss10k[(ctx.rss10k["filed"] <= R) & (ctx.rss10k["filed"] > R - pd.DateOffset(months=18))]["cik"])
        f = fl[(fl["filed"] <= R - pd.Timedelta(days=1)) & (fl["end"] >= R - pd.DateOffset(months=18)) & fl["cik"].isin(recent) & (fl["val"] > 0)]
        f = f.sort_values("filed").groupby("cik").last()
        top = f.sort_values("val", ascending=False).head(1500)
        d = df[df["R"] == R].set_index("cik")
        has_px = top.index.isin(d.index[d["price_flag"] == "ok"])
        in_u = top.index.isin(d.index[d["in_U"].fillna(False).astype(bool)])
        rows.append({"R": R.date(), "pool_recent_10k": len(recent), "float_top1500": len(top),
                     "coverage_price_%": round(100 * has_px.mean(), 1), "of_which_in_U_%": round(100 * in_u.mean(), 1),
                     "U1500_size": int(d["in_U"].fillna(False).astype(bool).sum()), "top1500_mcap_rows": int(d["top1500"].fillna(False).astype(bool).sum()),
                     "removed_by_liquidity": int((d["top1500"].fillna(False).astype(bool) & ~d["liquid"].fillna(False).astype(bool)).sum()),
                     "financial_in_top1500": int((d["top1500"].fillna(False).astype(bool) & d["financial"].fillna(False).astype(bool)).sum()),
                     "mcap_cutoff_$bn": round(d.loc[d["top1500"].fillna(False).astype(bool), "mcap"].min() / 1e9, 2)})
    out = pd.DataFrame(rows)
    # ตรวจ market cap กับ public float (แบบ v1): หุ้นใน U ที่ float วัดห่างจาก R ≤ 10 วัน
    uu = df[df["in_U"].fillna(False).astype(bool)][["R", "cik", "mcap"]]
    m = uu.merge(fl.loc[fl["val"].astype(float) > 0, ["cik", "end", "val"]], on="cik")
    m = m[(m["end"] - m["R"]).abs() <= pd.Timedelta(days=10)]
    ratio = (m["mcap"] / m["val"])
    ratio = ratio[(ratio >= 0.01) & (ratio <= 100)]
    print(f"mcap/float: n={len(ratio)}, median={ratio.median():.3f}, <0.7={(ratio < 0.7).mean():.2%}, >1.5={(ratio > 1.5).mean():.2%}")
    assert 0.9 <= ratio.median() <= 1.5 and (ratio < 0.7).mean() < 0.02, "market cap ผิดปกติเทียบ public float"
    out.to_csv(MODEL_A / "rounds" / "round_007" / "coverage.csv", index=False)
    pd.set_option("display.width", 250)
    print(out.to_string())


if __name__ == "__main__":
    main()
