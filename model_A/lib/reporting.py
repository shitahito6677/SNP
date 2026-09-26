"""
รายงานอัตโนมัติ: LEADERBOARD.md จาก trials.csv และกราฟรายรอบ (.png ใน model_A/figures/) ให้แสดงบน GitHub ได้
"""

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lib import criteria as cr
from lib.paths import MODEL_A

FIG = MODEL_A / "figures"
FIG.mkdir(exist_ok=True)


def _b(x):
    return str(x).lower() == "true"


def leaderboard(top: int = 30) -> str:
    t = cr.load_trials().copy()
    t["cand"] = [(_b(a) and _b(b) and _b(c)) for a, b, c in zip(t["S1"], t["S2"], t["S6"])]
    t["d_sharpe_vs_ew"] = t["dec_sharpe"] - t["dec_sharpe_ew"]
    t = t.sort_values("dec_sharpe", ascending=False)
    lines = ["# LEADERBOARD (สร้างอัตโนมัติจาก `trials.csv` — ห้ามแก้ด้วยมือ)", "",
             f"จำนวน trial สะสม: **{len(t)}** · เรียงตาม Sharpe ช่วงตัดสิน (2017–2022, net 10 bps) · แสดง {min(top, len(t))} อันดับแรก", "",
             "เกณฑ์ย่อ: S1 = Sharpe ≥ EW+0.15 และ ≥ SPY+0.15, CAGR ≥ EW+2pt, MDD ไม่แย่กว่า EW เกิน 5pt (ที่ 10 และ 25 bps) · "
             "S2 = ชนะ EW ≥ 70% ของหน้าต่าง 36 เดือน · S6 = ถือเฉลี่ย ≥ 30, ต่ำสุด ≥ 20 · S3 (DSR) อยู่ใน results ของแต่ละ round", "",
             "| # | trial | ตระกูล | Sharpe | EW | SPY | CAGR | MDD | S1(10/25) | S2 | S6 (เฉลี่ย/ต่ำสุด) | Sharpe 2011–16 (EW) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(t.head(top).itertuples(), 1):
        lines.append(
            f"| {i} | `{r.trial_id}` | {r.family} | {r.dec_sharpe:.3f} | {r.dec_sharpe_ew:.3f} | {r.dec_sharpe_spy:.3f} | "
            f"{r.dec_cagr * 100:.1f}% | {r.dec_maxdd * 100:.1f}% | {'✅' if _b(r.S1_10) else '❌'}/{'✅' if _b(r.S1_25) else '❌'} | "
            f"{r.S2_share:.0%} | {r.S6_avg_n:.0f}/{r.S6_min_n:.0f} | {r.info_sharpe:.3f} ({r.info_sharpe_ew:.3f}) |")
    text = "\n".join(lines) + "\n"
    (MODEL_A / "LEADERBOARD.md").write_text(text)
    return text


def round_figure(results: pd.DataFrame, round_: str, title: str) -> str:
    r = results.sort_values("dec_sharpe")
    ew, spy = float(r["dec_sharpe_ew"].iloc[0]), float(r["dec_sharpe_spy"].iloc[0])
    fig, ax = plt.subplots(figsize=(9, max(3, 0.28 * len(r))))
    colors = ["#2e7d32" if _b(s) else "#9e9e9e" for s in r["S1"]]
    ax.barh(r["trial_id"].str.replace(f"r{round_}_", "", regex=False), r["dec_sharpe"], color=colors)
    ax.axvline(ew, color="#1565c0", ls="--", label=f"EW {ew:.2f}")
    ax.axvline(spy, color="#6a1b9a", ls=":", label=f"SPY {spy:.2f}")
    ax.axvline(max(ew, spy) + 0.15, color="#c62828", lw=1.5, label=f"S1 threshold {max(ew, spy) + 0.15:.2f}")
    ax.set_xlabel("Sharpe, decision window 2017-2022 (net 10 bps)")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", alpha=.3)
    fig.tight_layout()
    p = FIG / f"round_{round_}_sharpe.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return str(p.relative_to(MODEL_A))


def nav_figure(nav: pd.DataFrame, cols: list, round_: str, name: str, title: str) -> str:
    fig, ax = plt.subplots(figsize=(10, 4))
    for c in cols:
        s = nav[c].dropna()
        ax.plot(s.index, s / s.iloc[0], label=c, lw=2 if c == "EW" else 1.2)
    ax.axvline(pd.Timestamp("2017-06-30"), color="gray", ls="--")
    ax.set_yscale("log")
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    p = FIG / f"round_{round_}_{name}.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return str(p.relative_to(MODEL_A))
