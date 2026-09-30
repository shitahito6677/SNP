"""
Round 013 — กราฟ, ตาราง, RESULTS.md และ notebook v13_bmf20 (รันแล้ว + html) — ตัวเลขทุกตัวอ่านจากไฟล์ผลที่ run.py / modes.py เขียนไว้
python3 -m rounds.round_013.report
"""
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat as nbf
import pandas as pd

from lib import panel, reporting, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_013.modes import MODES

OUT = MODEL_A / "rounds" / "round_013"
FIG = MODEL_A / "figures"
LABEL = {"S1_FUNNEL": "S1 คัดสองชั้น (BM 100 ตัวแรก → F 20 ตัว)", "S2_WEIGHTED": "S2 คะแนน 0.6·BM + 0.4·F (20 ตัว)",
         "SPY": "SPY", "EW": "EW ทั้ง universe (ถือทุกตัวเท่ากัน)", "v1_P3": "v1 P3 (BM quintile บน + F ≥ 7)"}
ORDER = list(LABEL)
MODE_TH = {"Y1_KEEP": "Y1 ก้อนรายปี สะสมไม่ขาย", "Y2_SWITCH": "Y2 ก้อนรายปี ย้ายทั้งพอร์ต", "Y3_BUYHOLD": "Y3 ก้อนเดียว ถือยาว",
           "M1_KEEP": "M1 DCA สะสมไม่ขาย", "M2_SWITCH": "M2 DCA ย้ายทุก มิ.ย."}
COLORS = {"S1_FUNNEL": "#c62828", "S2_WEIGHTED": "#ef6c00", "SPY": "#6a1b9a", "EW": "#1565c0", "v1_P3": "#757575"}


def load():
    return (pd.read_csv(OUT / "results.csv"), pd.read_csv(OUT / "modes_main.csv"), pd.read_csv(OUT / "modes_y3_all_starts.csv"),
            pd.read_parquet(INTERIM / "r013_modes_values.parquet"))


def main_table(m: pd.DataFrame, start: str) -> str:
    g = m[m["start"] == start]
    head = "| กลยุทธ์ | " + " | ".join(MODE_TH[x] for x in MODES) + " |"
    lines = [head, "|---|" + "---|" * len(MODES)]
    for s in ORDER:
        cells = []
        for mode in MODES:
            r = g[(g["strategy"] == s) & (g["mode"] == mode)].iloc[0]
            cells.append(f"{r.multiple:.2f} · {r.xirr:.1%}/ปี")
        lines.append(f"| {LABEL[s]} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def y3_table(y3: pd.DataFrame) -> str:
    p = y3.pivot(index="start", columns="strategy", values="cagr")[ORDER]
    lines = ["| ปีเริ่ม (ถือถึง 30 มิ.ย. 2023) | " + " | ".join(ORDER) + " |", "|---|" + "---|" * len(ORDER)]
    for d, r in p.iterrows():
        lines.append(f"| {d[:7]} | " + " | ".join(f"{v:.1%}" for v in r) + " |")
    return "\n".join(lines)


def y3_summary(y3: pd.DataFrame) -> pd.DataFrame:
    p = y3.pivot(index="start", columns="strategy", values="cagr")
    rows = []
    for s in ("S1_FUNNEL", "S2_WEIGHTED", "v1_P3"):
        rows.append({"strategy": s, "min": p[s].min(), "median": p[s].median(), "max": p[s].max(),
                     "beat_SPY": int((p[s] > p["SPY"]).sum()), "beat_EW": int((p[s] > p["EW"]).sum()), "n_starts": len(p)})
    return pd.DataFrame(rows)


def figures(res, m, vals, ctx):
    reporting.round_figure(res, "013", "Round 013 BMF20 - Sharpe 2017-2022")
    nav = pd.read_parquet(INTERIM / "r013_nav.parquet")
    nav = nav.rename(columns={"EW": "EW U(d)", "EW_v1u": "EW v1 universe", "P3": "v1 P3"}).join(ctx.spy.rename("SPY"), how="left")
    nav = nav[nav.index >= pd.Timestamp("2011-06-30")].ffill()
    reporting.nav_figure(nav, ["r013_BMF20_FUNNEL", "r013_BMF20_WEIGHTED", "EW U(d)", "EW v1 universe", "v1 P3", "SPY"], "013", "nav",
                         "Round 013 NAV (log, net 10 bps, annual June rebalance, lump sum no top-ups)")
    for start in ("2011", "2017"):
        fig, axes = plt.subplots(1, 5, figsize=(20, 4), sharey=False)
        for ax, mode in zip(axes, MODES):
            for s in ORDER:
                v = vals[f"{start}|{mode}|{s}"].dropna()
                inv = vals[f"{start}|{mode}|{s}|invested"].reindex(v.index)
                ax.plot(v.index, v / inv, color=COLORS[s], lw=2 if s in ("S1_FUNNEL", "S2_WEIGHTED") else 1.2, label=s)
            ax.set_title(f"{mode} (start {start}-06)")
            ax.axhline(1, color="black", lw=.6)
            ax.grid(alpha=.3)
        axes[0].set_ylabel("portfolio value / money put in")
        axes[0].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(FIG / f"round_013_modes_{start}.png", dpi=100)
        plt.close(fig)
    y3 = pd.read_csv(OUT / "modes_y3_all_starts.csv")
    p = y3.pivot(index="start", columns="strategy", values="cagr")[ORDER]
    ax = p.plot.bar(figsize=(12, 4), color=[COLORS[c] for c in ORDER], width=.8)
    ax.set_xticklabels([d[:4] for d in p.index], rotation=0)
    ax.set_ylabel("CAGR to 2023-06-30")
    ax.set_title("Y3 buy once & hold: annual return by start year (June)")
    ax.grid(axis="y", alpha=.3)
    ax.figure.tight_layout()
    ax.figure.savefig(FIG / "round_013_y3_starts.png", dpi=100)
    plt.close(ax.figure)


def facts(res, m, y3) -> dict:
    """ตัวเลขที่ใช้ในข้อความสรุป — อ่านจากไฟล์ผลเท่านั้น"""
    r = res.set_index("trial_id")
    f = {k: r.loc[t] for k, t in (("F", "r013_BMF20_FUNNEL"), ("W", "r013_BMF20_WEIGHTED"))}
    sc = pd.read_csv(OUT / "scores.csv", parse_dates=["R"])
    n_u = sc.groupby("R").size()
    beats = {}
    for start in ("2011-06-30", "2017-06-30"):
        g = m[m["start"] == start].set_index(["mode", "strategy"])["multiple"]
        for s in ("S1_FUNNEL", "S2_WEIGHTED"):
            beats[(start, s)] = [x for x in MODES if g[(x, s)] > g[(x, "SPY")] and g[(x, s)] > g[(x, "EW")]]
    from lib import prices, guard
    adj = prices.load_adj_close()
    last = adj[sorted(sc["yahoo"].unique())].apply(lambda s: s.last_valid_index())
    ov = sc.groupby("R")[["sel_funnel", "sel_weighted"]].apply(lambda g: int((g.sel_funnel & g.sel_weighted).sum()))
    return {"f": f, "n_u": n_u, "beats": beats, "y3s": y3_summary(y3), "chk": pd.read_json(OUT / "modes_check.json").T,
            "funnel_counts": funnel_counts(), "n_tick": len(last), "n_dead": int((last < guard.CUTOFF).sum()), "ov": ov}


def funnel_counts() -> str:
    p = pd.read_parquet(INTERIM / "panel_annual.parquet").drop_duplicates(["R", "ticker"])
    lines = ["  | R | สมาชิก | การเงิน | ไม่มีราคา/CIK | ไม่มี F หรือ BM | universe |", "  |---|---|---|---|---|---|"]
    for R, g in p.groupby("R"):
        nf = g[~g["financial"]]
        u = g[g["in_U"]].drop_duplicates("yahoo")
        ok = u[u["V_BM"].notna() & u["A_FSCORE"].notna()]
        lines.append(f"  | {R.year} | {len(g)} | {int(g['financial'].sum())} | {len(nf) - len(u)} | {len(u) - len(ok)} | {len(ok)} |")
    return "\n".join(lines)


def results_md(res, m, y3) -> str:
    x = facts(res, m, y3)
    F, W = x["f"]["F"], x["f"]["W"]
    rows = []
    for tid, r in (("r013_BMF20_FUNNEL", F), ("r013_BMF20_WEIGHTED", W)):
        rows.append(f"| `{tid}` | {r.dec_sharpe:.3f} | {r.dec_sharpe_ew:.3f} | {r.dec_sharpe_spy:.3f} | {r.dec_cagr:.1%} ({r.dec_cagr_ew:.1%}) | "
                    f"{r.dec_maxdd:.1%} ({r.dec_maxdd_ew:.1%}) | {'✅' if r.S1_10 else '❌'}/{'✅' if r.S1_25 else '❌'} | {r.S2_share:.0%} | "
                    f"{r.DSR:.3f} | {r.S6_avg_n:.0f}/{r.S6_min_n:.0f} ❌ | {r.info_sharpe:.3f} ({r.info_sharpe_ew:.3f}) | {r.info_cagr:.1%} ({r.info_cagr_ew:.1%}) |")
    b = x["beats"]
    fmt_b = lambda k: ", ".join(b[k]) if b[k] else "ไม่มี"
    ys = x["y3s"].set_index("strategy")
    chk = x["chk"]
    return f"""# Round 013 — BMF20: หุ้น 20 ตัวจาก BM + F-score + การลงทุน 5 แบบ — **ไม่มีผู้เข้ารอบ (ระดับ C ทั้งสองกฎ)**

สเปก: [HYPOTHESIS.md](HYPOTHESIS.md) (commit ก่อนรัน) · โค้ด: `run.py` (trial), `modes.py` (5 โหมด), `report.py` (ตาราง/กราฟ/notebook)

## ข้อมูล
- universe = universe ของ v1 variant main (ตรวจแล้วตรงทุกปี): จำนวนหุ้นต่อปี {", ".join(f"{d.year}: {n}" for d, n in x["n_u"].items())}
  — ต่ำกว่า 300–400 ที่สเปกคาดในช่วงแรก; ที่มาของจำนวน (สมาชิก → ตัดการเงิน → ตัดตัวที่ไม่มีราคา/จับคู่ไม่ได้ → ตัดตัวที่ไม่มี F-score/BM):
{x['funnel_counts']}
- เลือกได้ 20 ตัวครบทุกปีทั้งสองกฎ · สองกฎเลือกหุ้นซ้ำกัน {x["ov"].min()}–{x["ov"].max()} ตัวต่อปี (`scores.csv`)
- ตัวเทียบ v1 P3 และ EW ของ universe v1 สร้างใหม่ด้วยโค้ด v1 เดิม ได้ NAV ตรงกับ `v1_nav.parquet` (ต่างสูงสุด < 1e-15)
- **survivorship (สำคัญ):** หุ้นทั้ง {x["n_tick"]} ตัวที่เคยอยู่ใน universe มีราคาถึง 30 มิ.ย. 2023 ครบทุกตัว (ตัวที่ราคาหยุดก่อน: {x["n_dead"]} ตัว) — หุ้นที่ถูกซื้อกิจการ/ล้มละลายไม่มีราคาใน Yahoo
  จึงไม่เคยเข้า universe ตั้งแต่แรก → กฎ "ออกจากตลาด = เงินสด" ไม่ถูกใช้เลย (เงินสด 0% ทุกโหมด) และผลทุกแถวน่าจะดูดีกว่าจริง
  โดยเฉพาะกลยุทธ์หุ้นถูก (BM สูง) ซึ่งมีโอกาสเป็นหุ้นที่ถูกถอดออกมากกว่า

## ผลตามเกณฑ์ (Y2_SWITCH ลงก้อนเดียวไม่เติมเงิน = backtest มาตรฐาน) — 2 trial → สะสม **{int(F.N_trials)}**
ช่วงตัดสิน ก.ค. 2017 – มิ.ย. 2023, rebalance มิ.ย., 20 ตัวเท่ากัน, net 10 bps · EW = U(d) ตาม PREREG_AUTORUN
| trial | Sharpe | EW | SPY | CAGR (EW) | MaxDD (EW) | S1 (10/25) | S2 | DSR | S6 เฉลี่ย/ต่ำสุด | ช่วง 2011–16 Sharpe (EW) | ช่วง 2011–16 CAGR (EW) |
|---|---|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

- ผลตอบแทนส่วนเกินเทียบ EW ช่วงตัดสิน: FUNNEL {F.dec_active_ann:+.1%}/ปี (Newey-West t {F.dec_nw_t:.2f}), WEIGHTED {W.dec_active_ann:+.1%}/ปี (t {W.dec_nw_t:.2f})
- S6 ตกโดยโครงสร้าง (20 ตัว < 30) ตามที่ประกาศใน HYPOTHESIS → ระดับ C ไม่ว่าผลอื่นเป็นอย่างไร; S4/S5 ไม่ประเมิน (ไม่มีผู้เข้ารอบ)
- ช่วงประกอบ 2011–2016 ทั้งสองกฎชนะ EW (Sharpe และ CAGR สูงกว่า) แต่ช่วงตัดสินแพ้ชัด และขาดทุนหนักสุดลึกกว่า EW {100*(F.dec_maxdd_ew-F.dec_maxdd):.0f} / {100*(W.dec_maxdd_ew-W.dec_maxdd):.0f} จุด

## การลงทุน 5 แบบ (ข้อมูลอธิบาย — ห้ามใช้เลือกกฎ) · ตัวเลข = มูลค่าสุดท้าย ÷ เงินที่ใส่ · ผลตอบแทนต่อปีแบบถ่วงเงิน (XIRR; Y3 = CAGR)
ต้นทุน 10 bps ต่อการซื้อ/ขาย (SPY ไม่มีต้นทุน) · ทุกแถวใช้กระแสเงินเดียวกันในแต่ละคอลัมน์ · จบ 30 มิ.ย. 2023

**จุดเริ่ม มิ.ย. 2011**

{main_table(m, "2011-06-30")}

**จุดเริ่ม มิ.ย. 2017 (ช่วงตัดสิน)**

{main_table(m, "2017-06-30")}

- โหมดที่กฎ "ได้เงินมากกว่าทั้ง SPY และ EW": เริ่ม 2011 — S1: {fmt_b(("2011-06-30", "S1_FUNNEL"))}; S2: {fmt_b(("2011-06-30", "S2_WEIGHTED"))} ·
  เริ่ม 2017 — S1: {fmt_b(("2017-06-30", "S1_FUNNEL"))}; S2: {fmt_b(("2017-06-30", "S2_WEIGHTED"))}
- ตัวชี้วัดครบ (TWR CAGR, Sharpe, max drawdown ทั้งแบบดิบและหักเงินเติม, turnover, จำนวนหุ้นที่ถือ, เงินสด, แยกช่วง) อยู่ใน `modes_main.csv` และ notebook
- ตรวจตัวจำลอง: Y2 ลงก้อนเดียวไม่เติมเงินในตัวจำลอง vs `lib/backtest.run` ต่างกันที่มูลค่าสุดท้าย {chk["rel_diff"].abs().max():.1e} (สัมพัทธ์)
  — มาจากวิธีคิดต้นทุนต่างกัน (ตัวจำลองคิดตามดอลลาร์ที่ซื้อขายจริง, backtest เดิมคิดเป็นสัดส่วน NAV)

## Y3 ซื้อครั้งเดียวถือยาว — ทุกปีเริ่ม 2011–2022 (ขึ้นกับโชคของปีเริ่มแค่ไหน)
{y3_table(y3)}

| กฎ | CAGR ต่ำสุด | มัธยฐาน | สูงสุด | ชนะ SPY (ปีเริ่ม) | ชนะ EW (ปีเริ่ม) |
|---|---|---|---|---|---|
""" + "\n".join(f"| {r.Index} | {r.min:.1%} | {r.median:.1%} | {r.max:.1%} | {int(r.beat_SPY)}/{int(r.n_starts)} | {int(r.beat_EW)}/{int(r.n_starts)} |"
                for r in ys.itertuples()) + f"""

⚠️ ปีเริ่มหลัง ๆ ถือสั้นมาก (เริ่ม 2022 = 1 ปี) — ใช้ดูการกระจาย ไม่ใช่เทียบรายปี

## การตีความ
- ตรงกับความคาดหวังใน HYPOTHESIS: BM มี IC ติดลบในช่วงตัดสิน การเลือกหุ้นถูกที่สุด 20 ตัว (แม้กรองด้วย F-score) จึงแพ้ EW ในช่วง 2017–2023
  และการกระจุก 20 ตัวทำให้แกว่งแรงขึ้นมาก (MaxDD {F.dec_maxdd:.0%} / {W.dec_maxdd:.0%} เทียบ EW {F.dec_maxdd_ew:.0%})
- ช่วง 2011–2016 หุ้นถูก + F สูงทำได้ดีกว่า EW แต่ 2017–2023 แพ้ → ผลขึ้นกับยุค ไม่ทนทาน
- โหมดสะสมไม่ขาย (Y1/M1) ที่เริ่ม 2011 ดูดีกว่า EW/SPY เพราะหุ้นที่ซื้อช่วงแรก (ยุคที่ value ยังได้ผล) ถูกถือต่อ — เป็นคำอธิบายที่ **ยังไม่ได้ทดสอบ**
- XIRR ของ Y2/M2 อาจสูงกว่า CAGR แบบ time-weighted มากเมื่อเงินก้อนหลัง ๆ เข้าช่วงที่ตลาดดี (เช่น v1 P3 เริ่ม 2017) — เป็นผลของจังหวะเงินเข้า ไม่ใช่ความสามารถของกฎ
"""


def summary_md(res, m, y3) -> str:
    x = facts(res, m, y3)
    F, W = x["f"]["F"], x["f"]["W"]
    return f"""## สรุป (ภาษาง่าย)

**ระดับผล: S1_FUNNEL = C, S2_WEIGHTED = C** (ไม่มีกฎใดผ่านเกณฑ์ "ชนะขาดรอย")
- ช่วงตัดสิน 2017–2023 (ปรับพอร์ตปีละครั้งตามกฎมาตรฐาน): Sharpe {F.dec_sharpe:.2f} และ {W.dec_sharpe:.2f} เทียบตลาดเฉลี่ย EW {F.dec_sharpe_ew:.2f} และ SPY {F.dec_sharpe_spy:.2f}
  → แพ้ทั้งคู่; กำไร {F.dec_cagr:.1%} / {W.dec_cagr:.1%} ต่อปี เทียบ EW {F.dec_cagr_ew:.1%}; ขาดทุนหนักสุด {F.dec_maxdd:.0%} / {W.dec_maxdd:.0%} เทียบ EW {F.dec_maxdd_ew:.0%}
- ช่วง 2011–2016 กลับชนะ EW (Sharpe {F.info_sharpe:.2f} / {W.info_sharpe:.2f} เทียบ {F.info_sharpe_ew:.2f}) → ผลขึ้นกับยุค ไม่ทนทาน
- DSR {F.DSR:.3f} / {W.DSR:.3f} (ต้อง ≥ 0.95) และถือแค่ 20 ตัว (เกณฑ์ S6 ต้อง ≥ 30) → ตกโดยโครงสร้างอยู่แล้ว

**อุปมา:** เหมือนเลือกนักวิ่ง "ค่าตัวถูก + สุขภาพดี" 20 คน — ช่วงปี 2011–2016 ทีมนี้วิ่งดี แต่ช่วง 2017–2023 สนามเปลี่ยนเป็นยุคที่นักวิ่งค่าตัวแพง (หุ้นเติบโต) ชนะ
ทีมที่คัดมาจึงตามหลัง และเพราะมีแค่ 20 คน วันที่ทีมล้มก็ล้มหนักกว่าทีมใหญ่

**ข้อจำกัด**
- **Survivorship:** ทุกหุ้นใน universe มีราคาถึงปี 2023 ครบ (หุ้นที่หายจากตลาดไม่มีข้อมูลตั้งแต่แรก) → ผลน่าจะดูดีเกินจริง โดยเฉพาะหุ้นถูก
- **20 ตัวแกว่งแรง:** ขาดทุนหนักสุดลึกกว่าตลาดเฉลี่ยมาก ผลรายปีกระโดดตามหุ้นไม่กี่ตัว
- **ช่วงเวลาสั้น:** 12 ปี (ตัดสิน 6 ปี) มีโควิดและยุคหุ้นเติบโต · universe ปีแรก ๆ เล็ก ({x["n_u"].iloc[0]} ตัวในปี {x["n_u"].index[0].year})
- กลุ่มอุตสาหกรรมเป็น SIC ไม่ใช่ GICS · SPY ไม่คิดต้นทุน (ตาม PREREG) · XIRR ขึ้นกับจังหวะเงินเข้า

**ทดสอบแล้ว vs ยังเป็นไอเดีย**
| ทดสอบแล้ว (มีตัวเลขจากการรันจริง) | ยังเป็นไอเดีย (ไม่ได้ทดสอบ) |
|---|---|
| 2 กฎเลือก 20 ตัว ตามเกณฑ์ S1/S2/S3/S6 (2 trial, สะสม {int(F.N_trials)}) | ทำไมโหมดสะสมไม่ขายที่เริ่ม 2011 ดูดี (น่าจะมาจากหุ้นชุดแรก) |
| 5 โหมด × 2 จุดเริ่ม เทียบ SPY / EW / v1 P3 ด้วยกระแสเงินเดียวกัน | ถ้าเพิ่มเป็น 30+ ตัวจะผ่าน S6 ไหม (ต้องเป็น trial ใหม่ + HYPOTHESIS ใหม่) |
| Y3 ทุกปีเริ่ม 2011–2022 | ผลใน held-out (ก.ค. 2023 เป็นต้นไป) — ยังล็อก ไม่แตะ |
| ตัวเทียบ v1 P3/EW ตรงกับ v1 เดิมเป๊ะ; ตัวจำลองตรงกับ backtest มาตรฐาน | ผลเมื่อมีข้อมูลหุ้นที่ถูกถอดออกจากตลาด (ต้องซื้อข้อมูล) |
"""


INTRO = """# v13 — BMF20: เลือกหุ้น 20 ตัวจาก "ความถูก" (BM) + "ความแข็งแรงของงบ" (F-score) และลงทุน 5 แบบ

> ข้อมูลอธิบาย + การประเมินตามเกณฑ์ของ round 013 · ช่วงข้อมูล มิ.ย. 2011 – 30 มิ.ย. 2023 (held-out ตั้งแต่ ก.ค. 2023 **ไม่ถูกใช้**)

## 2 กฎเลือกหุ้น (อุปมา: คัดนักวิ่ง 20 คนจากนักวิ่ง ~170–355 คน)
- **BM (book-to-market)** = มูลค่าทางบัญชี ÷ มูลค่าตลาด → ยิ่งสูง หุ้นยิ่ง "ถูก" เทียบกับทรัพย์สินที่บริษัทมี (เหมือนนักวิ่งค่าตัวถูก)
- **F-score (Piotroski 0–9)** = เช็กลิสต์ 9 ข้อว่างบการเงินแข็งแรงขึ้นไหม (กำไร, เงินสด, หนี้, สภาพคล่อง, ประสิทธิภาพ) → เหมือนผลตรวจสุขภาพ
- **S1 คัดสองชั้น (FUNNEL):** เอา 100 คนค่าตัวถูกที่สุดก่อน แล้วเลือก 20 คนที่สุขภาพดีที่สุดใน 100 คนนั้น → "ถูก" มาก่อน แล้วค่อยดูสุขภาพ
- **S2 ให้คะแนนรวม (WEIGHTED):** ทุกคนได้คะแนน = 60% ความถูก + 40% สุขภาพ (วัดเป็นอันดับเปอร์เซ็นไทล์) แล้วเลือก 20 คะแนนสูงสุด → คนที่ถูกปานกลางแต่สุขภาพดีมากก็มีโอกาส

## 5 แบบการลงทุน (อุปมา: รายชื่อ 20 ตัวคือ "เมนูประจำปี" ที่เปลี่ยนทุก มิ.ย.)
| แบบ | เงินเข้า | ทำอะไร | อุปมา |
|---|---|---|---|
| **Y1_KEEP** | ก้อนเท่ากันทุก มิ.ย. | เงินใหม่ซื้อเมนูปีนี้ ของเดิมเก็บไว้ไม่ขาย | สั่งจานใหม่ทุกปี ไม่ทิ้งจานเก่า → จานบนโต๊ะเพิ่มเรื่อย ๆ |
| **Y2_SWITCH** | ก้อนเท่ากันทุก มิ.ย. | ปรับทั้งพอร์ตเป็นเมนูปีนี้ 20 ตัวเท่ากัน (ซื้อขายเฉพาะส่วนต่าง) | เปลี่ยนทั้งโต๊ะเป็นเมนูใหม่ทุกปี |
| **Y3_BUYHOLD** | ก้อนเดียวปีแรก | ซื้อเมนูปีแรก ถือไม่แตะจนจบ | สั่งครั้งเดียวแล้วนั่งกินยาว |
| **M1_KEEP** | เท่ากันทุกสิ้นเดือน (DCA) | เงินใหม่ซื้อเมนูล่าสุด ไม่ขาย | เติมจานทุกเดือน ไม่ทิ้งอะไร |
| **M2_SWITCH** | เท่ากันทุกสิ้นเดือน (DCA) | เหมือน M1 + ทุก มิ.ย. ขายตัวที่หลุดเมนูใหม่ แล้วซื้อเมนูใหม่ | เติมทุกเดือน และเก็บจานที่ไม่อยู่ในเมนูใหม่ทุก มิ.ย. |

ตัวเทียบใช้กระแสเงิน **แบบเดียวกันทุกโหมด**: SPY, EW (ซื้อทุกตัวใน universe เท่ากัน), v1 P3 (BM quintile บน + F ≥ 7)
· ต้นทุน 10 bps ต่อการซื้อ/ขาย · **มีเพียง Y2 แบบลงก้อนเดียวไม่เติมเงินที่ใช้ตัดสินตามเกณฑ์ S1–S7** — โหมดอื่นเป็นข้อมูลอธิบาย ห้ามใช้เลือกกฎ
"""


def notebook(summary: str):
    nb = nbf.v4.new_notebook()
    C = [nbf.v4.new_markdown_cell(INTRO)]
    C.append(nbf.v4.new_code_cell('''import sys, pathlib; sys.path.insert(0, str(pathlib.Path.cwd().parent))
import pandas as pd
from IPython.display import Image, Markdown, display
from lib import report
from rounds.round_013 import report as rp
report.banner()
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 200)
D = pathlib.Path("../rounds/round_013")
res, m, y3 = pd.read_csv(D / "results.csv"), pd.read_csv(D / "modes_main.csv"), pd.read_csv(D / "modes_y3_all_starts.csv")
sc = pd.read_csv(D / "scores.csv", parse_dates=["R"])
print("จำนวนหุ้นใน universe ต่อปี:", {d.year: n for d, n in sc.groupby("R").size().items()})'''))
    C.append(nbf.v4.new_markdown_cell("## 1) ผลตามเกณฑ์ S1–S7 (Y2_SWITCH ลงก้อนเดียวไม่เติมเงิน = backtest มาตรฐาน)"))
    C.append(nbf.v4.new_code_cell('''cols = ["trial_id","dec_sharpe","dec_sharpe_ew","dec_sharpe_spy","dec_cagr","dec_cagr_ew","dec_maxdd","dec_maxdd_ew","dec_active_ann","dec_nw_t",
        "S1_10","S1_25","S2_share","DSR","N_trials","S6_avg_n","S6_min_n","info_sharpe","info_sharpe_ew","info_cagr","info_cagr_ew"]
display(res[cols].set_index("trial_id").T.round(3))
display(Image(filename="../figures/round_013_sharpe.png")); display(Image(filename="../figures/round_013_nav.png"))'''))
    C.append(nbf.v4.new_markdown_cell("## 2) ตารางหลัก: เงิน 1 บาทที่ใส่ → กี่บาท · ผลตอบแทนต่อปี (XIRR; Y3 = CAGR)"))
    C.append(nbf.v4.new_code_cell('''for s in ("2011-06-30", "2017-06-30"):
    display(Markdown(f"**จุดเริ่ม {s[:7]}**\\n\\n" + rp.main_table(m, s)))'''))
    C.append(nbf.v4.new_markdown_cell("## 3) ตัวชี้วัดครบทุกโหมด (TWR = หักผลของเงินที่เติม) และแยกช่วง 2011–2016 / 2017–2023"))
    C.append(nbf.v4.new_code_cell('''k = ["start","mode","strategy","final","invested","multiple","xirr","twr_cagr","sharpe","maxdd_twr","maxdd_value","turnover_yr","n_avg","n_end","cash_avg","cash_end"]
display(m[k].round(3))
print("แยกช่วง (จากการรันจุดเริ่ม 2011; ดัชนี time-weighted)")
display(m[m.start == "2011-06-30"][["mode","strategy","info_twr_cagr","info_sharpe","info_maxdd","dec_twr_cagr","dec_sharpe","dec_maxdd"]].round(3))'''))
    C.append(nbf.v4.new_markdown_cell("## 4) กราฟมูลค่าพอร์ต ÷ เงินที่ใส่ แต่ละโหมด เทียบ SPY และ EW"))
    C.append(nbf.v4.new_code_cell('''for f in ("round_013_modes_2011.png", "round_013_modes_2017.png"): display(Image(filename=f"../figures/{f}"))'''))
    C.append(nbf.v4.new_markdown_cell("## 5) Y3 ซื้อครั้งเดียวถือยาว ทุกปีเริ่ม 2011–2022 — ขึ้นกับโชคของปีเริ่มแค่ไหน"))
    C.append(nbf.v4.new_code_cell('''display(Markdown(rp.y3_table(y3))); display(rp.y3_summary(y3).round(3))
display(Image(filename="../figures/round_013_y3_starts.png"))'''))
    C.append(nbf.v4.new_markdown_cell("## 6) รายชื่อ 20 ตัวต่อปี (2017–2022) พร้อมกลุ่มอุตสาหกรรม (SIC) — กระจุกตัวไหม"))
    C.append(nbf.v4.new_code_cell('''for rule in ("funnel", "weighted"):
    p = pd.read_csv(D / f"picks_{rule}.csv", parse_dates=["R"])
    q = p[p.R.dt.year >= 2017]
    display(Markdown(f"### {rule}: หุ้นที่เลือก"))
    display(q.assign(ปี=q.R.dt.year).pivot_table(index="rank", columns="ปี", values="ticker", aggfunc="first"))
    display(q.assign(ปี=q.R.dt.year).pivot_table(index="rank", columns="ปี", values="sic_group", aggfunc="first"))
    c = q.groupby([q.R.dt.year, "sic_group"]).size().unstack(fill_value=0)
    print(f"{rule}: จำนวนหุ้นในกลุ่มที่มากที่สุดต่อปี:", c.max(axis=1).to_dict(), "| กลุ่ม:", c.idxmax(axis=1).to_dict())
    display(c.T.sort_values(c.index.max(), ascending=False))
display(Markdown("สัดส่วนกลุ่มใน universe ทั้งหมด (เทียบ): " + ", ".join(f"{k} {v:.0%}" for k, v in sc.groupby("sic_group").size().div(len(sc)).sort_values(ascending=False).head(8).items())))'''))
    C.append(nbf.v4.new_markdown_cell(summary))
    nb["cells"] = C
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    path = MODEL_A / "notebooks" / "v13_bmf20.ipynb"
    nbf.write(nb, path)
    subprocess.run(["python3", "-W", "ignore", "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace", str(path)], check=True, capture_output=True)
    subprocess.run(["python3", "-W", "ignore", "-m", "nbconvert", "--to", "html", "--output-dir", str(MODEL_A / "reports"), str(path)], check=True, capture_output=True)
    return path


def main():
    ctx = panel.Ctx()
    res, m, y3, vals = load()
    figures(res, m, vals, ctx)
    (OUT / "RESULTS.md").write_text(results_md(res, m, y3))
    s = summary_md(res, m, y3)
    (OUT / "SUMMARY_TH.md").write_text(s)
    print(notebook(s))


if __name__ == "__main__":
    main()
