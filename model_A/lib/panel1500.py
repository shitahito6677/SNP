"""
Panel ของ universe "top 1500 by market cap" (round 007) — ต่อยอด lib.panel แต่สมาชิกมาจาก candidate pool (lib.universe1500)

ณ วัน R:
  ผู้สมัคร = CIK ใน pool ที่ยื่น 10-K ภายใน 18 เดือนก่อน R (จาก SEC RSS) และมีงบ PIT
  market cap PIT = ราคาจริง (ย้อน split) × จำนวนหุ้น PIT (ปรับ split หลังวันนับหุ้น) — ตรวจ ticker reuse ด้วย min_mcap = $50M
  top1500 = 1,500 อันดับแรกตาม market cap (รวมกลุ่มการเงิน)
  liquid = ราคาจริง ≥ $5 และ median(Close × Volume) 63 วันทำการ ≥ $1M
  in_U = top1500 & liquid & ไม่ใช่กลุ่มการเงิน
"""

import numpy as np
import pandas as pd

from lib import audit, build1500, cik_map, constituents, fscore, guard, prices, sec_rss, signals_a, signals_v2
from lib.panel import _rows_from_wide
from lib.paths import INTERIM
from lib.pit import PIT

TOP = 1500
MIN_PRICE_LIQ, MIN_DVOL = 5.0, 1e6


class Ctx1500:
    def __init__(self):
        self.pit = PIT(build1500.facts())
        self.tick = build1500.tickers().set_index("cik")
        self.close = guard.clip(pd.read_parquet(build1500.P_CLOSE).sort_index())
        self.adj = guard.clip(pd.read_parquet(build1500.P_ADJ).sort_index())
        self.vol = guard.clip(pd.read_parquet(build1500.P_VOL).sort_index())
        main_adj = prices.load_adj_close()
        us = main_adj["SPY"].dropna().index  # ปฏิทินสหรัฐและ SPY จาก price store หลัก (ตรวจแล้วใน v0)
        self.close, self.adj, self.vol = (x.reindex(us) for x in (self.close, self.adj, self.vol))
        self.adj["SPY"] = main_adj["SPY"].reindex(us)
        self.splits = prices.load_splits()
        rss = sec_rss.load_all()
        self.rss10k = rss[rss["form"].isin({"10-K", "10-K/A", "10-KT"})][["cik", "filed"]]
        self.sic_of = rss.sort_values("filed").dropna(subset=["sic"]).groupby("cik").sic.last().to_dict()
        cur = cik_map.load_current_map()
        inv = {}
        for tk, c in cur.items():
            inv.setdefault(c, []).append(tk)
        self.cik_ticker = {c: audit.common_ticker(v) for c, v in inv.items()}
        self.spy = self.adj["SPY"].dropna()
        irx = prices.load_close()["^IRX"].resample("ME").last()
        self.rf = irx.shift(1) / 100 / 12


def _splits_for(ctx, names):
    missing = sorted(set(n for n in names if n) - set(ctx.splits["yahoo"]))
    if missing:
        ctx.splits = pd.concat([ctx.splits, prices.download_splits(missing)], ignore_index=True).drop_duplicates()


def build(dates, ctx: Ctx1500, tag: str = "annual1500", force: bool = False) -> pd.DataFrame:
    p = INTERIM / f"panel_{tag}.parquet"
    if p.exists() and not force:
        return pd.read_parquet(p)
    dvol = (ctx.close * ctx.vol).rolling(63, min_periods=40).median()
    rows = []
    for R in dates:
        guard.check_end(R)
        recent = set(ctx.rss10k[(ctx.rss10k["filed"] <= R) & (ctx.rss10k["filed"] > R - pd.DateOffset(months=18))]["cik"])
        for cik in ctx.tick.index.intersection(list(recent)):
            tk = ctx.tick.loc[cik]
            t_hist = tk["ticker_prefix"] or tk["ticker_current"]
            if not isinstance(t_hist, str):
                continue
            w = ctx.pit.wide_asof(int(cik), R)
            rs = _rows_from_wide(w, R)
            tr = rs["t"]
            if tr is None:
                continue
            pr = audit.choose_price(t_hist, int(cik), R, tr.get("shares", np.nan), tr.get("shares_ratio", np.nan), ctx.adj,
                                    ctx.close, ctx.splits, ctx.cik_ticker, constituents.to_yahoo, prices.split_factor_after,
                                    tr.get("shares_date", None), min_mcap=50e6)
            if pr["price_flag"] != "ok":
                rows.append({"R": R, "cik": int(cik), "ticker": t_hist, "price_flag": pr["price_flag"]})
                continue
            sic = ctx.sic_of.get(int(cik))
            y = pr["yahoo"]
            dv = dvol[y].loc[:R].dropna().iloc[-1] if y in dvol.columns and dvol[y].loc[:R].notna().any() else np.nan
            rows.append({"R": R, "cik": int(cik), "ticker": t_hist, "yahoo": y, "price_flag": "ok", "mcap": pr["mcap_R"],
                         "raw_price": pr["raw_price"], "dvol63": dv, "sic": sic, "financial": audit.is_financial(sic),
                         "sic_group": audit.sic_group(sic), "_w": w, "_rs": rs})
        print(f"{R.date()} candidates {len(recent)} rows so far {len(rows)}", flush=True)
    df = pd.DataFrame(rows)
    ok = df["price_flag"] == "ok"
    df.loc[ok, "mcap_rank"] = df[ok].groupby("R")["mcap"].rank(ascending=False, method="first")
    df["top1500"] = ok & (df["mcap_rank"] <= TOP)
    df["liquid"] = (df["raw_price"] >= MIN_PRICE_LIQ) & (df["dvol63"] >= MIN_DVOL)
    df["in_U"] = df["top1500"] & df["liquid"] & ~df["financial"].fillna(False).astype(bool)
    # สัญญาณเฉพาะหุ้นใน U (ประหยัดเวลา)
    sig_rows = []
    for i, r in df[df["in_U"]].iterrows():
        rs, w = r["_rs"], r["_w"]
        tr = rs["t"]
        sf = 1.0
        if rs["t1"] is not None:
            sf = audit.split_factor_between(ctx.splits, r["yahoo"], rs["t1"]["shares_date"], tr["shares_date"])
        sg = fscore.signals(rs, sf, "evidence")
        d = {"_i": i}
        d["A_FSCORE"], d["nsig"] = fscore.score(sg, "rescale")
        d.update(signals_v2.raw(rs, r["mcap"], sf))
        d.update(signals_a.compute(w, rs, r["mcap"]))
        sig_rows.append(d)
    sig = pd.DataFrame(sig_rows).set_index("_i")
    df = df.drop(columns=["_w", "_rs"]).join(sig)
    u = df[df["in_U"]].copy()
    df.loc[u.index, "A_GSCORE"] = signals_a.gscore(u)
    df.to_parquet(p, index=False)
    return df
