"""
Panel หุ้น × วัน rebalance (รอบเดียวจบ) — universe, market cap, F-score, สัญญาณ v2 และตระกูล A ทั้งหมด
ใช้ได้ทั้ง rebalance รายปีและรายเดือน; ข้อมูลราคาถูกตัดที่ held-out cutoff ผ่าน lib.guard

เรียก: build(dates) → DataFrame (cache เป็น parquet ใน data/interim/panel_<tag>.parquet)
"""

import numpy as np
import pandas as pd

from lib import audit, build_data, cik_map, constituents, fscore, guard, prices, sec_rss, signals_a, signals_v2
from lib.paths import INTERIM
from lib.pit import PIT, STALE_MONTHS


class Ctx:
    """ข้อมูลที่ใช้ร่วมกัน โหลดครั้งเดียว"""

    def __init__(self):
        self.hist = constituents.load_history()
        self.segs = build_data.build_segments(build_data.build_spells())
        long, _ = build_data.build_facts(self.segs)
        self.pit = PIT(long)
        self.adj = prices.load_adj_close()
        self.close = prices.load_close()
        self.splits = prices.load_splits()
        rss = sec_rss.load_all()
        self.sic_of = rss.sort_values("filed").dropna(subset=["sic"]).groupby("cik").sic.last().to_dict()
        self.name_of = rss.sort_values("filed").groupby("cik").name.last().to_dict()
        cur = cik_map.load_current_map()
        inv = {}
        for tk, c in cur.items():
            inv.setdefault(c, []).append(tk)
        self.cik_ticker = {c: audit.common_ticker(v) for c, v in inv.items()}
        irx = self.close["^IRX"].resample("ME").last()
        self.rf = irx.shift(1) / 100 / 12
        self.spy = self.adj["SPY"].dropna()


def _rows_from_wide(w: pd.DataFrame, R: pd.Timestamp) -> dict:
    out = {"t": None, "t1": None, "t2": None}
    if w.empty:
        return out
    ta = w["total_assets"].dropna()
    ta = ta[ta.index >= R - pd.DateOffset(months=STALE_MONTHS)]
    if ta.empty:
        return out
    pe = ta.index.max()
    out["t"] = w.loc[pe].rename(pe)
    for k, yrs in (("t1", 1), ("t2", 2)):
        lo, hi = pe - pd.Timedelta(days=365 * yrs + 40), pe - pd.Timedelta(days=365 * yrs - 40)
        c = w[(w.index >= lo) & (w.index <= hi) & w["total_assets"].notna()]  # ดู lib/pit.py
        if len(c):
            out[k] = c.iloc[-1].rename(c.index[-1])
    return out


def build(dates, ctx: Ctx, tag: str, force: bool = False) -> pd.DataFrame:
    p = INTERIM / f"panel_{tag}.parquet"
    if p.exists() and not force:
        return pd.read_parquet(p)
    for d in dates:
        guard.check_end(d)
    rows = []
    cache = {}
    for R in dates:
        members = ctx.hist[ctx.hist["date"] <= R].iloc[-1]["tickers"]
        for t in members:
            cik = audit.cik_for(ctx.segs, t, R)
            sic = ctx.sic_of.get(cik) if cik is not None else None
            row = {"R": R, "ticker": t, "cik": cik, "sic": sic, "financial": audit.is_financial(sic),
                   "sic_group": audit.sic_group(sic)}
            if cik is None:
                rows.append(row)
                continue
            w = ctx.pit.wide_asof(cik, R)
            rs = _rows_from_wide(w, R)
            tr = rs["t"]
            shares = tr.get("shares", np.nan) if tr is not None else np.nan
            sratio = tr.get("shares_ratio", np.nan) if tr is not None else np.nan
            sdate = tr.get("shares_date", None) if tr is not None else None
            pr = audit.choose_price(t, cik, R, shares, sratio, ctx.adj, ctx.close, ctx.splits, ctx.cik_ticker,
                                    constituents.to_yahoo, prices.split_factor_after, sdate)
            row.update(yahoo=pr["yahoo"], price_flag=pr["price_flag"], mcap=pr["mcap_R"],
                       fy_t_end=tr.name if tr is not None else pd.NaT)
            if tr is not None:
                sf = 1.0
                if rs["t1"] is not None and pr["yahoo"]:
                    sf = audit.split_factor_between(ctx.splits, pr["yahoo"], rs["t1"]["shares_date"], tr["shares_date"])
                sg = fscore.signals(rs, sf, "evidence")
                row["A_FSCORE"], row["nsig"] = fscore.score(sg, "rescale")
                row.update(signals_v2.raw(rs, pr["mcap_R"], sf))
                row.update(signals_a.compute(w, rs, pr["mcap_R"]))
            rows.append(row)
    df = pd.DataFrame(rows)
    df["in_U"] = (~df["financial"]) & df["cik"].notna() & df["yahoo"].notna() & (df["price_flag"] == "ok")
    # G-score เทียบค่ากลางกลุ่ม SIC ภายใน U ณ วันเดียวกัน
    u = df[df["in_U"]].copy()
    df.loc[u.index, "A_GSCORE"] = signals_a.gscore(u)
    df.to_parquet(p, index=False)
    return df


def rebalance_dates(ctx: Ctx, freq: str, start="2011-06-01", end=guard.CUTOFF) -> list:
    """วันทำการสุดท้ายของงวด: 'A' = มิ.ย. ทุกปี, 'S' = มิ.ย./ธ.ค., 'Q' = มี.ค./มิ.ย./ก.ย./ธ.ค., 'M' = ทุกเดือน"""
    idx = ctx.spy.loc[start:end].index
    months = {"A": {6}, "S": {6, 12}, "Q": {3, 6, 9, 12}, "M": set(range(1, 13))}[freq]
    s = pd.Series(idx, index=idx)
    last = s.groupby([idx.year, idx.month]).max()
    # rebalance ต้องเกิดก่อน cutoff (ช่วงถือสุดท้ายจบที่ cutoff) — rebalance มิ.ย. 2023 เป็น held-out
    return [d for d in last if d.month in months and d < pd.Timestamp(end)]
