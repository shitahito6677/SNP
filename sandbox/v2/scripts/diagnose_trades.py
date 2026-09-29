"""
Q0 — สาเหตุจริงของ SELL/BUY แต่ละรายการ (อ่านบันทึกตอนรัน ไม่รันใหม่ ไม่แก้อะไร)

    python3 -m sandbox.v2.scripts.diagnose_trades <job_id | experiment_id> [--ticker NOW --ticker FTNT]

พิมพ์: จำนวน trade ต่อสาเหตุ (ซื้อ/ขาย) + รายการของหุ้นที่ระบุ พร้อม note ของ condition วันนั้นและหุ้นอื่นที่เป้าเปลี่ยน
"""

from __future__ import annotations

import argparse
import collections
import sqlite3
from pathlib import Path

import pandas as pd

from sandbox.v2 import config as cfg, trade_causes


def result_dir(rid: str) -> Path:
    d = cfg.EXPERIMENTS_DIR / rid
    if d.exists():
        return d
    r = sqlite3.connect(cfg.JOBS_DB).execute("SELECT result_dir FROM jobs WHERE id=?", (rid,)).fetchone()
    if not r or not r[0]:
        raise SystemExit(f"ไม่พบผล {rid}")
    return Path(r[0])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("rid")
    ap.add_argument("--ticker", action="append", default=[])
    a = ap.parse_args(argv)
    d = result_dir(a.rid)
    tr = trade_causes.classify_dir(d)
    print(f"# {a.rid} — trade {len(tr)} รายการ")
    cnt = collections.Counter(zip(tr["side"], tr["kind"]))
    for (side, kind), n in sorted(cnt.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"- {side:4s} {trade_causes.KINDS[kind][0]:18s} {n:4d}  · {trade_causes.KINDS[kind][1]}")
    dec = pd.read_parquet(d / "decisions.parquet") if (d / "decisions.parquet").exists() else None
    for tk in a.ticker:
        print(f"\n## {tk}")
        for r in tr[tr["ticker"] == tk].itertuples():
            own = []
            if dec is not None:
                m = dec[(dec["ticker"] == tk) & (dec["date"] == r.decision_date)]
                own = list(m.iloc[0]["notes"]) if len(m) else []
            ref = f" · เกี่ยวกับ {', '.join(r.ref[:6])}{' …' if len(r.ref) > 6 else ''}" if len(r.ref) else ""
            print(f"- ตัดสินใจ {r.decision_date} {r.side.upper():4s} {100 * r.weight_before:.2f}% → {100 * r.weight_after:.2f}% · "
                  f"**{r.label}**{ref} · {r.detail} · note ของตัวเอง: {own or '—'}")


if __name__ == "__main__":
    main()
