"""
คะแนนต่อหุ้นต่อรอบ rebalance (BM + F-score) สำหรับทุก variant ใน PREREG v1

variant (ดู PREREG.md ข้อ 4, 8):
  main : ltd_policy="evidence", score_policy="rescale"  (หลัก)
  S1   : ltd_policy="evidence", score_policy="zero"     (ข้อที่ขาด = 0)
  S2   : ltd_policy="zero",     score_policy="rescale"  (หนี้ที่ไม่มี tag = 0)
  S3   : เหมือน main แต่ตัด IR และ JEF
"""

import numpy as np
import pandas as pd

from lib import audit, fscore

VARIANTS = {"main": ("evidence", "rescale"), "S1": ("evidence", "zero"), "S2": ("zero", "rescale")}
S3_EXCLUDE = {"IR", "JEF"}


def build_scores(hist, segs, pit, adj, close, splits, Rs, to_yahoo, sic_of, cik_ticker, split_factor_after) -> pd.DataFrame:
    rows = []
    for R in Rs:
        members = hist[hist["date"] <= R].iloc[-1]["tickers"]
        for t in members:
            cik = audit.cik_for(segs, t, R)
            sic = sic_of.get(cik) if cik is not None else None
            rs = pit.rows_asof(cik, R) if cik is not None else {"t": None, "t1": None, "t2": None}
            tr = rs["t"]
            shares = tr.get("shares", np.nan) if tr is not None else np.nan
            sratio = tr.get("shares_ratio", np.nan) if tr is not None else np.nan
            sdate = tr.get("shares_date", None) if tr is not None else None
            pr = audit.choose_price(t, cik, R, shares, sratio, adj, close, splits, cik_ticker, to_yahoo,
                                    split_factor_after, sdate)
            equity = tr.get("equity", np.nan) if tr is not None else np.nan
            row = {"R": R, "ticker": t, "cik": cik, "sic": sic, "financial": audit.is_financial(sic),
                   "yahoo": pr["yahoo"], "price_flag": pr["price_flag"], "mcap_R": pr["mcap_R"],
                   "equity_t": equity, "fy_t_end": tr.name if tr is not None else pd.NaT}
            row["BM"] = equity / pr["mcap_R"] if pd.notna(equity) and pd.notna(pr["mcap_R"]) and pr["mcap_R"] > 0 else np.nan
            sf = 1.0
            if tr is not None and rs["t1"] is not None and pr["yahoo"]:
                sf = audit.split_factor_between(splits, pr["yahoo"], rs["t1"]["shares_date"], tr["shares_date"])
            for v, (ltd, sc) in VARIANTS.items():
                if tr is None:
                    row[f"F_{v}"], row[f"nsig_{v}"] = np.nan, 0
                    continue
                sg = fscore.signals(rs, sf, ltd_policy=ltd)
                row[f"F_{v}"], row[f"nsig_{v}"] = fscore.score(sg, sc)
                if v == "main":
                    row.update({k: sg[k] for k in fscore.SIGNALS})
            rows.append(row)
    df = pd.DataFrame(rows)
    base = (~df["financial"]) & df["cik"].notna() & df["yahoo"].notna() & (df["price_flag"] == "ok") & df["BM"].notna()
    for v in VARIANTS:
        df[f"elig_{v}"] = base & df[f"F_{v}"].notna()
    df["elig_S3"] = df["elig_main"] & ~df["ticker"].isin(S3_EXCLUDE)
    df["F_S3"] = df["F_main"]
    return df


def portfolios(df: pd.DataFrame, variant: str, high_f: float = 7.0, bm_pct: float = 0.8) -> dict:
    """คืน {R: {"EW": [...], "P1": [...], "P2": [...], "P3": [...]}} เป็นรายชื่อ yahoo ticker (unique ต่อรอบ)"""
    out = {}
    for R, g in df[df[f"elig_{variant}"]].groupby("R"):
        g = g.drop_duplicates("yahoo")
        pos = g[g["BM"] > 0]
        thr = pos["BM"].quantile(bm_pct)
        p1 = set(pos.loc[pos["BM"] >= thr, "yahoo"])
        p2 = set(g.loc[g[f"F_{variant}"] >= high_f, "yahoo"])
        out[R] = {"EW": sorted(g["yahoo"]), "P1": sorted(p1), "P2": sorted(p2), "P3": sorted(p1 & p2)}
    return out
