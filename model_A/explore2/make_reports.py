"""
EXPLORE2 — กราฟ (.png) + notebook ที่รันแล้ว (.ipynb + .html ใน reports/) ของ round 008–012, T0 และตาราง top-5 3 แบบการลงทุน
python3 -m explore2.make_reports [round ...]
"""
import subprocess
import sys

import nbformat as nbf
import pandas as pd

from lib import panel, reporting, round_notebook, strategy as st
from lib.paths import INTERIM, MODEL_A
from rounds.round_003.run import monthly_universe

ROUNDS = {
    "008": ("t1_trend_filter", "Round 008 — T1 ตัวกรองแนวโน้ม (Faber / TSMOM)", "M"),
    "009": ("t2_factor_momentum", "Round 009 — T2 factor momentum", "A"),
    "010": ("t5_value_mom_quality", "Round 010 — T5 value + momentum + quality", "A"),
    "011": ("t3_insider", "Round 011 — T3 opportunistic insider buying", "M"),
    "012": ("t4_lazy_prices", "Round 012 — T4 Lazy Prices (ความเปลี่ยนแปลงของ 10-K)", "M"),
}
INTRO = ("ตัวเลขทั้งหมดอ่านจาก `results.csv` ที่ `run.py` ของ round นี้เขียนไว้ · ช่วงตัดสิน ก.ค. 2017 – มิ.ย. 2023 · "
         "⚠️ survivorship: ราคาของหุ้นที่ออกจากตลาดไปแล้วหายบางส่วน → ผลอาจดูดีเกินจริง · held-out (ตั้งแต่ ก.ค. 2023) ไม่ถูกใช้")


def ew_navs(ctx, dfm):
    ew = st.ew_holdings(dfm)
    out = {}
    for f in ("A", "M"):
        d = set(panel.rebalance_dates(ctx, f))
        out[f] = st.run_nav({R: v for R, v in ew.items() if R in d}, ctx.adj, 0.001)
    return out


def main(rounds):
    ctx = panel.Ctx()
    dfm, _ = monthly_universe(ctx)
    ew = ew_navs(ctx, dfm)
    for r in rounds:
        slug, title, f = ROUNDS[r]
        res = pd.read_csv(MODEL_A / "rounds" / f"round_{r}" / "results.csv")
        reporting.round_figure(res, r, title.split(" — ")[0] + " — Sharpe 2017-2022")
        nav = pd.read_parquet(INTERIM / f"r{r}_nav.parquet")
        cols = [c for c in nav.columns if c.startswith(f"r{r}_")]
        nav = nav[cols].join(ew[f].rename("EW"), how="outer").join(ctx.spy.rename("SPY"), how="left")
        nav = nav[nav.index >= pd.Timestamp("2011-06-30")].ffill()
        reporting.nav_figure(nav, cols + ["EW", "SPY"], r, "nav", f"Round {r} NAV (log, net 10 bps; EW rebalance {f})")
        round_notebook.build(r, slug, title, INTRO)
        print(r, "ok", flush=True)


def t0_and_top5():
    nb = nbf.v4.new_notebook()
    nb["cells"] = [
        nbf.v4.new_markdown_cell("# EXPLORE2 — T0 วินิจฉัย low accruals + top-5 ใน 3 แบบการลงทุน\n\n"
                                 "T0 เป็น diagnostic (ไม่นับ trial, ห้ามใช้แก้กฎ) · top-5 3 แบบการลงทุน = ข้อมูลอธิบายเท่านั้น ไม่ใช้เลือกกฎ\n\n" + INTRO),
        nbf.v4.new_code_cell('''import sys, pathlib; sys.path.insert(0, str(pathlib.Path.cwd().parent))
import pandas as pd
from IPython.display import Markdown, display
pd.set_option("display.width", 250)
display(Markdown(pathlib.Path("../explore2/t0/SUMMARY.md").read_text()))
for f in sorted(pathlib.Path("../explore2/t0").glob("*.csv")):
    print("==", f.name); display(pd.read_csv(f).round(4).head(40))'''),
        nbf.v4.new_code_cell('''display(Markdown("## top-5: lump-sum / DCA / ซื้อครั้งเดียว มิ.ย. 2017\\n\\n" + pathlib.Path("../explore2/top5/top5_modes.md").read_text()))'''),
    ]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    path = MODEL_A / "notebooks" / "explore2_t0_top5.ipynb"
    nbf.write(nb, path)
    subprocess.run(["python3", "-W", "ignore", "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace", str(path)], check=True, capture_output=True)
    subprocess.run(["python3", "-W", "ignore", "-m", "nbconvert", "--to", "html", "--output-dir", str(MODEL_A / "reports"), str(path)], check=True, capture_output=True)
    print("t0/top5 ok")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "t0" in args:
        t0_and_top5()
        args.remove("t0")
    main(args)
