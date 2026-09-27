"""
ตรวจคุณภาพราคาใน sandbox/v2/data/prices/ → เขียน sandbox/v2/data/DATA_QUALITY.md

ตรวจ: วันที่ซ้ำ, ราคา ≤ 0, gap ยาวผิดปกติ (> 7 วันทำการของ SPY ที่ไม่มีราคา ระหว่างวันแรก–วันสุดท้าย),
ผลตอบแทน Adj Close รายวันผิดปกติ (|r| > 45% — อาจเป็น split ที่ไม่ถูกปรับ), split ที่ Adj Close ไม่ปรับ
(Close กระโดดเป็นอัตราส่วน split ทั่วไป แต่ Adj Close กระโดดตามไปด้วย)

    python3 -m sandbox.v2.scripts.data_quality
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg

SPLIT_RATIOS = [2, 3, 4, 5, 10, 20, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10, 1 / 20, 3 / 2, 2 / 3]
BIG_MOVE = 0.45
GAP_DAYS = 7


def check_one(t: str, d: pd.DataFrame, cal: pd.DatetimeIndex) -> list:
    issues = []
    if d.index.duplicated().any():
        issues.append(("duplicate_dates", int(d.index.duplicated().sum()), ""))
    px = d[["Open", "High", "Low", "Close", "Adj Close"]]
    bad = (px <= 0).any(axis=1)
    if t != cfg.RISK_FREE and bad.any():
        issues.append(("price_le_0", int(bad.sum()), str(d.index[bad][0].date())))
    c = cal[(cal >= d.index.min()) & (cal <= d.index.max())]
    missing = c.difference(d.index)
    if len(missing):
        # run ยาวสุดของวันทำการที่หายต่อเนื่อง
        pos = np.searchsorted(c, missing)
        runs = np.split(pos, np.where(np.diff(pos) != 1)[0] + 1)
        longest = max(runs, key=len)
        if len(longest) > GAP_DAYS:
            issues.append(("long_gap", int(len(longest)), f"{c[longest[0]].date()} → {c[longest[-1]].date()}"))
    if t == cfg.RISK_FREE:
        return issues
    r = d["Adj Close"].pct_change(fill_method=None)
    big = r[r.abs() > BIG_MOVE]
    for dt, v in big.items():
        cr = d["Close"].pct_change(fill_method=None).loc[dt] + 1
        near_split = any(abs(cr - s) / s < 0.03 for s in SPLIT_RATIOS)
        kind = "unadjusted_split_suspect" if near_split else "big_move"
        issues.append((kind, 1, f"{dt.date()} adj {v:+.1%} close×{cr:.3f}"))
    return issues


def main():
    man = json.loads(cfg.UNIVERSE_MANIFEST.read_text())
    spy = pd.read_parquet(cfg.PRICES_DIR / f"{cfg.BENCHMARK}.parquet")
    cal = spy.index
    rows = []
    for t, rec in sorted(man["tickers"].items()):
        f = cfg.PRICES_DIR / f"{t}.parquet"
        if rec.get("status") == "missing" or not f.exists():
            continue
        d = pd.read_parquet(f)
        for kind, n, detail in check_one(t, d, cal):
            rows.append({"ticker": t, "issue": kind, "n": n, "detail": detail})
    df = pd.DataFrame(rows, columns=["ticker", "issue", "n", "detail"])
    counts = man["counts"]
    missing = sorted(t for t, r in man["tickers"].items() if r.get("status") == "missing")
    partial = sorted(t for t, r in man["tickers"].items() if r.get("status") == "partial")
    lines = [
        "# DATA QUALITY — sandbox v2 prices",
        "",
        f"สร้างอัตโนมัติ `{datetime.now(timezone.utc).isoformat(timespec='seconds')}` โดย `scripts/data_quality.py` — ห้ามแก้ด้วยมือ",
        "",
        f"- PRICE_START `{man['price_start']}` · วันทำการล่าสุด `{man['latest_trading_day']}` · S&P 500 snapshot `{man['sp500_snapshot_date']}`",
        f"- สถานะ ticker: " + ", ".join(f"**{k}** {v}" for k, v in sorted(counts.items())),
        f"- data_hash `{man['data_hash']}`",
        "",
        "## สรุปปัญหาที่พบ",
        "",
    ]
    if df.empty:
        lines.append("ไม่พบปัญหา")
    else:
        lines.append("| ประเภท | จำนวน ticker | จำนวนครั้ง |")
        lines.append("|---|---|---|")
        for k, g in df.groupby("issue"):
            lines.append(f"| `{k}` | {g['ticker'].nunique()} | {int(g['n'].sum())} |")
        lines += ["", "## รายละเอียด", "", "| ticker | ประเภท | n | รายละเอียด |", "|---|---|---|---|"]
        for r in df.itertuples():
            lines.append(f"| {r.ticker} | `{r.issue}` | {r.n} | {r.detail} |")
    lines += ["", f"## missing ({len(missing)}) — ตัดทิ้ง (ผู้ใช้อนุญาต)", "", ", ".join(missing) or "—",
              "", f"## partial ({len(partial)})", "", "| ticker | ช่วง | เหตุผล |", "|---|---|---|"]
    for t in partial:
        r = man["tickers"][t]
        lines.append(f"| {t} | {r['start']} → {r['end']} | {r.get('reason') or ''} |")
    lines += ["", "หมายเหตุ: `big_move` = ผลตอบแทนรายวัน > 45% ที่ไม่ตรงอัตราส่วน split — ส่วนใหญ่เป็นเหตุการณ์จริง "
              "(ควบรวม/ข่าวแรง) แต่ควรตรวจด้วยตาก่อนเชื่อผล; `unadjusted_split_suspect` = Close กระโดดตรงอัตราส่วน split "
              "และ Adj Close กระโดดตาม → Yahoo อาจไม่ได้ปรับ split"]
    cfg.DATA_QUALITY_REPORT.write_text("\n".join(lines) + "\n")
    print(f"DATA_QUALITY: {len(df)} รายการ → {cfg.DATA_QUALITY_REPORT.relative_to(cfg.REPO)}")
    return df


if __name__ == "__main__":
    main()
