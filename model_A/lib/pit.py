"""
Point-in-time (PIT) accessor ของงบรายปี — "ณ วัน R นักลงทุนเห็นตัวเลขอะไรบ้าง"

กติกา (ผู้ใช้ยืนยันใน Phase 0):
  - ค่าของ (field, งวด) ใช้ได้ ณ วัน R ก็ต่อเมื่อ filed <= R - 1 วัน
  - ใช้ค่าที่ filed ครั้งแรกของแต่ละ tag (ตัดสินไว้แล้วใน lib.sec_facts.first_filed_annual)
  - ถ้ามีหลาย tag ให้เลือก tag ลำดับสูงสุด "เฉพาะที่ filed แล้ว ณ วัน R" (เลือกทีละ field)
    บทเรียนจาก v0 รอบแรก: ถ้าเลือก tag ก่อนแล้วค่อยเช็ควันที่ tag ที่ถูกเปิดเผยทีหลัง (เช่น revenue tag ใหม่ตาม
    ASC 606 ที่ถูกใส่ย้อนหลังเป็นตัวเลขเปรียบเทียบในงบปีถัดไป) จะทำให้ข้อมูลที่มีอยู่แล้ว "หายไป"
  - งบปีล่าสุด t = period_end ล่าสุดที่ total_assets filed แล้ว และไม่เก่ากว่า 18 เดือน
  - t1 / t2 = งวดที่ period_end ห่างจาก t ประมาณ 1 / 2 ปี (±40 วัน)

อุปมา: ห้องสมุดที่หนังสือแต่ละเล่มมี "วันวางแผง" — ณ วัน R หยิบได้เฉพาะเล่มที่วางแผงแล้ว
ถ้าเล่มเดียวกันมีหลายฉบับ (หลาย tag) เลือกฉบับที่ดีที่สุดในบรรดาที่วางแผงแล้วเท่านั้น
"""

import numpy as np
import pandas as pd

from lib.sec_facts import FIELDS

STALE_MONTHS = 18
LAG_DAYS = 1


class PIT:
    def __init__(self, long: pd.DataFrame):
        prio = {f: {t: i for i, t in enumerate(tags)} for f, (_, tags) in FIELDS.items()}
        x = long[long["field"] != "shares_cover"][["cik", "field", "tag", "period_end", "val", "filed"]].copy()
        x["prio"] = [prio[f].get(t, 99) for f, t in zip(x["field"], x["tag"])]
        cover = long[long["field"] == "shares_cover"][["cik", "val", "filed"]]
        self._by_cik = {c: g.sort_values(["field", "period_end", "prio"]) for c, g in x.groupby("cik")}
        self._cover = {c: g.sort_values("filed") for c, g in cover.groupby("cik")}

    def wide_asof(self, cik: int, R: pd.Timestamp) -> pd.DataFrame:
        """ตาราง period_end × field ของค่าที่เห็นได้ ณ วัน R (tag ลำดับสูงสุดที่ filed แล้ว)"""
        g = self._by_cik.get(cik)
        if g is None:
            return pd.DataFrame()
        cutoff = R - pd.Timedelta(days=LAG_DAYS)
        g = g[g["filed"] <= cutoff]
        if g.empty:
            return pd.DataFrame()
        best = g.groupby(["field", "period_end"], as_index=False).first()  # เรียงตาม prio แล้ว
        w = best.pivot(index="period_end", columns="field", values="val").sort_index()
        # จำนวนหุ้นจากหน้าปกงบ (dei) — ผูกกับงวดบัญชีที่ filing นั้นรายงาน (filed ภายใน 200 วันหลังสิ้นงวด)
        c = self._cover.get(cik)
        w["shares_cover"] = np.nan
        if c is not None:
            c = c[c["filed"] <= cutoff]
            for pe in w.index:
                m = c[(c["filed"] > pe) & (c["filed"] <= pe + pd.Timedelta(days=200))]
                if len(m):
                    w.at[pe, "shares_cover"] = m["val"].iloc[0]
        for col in list(FIELDS):
            if col not in w:
                w[col] = np.nan
        # หน้าปกงบ (dei) รวมทุก class ของหุ้น → ใช้เป็นหลัก; us-gaap บางบริษัทรายงานเป็นหน่วยอื่น
        # (v0 พบ: 0 หุ้น, scale ผิดหลักพัน/ล้าน, BRK รายงานเป็น Class A equivalent)
        # จำนวนหุ้น < 1 ล้าน = ข้อมูลผิดแน่นอนสำหรับบริษัทใน S&P 500 (v0 พบ TechnipFMC รายงาน 1 หุ้น) → ถือว่าไม่มี
        for c_ in ("shares_cover", "shares_out", "shares_wavg"):
            w[c_] = w[c_].where(w[c_] >= 1e6)
        w["shares"] = w["shares_cover"].combine_first(w["shares_out"]).combine_first(w["shares_wavg"])
        # ตรวจความสอดคล้อง: เทียบแหล่งหลักกับแหล่งสำรองตัวแรกที่มี
        alt = w["shares_out"].where(w["shares_cover"].notna(), w["shares_wavg"])
        w["shares_ratio"] = alt / w["shares"]
        w["gross_profit_any"] = w["gross_profit"].combine_first(w["revenue"] - w["cogs"])
        return w

    def rows_asof(self, cik: int, R: pd.Timestamp) -> dict:
        """คืน {"t": Series|None, "t1": ..., "t2": ...} ของงบปีล่าสุดและปีก่อนหน้า ณ วัน R"""
        out = {"t": None, "t1": None, "t2": None}
        w = self.wide_asof(cik, R)
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
            cand = w[(w.index >= lo) & (w.index <= hi)]
            if len(cand):
                out[k] = cand.iloc[-1].rename(cand.index[-1])
        return out
