"""
N0 — หลักฐานจากการรันจริง (ไม่เดา) สำหรับ 3 อาการที่ผู้ใช้รายงาน:
  1) โหมด Top-N ใน scope ได้ 1 ตัวทั้งที่ตั้ง N=20
  2) `_news()` ใน condition ของผู้ใช้อ่าน ctx.b ถูกไหม (เทียบ raw dict กับค่าที่แปลงได้)
  3) sector จริงของหุ้นที่มีข่าว manual เทียบกับ scope ที่เลือก

    python3 -m sandbox.v2.scripts.diagnose_run [--condition equal_weight_A_v2_v2_v2] [--out sandbox/v2/debug/N0_evidence.md]

อ่านข้อมูลอย่างเดียว (ไม่แก้ข่าว/condition/ผลการทดลอง) — รัน engine ในโฟลเดอร์ชั่วคราว
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import logging
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from sandbox.v2 import condition_registry, config as cfg, engine, news, prices

A_VER = "A:bmf20-weighted"
DEBUG_WRAP = '''

# ===== N0 debug wrapper (เพิ่มตอนวินิจฉัยเท่านั้น — ไม่แก้ตรรกะเดิม) =====
import json as _json
_orig_decide = decide
_N0 = {-2: 0, 2: 0}
def decide(ctx):
    for _t in sorted(ctx.universe):
        _v = ctx.b.get(_t)
        if isinstance(_v, dict) and _v.get("applicable") and _v.get("label") in (-2, 2) and _N0[_v["label"]] < 4:
            _N0[_v["label"]] += 1
            print("N0RAW|" + ctx.date + "|" + _t + "|" + _json.dumps(_v, ensure_ascii=False, default=str) + "|_news=" + repr(_news(ctx, _t)))
    return _orig_decide(ctx)
'''


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", default="equal_weight_A_v2_v2_v2")
    ap.add_argument("--out", default=str(cfg.V2 / "debug" / "N0_evidence.md"))
    args = ap.parse_args(argv)
    out = io.StringIO()
    w = lambda *a: print(*a, file=out)  # noqa: E731

    # ---------- 0) สิ่งที่ server ได้รับจริงในรอบที่ผู้ใช้เจอ "1 ตัว"
    w("# N0 — หลักฐานจากการรันจริง\n\n## 0) config ที่ server ได้รับจริง (jobs.db) — run ที่ A = bmf20 + scope XLK")
    db = sqlite3.connect(cfg.JOBS_DB)
    db.row_factory = sqlite3.Row
    for r in db.execute("SELECT id, created_at, config, result_dir FROM jobs WHERE config LIKE '%bmf20%' AND config LIKE '%XLK%' ORDER BY created_at"):
        c = json.loads(r["config"])
        a = c["stages"]["A"]
        f = Path(r["result_dir"] or "") / "funnel.parquet"
        after = round(float(pd.read_parquet(f)["after_A"].mean()), 1) if f.exists() else None
        w(f"- {r['created_at'][:16]} UTC · job {r['id']} · A = `{json.dumps(a, ensure_ascii=False)}` · after_A เฉลี่ย **{after}**")

    # ---------- 1) Top-N debug log
    w("\n## 1) โหมด Top-N ใน scope XLK — log ทุกขั้น (DEBUG ของ sandbox.v2.engine)")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setLevel(logging.DEBUG)
    engine.dlog.addHandler(h)
    engine.dlog.setLevel(logging.DEBUG)
    xlk = {"mode": "sectors", "sectors": ["XLK"], "tickers": []}
    runs = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, a in (("global (ค่าเริ่มต้น)", {"mode": "on", "version": A_VER}),
                        ("Top-N คงที่ N=20", {"mode": "on", "version": A_VER, "ranking": "scoped_fixed_n", "n": 20})):
            buf.truncate(0)
            buf.seek(0)
            conf, _ = engine.normalize_config({"stages": {"A": a, "B": {"mode": "on", "version": "B:manual-labels-realtime"}},
                                               "scope": xlk, "condition": {"id": "equal_weight_A"}})
            d = Path(tmp) / str(len(runs))
            engine.run(conf, d, log=lambda m: None)
            fun = pd.read_parquet(d / "funnel.parquet")
            runs[name] = fun
            w(f"\n### {name}\n- funnel: ขอบเขต {fun['universe'].mean():.0f} → ผ่าน A เฉลี่ย **{fun['after_A'].mean():.1f}** (min {fun['after_A'].min()}, max {fun['after_A'].max()}) → ถือ {fun['held'].mean():.1f}")
            lines = sorted(set(buf.getvalue().splitlines()))
            w("- log: " + ("\n  - ".join([""] + lines) if lines else "(ไม่มี — โหมดนี้ไม่เรียก scoped_select)"))
    engine.dlog.removeHandler(h)
    sig = __import__("sandbox.v2.registry", fromlist=["x"]).signals(A_VER)
    mem = set(engine.scope_members(xlk))
    for R in ("2021-06-30", "2022-06-30"):
        g = sig[(pd.to_datetime(sig["date"]) == pd.Timestamp(R)) & sig["ticker"].isin(mem)]
        w(f"- รอบ {R}: หุ้น XLK ที่มี record {len(g)} · applicable {int(g['applicable'].sum())} · ที่กฎเลือก (ทั้งตลาด) {int((g['class'] == 'selected').sum())} "
          f"= {sorted(g[g['class'] == 'selected']['ticker'])}")

    # ---------- 2) _news() ของผู้ใช้
    w(f"\n## 2) `_news()` ใน condition `{args.condition}` — ctx.b ดิบ เทียบค่าที่ `_news()` คืน (วันที่มีข่าว ±2)")
    src = condition_registry.source(args.condition) + DEBUG_WRAP
    conf, _ = engine.normalize_config({"stages": {"A": {"mode": "on", "version": A_VER, "ranking": "scoped_fixed_n", "n": 20},
                                                  "B": {"mode": "on", "version": "B:manual-labels-realtime"}},
                                       "scope": xlk, "condition": {"source": src}})
    with tempfile.TemporaryDirectory() as tmp:
        res = engine.run(conf, Path(tmp) / "c", log=lambda m: None)
    raw = [x for x in res["provenance"]["condition_stdout_tail"].splitlines() if x.startswith("N0RAW|")]
    for x in raw:
        _, d, t, js, nv = x.split("|", 4)
        v = json.loads(js)
        w(f"- {d} {t}: label **{v.get('label')}** · class `{v.get('class')}` · score {v.get('score')} → `{nv}`")
        w(f"  - raw: `{js}`")
    if not raw:
        w("- (ไม่พบวันที่มีข่าว ±2 ของหุ้นใน universe)")

    # ---------- 3) sector ของหุ้นที่มีข่าว
    w("\n## 3) sector จริง (GICS ใน universe_manifest จาก S&P 500 snapshot) ของหุ้นที่มีข่าว manual")
    man = prices.manifest()["tickers"]
    snap = pd.read_csv(cfg.DATA / "sp500_snapshot.csv")
    snap_sec = dict(zip(snap["yahoo"], snap["gics_sector"])) if "yahoo" in snap else {}
    cnt = collections.Counter()
    for r in news._load():
        if not r.get("deleted"):
            for t in r.get("tickers") or []:
                cnt[t] += 1
    by_sec = collections.defaultdict(list)
    for t, n in sorted(cnt.items()):
        sec = man.get(t, {}).get("sector") or "Unknown"
        by_sec[sec].append(f"{t}({n})")
        if t in snap_sec and snap_sec[t] != sec:
            w(f"- ⚠️ {t}: manifest = {sec} แต่ snapshot = {snap_sec[t]}")
    for sec, xs in sorted(by_sec.items(), key=lambda kv: -len(kv[1])):
        etf = cfg.SECTOR_ETFS.get(sec, "-")
        w(f"- **{sec} ({etf})** {len(xs)} หุ้น / {sum(int(x.split('(')[1][:-1]) for x in xs)} ข่าว: {', '.join(xs)}")
    in_xlk = sum(n for t, n in cnt.items() if t in mem)
    w(f"- ข่าวทั้งหมด {sum(cnt.values())} รายการ (นับต่อ ticker) · อยู่ใน scope XLK {in_xlk} · นอก XLK {sum(cnt.values()) - in_xlk}")
    for t in ("META", "NFLX", "GOOGL", "NVDA", "TXN", "TRMB"):
        w(f"- {t}: {man.get(t, {}).get('sector')} → {cfg.SECTOR_ETFS.get(man.get(t, {}).get('sector') or '', '-')} · อยู่ใน XLK scope: {t in mem}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(out.getvalue(), encoding="utf-8")
    print(out.getvalue())


if __name__ == "__main__":
    main()
