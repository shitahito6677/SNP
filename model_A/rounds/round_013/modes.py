"""
Round 013 — จำลองการลงทุน 5 แบบ (ข้อมูลอธิบายเท่านั้น ไม่นับ trial ห้ามใช้เลือกกฎ) — HYPOTHESIS.md ข้อ 5–7
python3 -m rounds.round_013.modes   (ต้องรัน rounds.round_013.run ก่อน เพื่อให้มี scores.csv)

อุปมา: "รายชื่อ 20 ตัว" คือเมนูประจำปี — Y1/M1 สั่งเมนูใหม่เพิ่มแต่ไม่ทิ้งจานเก่า, Y2 เปลี่ยนทั้งโต๊ะเป็นเมนูใหม่ทุกปี,
Y3 สั่งครั้งเดียวแล้วนั่งกินยาว, M2 เติมจานทุกเดือนและทิ้งเฉพาะจานที่หลุดเมนูทุก มิ.ย.

การคิดเงิน (แบบดอลลาร์): ทุกเหตุการณ์ซื้อขายเสีย 10 bps ของมูลค่าที่ซื้อหรือขาย · ซื้อขายที่ Adj Close วันนั้น ·
หุ้นที่ราคาหยุด (ออกจากตลาด) มูลค่าค้างที่ราคาสุดท้าย (= เงินสด 0%) แล้วถูกขายในเหตุการณ์ซื้อครั้งถัดไป
"""
import json

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from lib import backtest as bt, criteria as cr, guard, panel, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_013.run import OUT, RULES, holdings, v1_p3_and_ew

COST = 0.001
Y_AMT, M_AMT = 100_000.0, 10_000.0
MODES = ["Y1_KEEP", "Y2_SWITCH", "Y3_BUYHOLD", "M1_KEEP", "M2_SWITCH"]
STARTS = [pd.Timestamp("2011-06-30"), pd.Timestamp("2017-06-30")]
STRATS = {"S1_FUNNEL": "funnel", "S2_WEIGHTED": "weighted", "SPY": None, "EW": None, "v1_P3": None}


class Sim:
    """พอร์ตแบบถือเป็นจำนวนหุ้น — prices = Adj Close (ปฏิทิน SPY) ที่ ffill แล้ว; last = วันสุดท้ายที่มีราคาจริงของแต่ละตัว"""

    def __init__(self, prices: pd.DataFrame, last: pd.Series, cost: float):
        self.P, self.last, self.c = prices, last, cost
        self.sh, self.cash = {}, 0.0
        self.sold = 0.0  # มูลค่าที่ขายสะสม (สำหรับ turnover)

    def px(self, d):
        return self.P.loc[d]

    def alive(self, t, d) -> bool:
        return pd.notna(self.last.get(t)) and self.last[t] >= d

    def value_of(self, d) -> dict:
        p = self.px(d)
        return {t: s * p[t] for t, s in self.sh.items()}

    def _sell(self, names, d):
        v = self.value_of(d)
        out = sum(v[t] for t in names)
        for t in names:
            del self.sh[t]
        self.cash += out * (1 - self.c)
        self.sold += out

    def _buy_equal(self, names, d):
        """ใช้เงินสดทั้งหมดซื้อ names เท่ากัน (ต้นทุนรวมในราคา)"""
        names = [t for t in names if self.alive(t, d)]
        if not names or self.cash <= 0:
            return
        x = self.cash / (len(names) * (1 + self.c))
        p = self.px(d)
        for t in names:
            self.sh[t] = self.sh.get(t, 0.0) + x / p[t]
        self.cash = 0.0

    def sell_dead(self, d):
        self._sell([t for t in self.sh if not self.alive(t, d)], d)

    def keep_buy(self, names, d):
        self.sell_dead(d)
        self._buy_equal(names, d)

    def switch_drop(self, names, d):
        """M2: ขายตัวที่ไม่อยู่ในรายชื่อใหม่ (รวมตัวที่ตายแล้ว) แล้วซื้อรายชื่อใหม่เท่ากันด้วยเงินสดทั้งหมด"""
        keep = {t for t in names if self.alive(t, d)}
        self._sell([t for t in self.sh if t not in keep], d)
        self._buy_equal(names, d)

    def switch_full(self, names, d):
        """Y2: ปรับทั้งพอร์ตให้เป็นรายชื่อใหม่เท่ากัน ซื้อขายเฉพาะส่วนต่าง — แก้ T + c·Σ|a − h| = W ให้ได้พอดี"""
        names = [t for t in dict.fromkeys(names) if self.alive(t, d)]
        if not names:
            self._sell(list(self.sh), d)
            return
        h = self.value_of(d)
        W = self.cash + sum(h.values())
        keys = set(h) | set(names)
        tgt = lambda T: {t: (T / len(names) if t in names else 0.0) for t in keys}
        f = lambda T: T + self.c * sum(abs(tgt(T)[t] - h.get(t, 0.0)) for t in keys) - W
        T = brentq(f, 0.0, W, xtol=1e-9)
        a, p = tgt(T), self.px(d)
        self.sold += sum(max(h.get(t, 0.0) - a[t], 0.0) for t in keys)
        self.sh = {t: a[t] / p[t] for t in names}
        self.cash = 0.0


def lists_at(hold: dict, d) -> list:
    Rs = [R for R in sorted(hold) if R <= d]
    return hold[Rs[-1]] if Rs else []


def run_mode(mode: str, hold: dict, start, P, last, cost: float, cal: pd.DatetimeIndex, month_ends: list) -> dict:
    """คืน daily value, flows และสถิติ ณ เหตุการณ์ของโหมดหนึ่ง"""
    Rs = [R for R in sorted(hold) if R >= start]
    if mode.startswith("Y"):
        ev = {R: Y_AMT for R in (Rs if mode != "Y3_BUYHOLD" else Rs[:1])}
    else:
        ev = {d: M_AMT for d in month_ends if d >= start}
    sim = Sim(P, last, cost)
    days = cal[(cal >= start) & (cal <= guard.CUTOFF)]
    val, cashv, nheld = pd.Series(np.nan, index=days), pd.Series(np.nan, index=days), pd.Series(np.nan, index=days)
    evd = sorted(ev)
    bounds = evd + [None]
    for k, d in enumerate(evd):
        sim.cash += ev[d]
        names = lists_at(hold, d)
        june = d in hold
        if mode in ("Y1_KEEP", "M1_KEEP", "Y3_BUYHOLD"):
            sim.keep_buy(names, d)
        elif mode == "Y2_SWITCH":
            sim.switch_full(names, d)
        elif mode == "M2_SWITCH":
            (sim.switch_drop if june else sim.keep_buy)(names, d)
        # มูลค่ารายวันจนถึงเหตุการณ์ถัดไป (ไม่รวมวันของเหตุการณ์ถัดไป)
        seg = days[(days >= d) & ((days < bounds[k + 1]) if bounds[k + 1] is not None else True)]
        if sim.sh:
            tk = list(sim.sh)
            sv = pd.Series(sim.sh)[tk]
            pv = P.loc[seg, tk]
            v = pv.mul(sv, axis=1)
            dead = pd.Series({t: last[t] for t in tk})
            deadmask = pd.DataFrame({t: seg > dead[t] for t in tk}, index=seg)
            val.loc[seg] = v.sum(axis=1) + sim.cash
            cashv.loc[seg] = v.where(deadmask, 0.0).sum(axis=1) + sim.cash
            nheld.loc[seg] = (~deadmask).sum(axis=1)
        else:
            val.loc[seg], cashv.loc[seg], nheld.loc[seg] = sim.cash, sim.cash, 0
    flows = pd.Series(ev).reindex(days).fillna(0.0)
    return {"value": val, "flows": flows, "cash": cashv, "n": nheld, "sold": sim.sold}


def xirr(flows: pd.Series, final: float, end) -> float:
    f = flows[flows > 0]
    t0 = f.index[0]
    ts = np.array([(d - t0).days / 365.25 for d in f.index])
    T = (pd.Timestamp(end) - t0).days / 365.25
    g = lambda r: sum(a * (1 + r) ** (T - ti) for a, ti in zip(f.values, ts)) - final
    return float(brentq(g, -0.99, 5.0))


def twr_index(value: pd.Series, flows: pd.Series) -> pd.Series:
    """ดัชนี time-weighted (หักเงินที่เติม): วันแรก = มูลค่า/เงินเข้า (สะท้อนต้นทุนซื้อครั้งแรก)"""
    r = (value - flows) / value.shift(1)
    r.iloc[0] = value.iloc[0] / flows.iloc[0]
    return r.cumprod()


def summarize(res: dict, rf: pd.Series) -> dict:
    v, fl = res["value"], res["flows"]
    end = v.index[-1]
    inv = float(fl.sum())
    idx = twr_index(v, fl)
    r = bt.monthly(idx)
    m = bt.metrics(r, rf, idx)
    years = (end - v.index[0]).days / 365.25
    me = v.resample("ME").last().index
    out = {"final": float(v.iloc[-1]), "invested": inv, "multiple": float(v.iloc[-1]) / inv,
           "xirr": xirr(fl, float(v.iloc[-1]), end), "twr_cagr": float(idx.iloc[-1] ** (1 / years) - 1),
           "sharpe": m["Sharpe"], "maxdd_twr": m["maxDD"], "maxdd_value": float((v / v.cummax() - 1).min()),
           "turnover_yr": res["sold"] / float(v.mean()) / years,
           "n_avg": float(res["n"].reindex(me, method="ffill").mean()), "n_end": int(res["n"].iloc[-1]),
           "cash_avg": float((res["cash"] / v).reindex(me, method="ffill").mean()), "cash_end": float(res["cash"].iloc[-1] / v.iloc[-1]),
           "years": years}
    for tag, w in (("info", cr.INFO), ("dec", cr.DEC)):
        if v.index[0] <= w[0]:
            mm = cr.win_metrics(idx, rf, w)
            out |= {f"{tag}_twr_cagr": mm["CAGR"], f"{tag}_sharpe": mm["Sharpe"], f"{tag}_maxdd": mm["maxDD"]}
    return out


def main():
    ctx = panel.Ctx()
    sc = pd.read_csv(OUT / "scores.csv", parse_dates=["R"])
    v1 = v1_p3_and_ew()
    lists = {"S1_FUNNEL": holdings(sc, "funnel"), "S2_WEIGHTED": holdings(sc, "weighted"),
             "SPY": {R: ["SPY"] for R in sorted(v1["P3"])}, "EW": v1["EW_v1u"], "v1_P3": v1["P3"]}
    cal = ctx.spy.index[ctx.spy.index <= guard.CUTOFF]
    tick = sorted({t for h in lists.values() for v in h.values() for t in v})
    adj = ctx.adj.reindex(columns=tick)
    last = adj.apply(lambda s: s.last_valid_index())
    P = adj.reindex(adj.index.union(cal)).ffill().reindex(cal)
    month_ends = [d for d in panel.rebalance_dates(ctx, "M")]
    assert max(month_ends) < guard.CUTOFF and cal.max() == guard.CUTOFF

    # ตรวจตัวจำลอง: Y2 ลงก้อนเดียวไม่เติมเงิน ต้องใกล้ lib.backtest.run (ต่างกันเฉพาะวิธีคิดต้นทุน — HYPOTHESIS ข้อ 7.2)
    check = {}
    for s in ("S1_FUNNEL", "S2_WEIGHTED", "EW", "v1_P3"):
        sim = Sim(P, last, COST)
        hold = lists[s]
        seg_vals = []
        Rs = sorted(hold)
        for k, R in enumerate(Rs):
            if k == 0:
                sim.cash = 1.0
            sim.switch_full(hold[R], R)
            stop = Rs[k + 1] if k + 1 < len(Rs) else guard.CUTOFF
            seg_vals.append(float(sum(sim.value_of(stop).values()) + sim.cash))
        ref = st.run_nav(hold, ctx.adj, COST)
        check[s] = {"sim_final": seg_vals[-1], "bt_final": float(ref.iloc[-1]), "rel_diff": seg_vals[-1] / float(ref.iloc[-1]) - 1}
    print("ตรวจ Y2 ก้อนเดียว vs lib.backtest.run:", {k: f"{v['rel_diff']:.2e}" for k, v in check.items()}, flush=True)
    for k, v in check.items():
        assert abs(v["rel_diff"]) < 5e-3, f"{k}: ตัวจำลองต่างจาก backtest เดิมเกินคาด"

    rows, series = [], {}
    for start in STARTS:
        for mode in MODES:
            for s, h in lists.items():
                res = run_mode(mode, h, start, P, last, 0.0 if s == "SPY" else COST, cal, month_ends)
                r = {"start": start.date().isoformat(), "mode": mode, "strategy": s} | summarize(res, ctx.rf)
                rows.append(r)
                series[f"{start.year}|{mode}|{s}"] = res["value"]
                series[f"{start.year}|{mode}|{s}|invested"] = res["flows"].cumsum()
            print(start.date(), mode, "done", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "modes_main.csv", index=False)
    pd.DataFrame(series).to_parquet(INTERIM / "r013_modes_values.parquet")

    # Y3_BUYHOLD ทุกปีเริ่ม 2011–2022
    y3 = []
    for R in sorted(lists["v1_P3"]):
        for s, h in lists.items():
            res = run_mode("Y3_BUYHOLD", h, R, P, last, 0.0 if s == "SPY" else COST, cal, month_ends)
            m = summarize(res, ctx.rf)
            y3.append({"start": R.date().isoformat(), "strategy": s, "multiple": m["multiple"], "cagr": m["xirr"],
                       "maxdd": m["maxdd_twr"], "cash_end": m["cash_end"], "n_end": m["n_end"], "years": m["years"]})
    y3 = pd.DataFrame(y3)
    y3.to_csv(OUT / "modes_y3_all_starts.csv", index=False)
    (OUT / "modes_check.json").write_text(json.dumps(check, indent=1))
    pd.set_option("display.width", 250)
    print(df[["start", "mode", "strategy", "multiple", "xirr", "twr_cagr", "sharpe", "maxdd_twr", "maxdd_value", "turnover_yr", "n_avg", "cash_end"]]
          .round(3).to_string())
    print(y3.pivot(index="start", columns="strategy", values="cagr").round(3).to_string())


if __name__ == "__main__":
    main()
