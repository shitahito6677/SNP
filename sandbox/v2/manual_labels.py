"""
B version จากข่าว manual — `model_B/export/manual-labels-{oracle,realtime}/` (สร้างใหม่อัตโนมัติจาก sandbox/v2/data/manual_news.jsonl)

ระหว่างที่ยังไม่มี Model B จริง: ใช้ label -2..+2 ที่ผู้ใช้/Claude ระบุไว้ในข่าว manual เป็นคะแนน B แทน stub สุ่ม
- signal ต่อ (ticker, วันที่ข่าวมีผล) → score = label -2..+2, applicable True
- **point-in-time**: ใช้ได้เฉพาะวันที่มีข่าวจริง (`asof.max_age_days = 0`) — ไม่ลากค่าเก่าไปวันถัดไป
- ticker/วันที่ที่ไม่มีข่าว → engine ส่ง `applicable: False` ให้ condition (ไม่เดาค่า)

ไฟล์ที่สร้างมาจากข้อมูลส่วนตัวของผู้ใช้ (gitignored) จึงไม่ commit — rebuild ทุกครั้งที่ข่าวเปลี่ยน / server start / Rescan
"""

from __future__ import annotations

import hashlib
import json
import shutil

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg, news, registry

# 2 version แยกตามวิธีตั้ง label — ข่าวคนละประเภทไม่ปนกัน, ข่าว unknown ไม่เข้า version ไหนเลย
ORACLE_TIP = ("Oracle test — label รู้ผลราคาจริงล่วงหน้าแล้ว ใช้หาเพดานบนว่า B ที่แม่นสมบูรณ์จะช่วยได้แค่ไหน "
              "ผลตอบแทนที่ได้ไม่ใช่สิ่งที่ทำได้จริง ห้ามอ้างเป็นผลจริง")
VERSIONS = {
    "manual-labels-oracle": {
        "method": "hindsight", "short_label": "B-oracle", "result_badge": "oracle",
        "display_name": "Oracle — label แบบรู้ผลราคาแล้ว (hindsight)",
        "warnings": ["ORACLE: " + ORACLE_TIP],
    },
    "manual-labels-realtime": {
        "method": "real_time", "short_label": "B-manual", "result_badge": "manual",
        "display_name": "Manual labels แบบ real-time (ไม่รู้ผลล่วงหน้า)",
        "warnings": ["MANUAL: คะแนน B มาจาก label ที่ผู้ใช้/Claude ระบุ ณ วันข่าว (ไม่รู้ผลล่วงหน้า) ไม่ใช่โมเดลที่เทรน"],
    },
}
COLUMNS = ["date", "ticker", "class", "score", "label", "label_text", "label_method", "applicable", "reasons", "model_version",
           "is_stub", "n_news", "news_ids"]
POINT_IN_TIME_NOTE = ("point-in-time: สัญญาณใช้ได้เฉพาะวันที่มีข่าวจริง (asof.max_age_days = 0) ไม่ carry-forward — "
                      "ข่าว manual ไม่ได้มีทุกวัน การลากค่าเก่าไปเรื่อย ๆ จะทำให้ดูเหมือนมีสัญญาณมากกว่าที่มีจริง; "
                      "วันที่/หุ้นที่ไม่มีข่าว = applicable False (ไม่เดาค่า)")


def root():
    return cfg.MODEL_EXPORT_ROOTS["B"]


def _round_half_away(x: float) -> int:
    return int(np.sign(x) * np.floor(abs(x) + 0.5))


def _rows(items: list, version: str) -> pd.DataFrame:
    by = {}
    for n in items:
        for t in n.get("tickers") or []:
            by.setdefault((n["effective_date"], t), []).append(n)
    rows = []
    for (d, t), ns in sorted(by.items()):
        labs = [news.label_of(n) for n in ns]
        lab = labs[0] if len(set(labs)) == 1 else _round_half_away(float(np.mean(labs)))
        reasons = [f"MANUAL {d} [{news.label_tag(v)}]: {n['headline'][:140]}" for n, v in zip(ns, labs)]
        if len(ns) > 1:
            reasons.append(f"ข่าว {len(ns)} รายการในวันเดียว: label {labs} → เฉลี่ยปัดครึ่งออกจาก 0 = {lab:+d}")
        rows.append({"date": pd.Timestamp(d), "ticker": t, "class": news.label_class(lab), "score": float(lab), "label": lab,
                     "label_text": news.LABELS[lab], "label_method": news.label_method_of(ns[0]), "applicable": True, "reasons": reasons, "model_version": version,
                     "is_stub": False, "n_news": len(ns), "news_ids": [n["id"] for n in ns]})
    return pd.DataFrame(rows, columns=COLUMNS)


def _select(version: str, spec: dict) -> list:
    """ข่าวรายบริษัทที่ยังไม่ถูกลบ และ label_method ตรงกับ version นี้เท่านั้น (ไม่ผสมข้ามประเภทมาเติมให้)"""
    return [n for n in news._load() if not n.get("deleted") and n.get("tickers") and news.label_method_of(n) == spec["method"]]


def build(rescan: bool = True) -> dict:
    """เขียน signal + manifest ของทุก version (เฉพาะเมื่อเนื้อหาเปลี่ยน) แล้ว rescan registry — คืน {version: n_rows}"""
    out, changed = {}, False
    for version, spec in VERSIONS.items():
        items = _select(version, spec)
        df = _rows(items, version)
        payload = "[]" if df.empty else \
            df.drop(columns=["date"]).assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_json(orient="records", force_ascii=False)
        sha = hashlib.sha256(payload.encode()).hexdigest()
        d = root() / version
        mf = d / "manifest.json"
        if mf.exists() and json.loads(mf.read_text()).get("content_sha256") == sha:
            out[version] = len(df)
            continue
        changed = True
        d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / "signals.parquet", index=False)
        empty = df.empty
        man = {
            "model": "B", "version": version, "short_label": spec["short_label"], "display_name": spec["display_name"],
            "rule_id": version, "is_stub": False, "result_badge": spec["result_badge"], "signal_files": ["signals.parquet"],
            "coverage": {"start": None if empty else str(df["date"].min().date()), "end": None if empty else str(df["date"].max().date()),
                         "n_rows": len(df), "n_news": len(items), "n_tickers": int(df["ticker"].nunique()),
                         "tickers": sorted(df["ticker"].unique().tolist())},
            "rebalance": "event", "asof": {"max_age_days": 0}, "key": "ticker",
            "classes": ["positive", "neutral", "negative"],
            "score_meaning": "label ความแรงของข่าว -2..+2 (-2 negative แรงมาก · -1 negative · 0 ไม่ค่อยมีผล · +1 positive · +2 positive แรงมาก)",
            "source_experiment": f"sandbox/v2/data/manual_news.jsonl (ข่าว manual ที่ label_method = {spec['method']})",
            "label_method": spec["method"], "contains_oracle_signal": spec["result_badge"] == "oracle",
            # created_at = เวลาของข่าวล่าสุดที่ใช้ (ไม่ใช่เวลา build) → rebuild ด้วยข่าวชุดเดิมไม่ถูกนับว่า "signal เปลี่ยน"
            "created_at": max((n.get("updated_at") or n.get("created_at") or "") for n in items) if items else "1970-01-01T00:00:00+00:00",
            "content_sha256": sha,
            "notes": POINT_IN_TIME_NOTE + " · ข่าวหลายรายการของหุ้นเดียวกันในวันเดียว → label เฉลี่ยปัดครึ่งออกจาก 0 (reasons เก็บทุกข่าว)",
            "warnings": list(spec["warnings"]) + ([] if not empty else [f"ยังไม่มีข่าว manual ที่ label_method = {spec['method']} — ไม่มีสัญญาณเลย (applicable False ทุกวัน) · ระบุวิธี label ของข่าวได้ที่หน้าเพิ่มข่าว"]),
        }
        mf.write_text(json.dumps(man, ensure_ascii=False, indent=1))
        out[version] = len(df)
    for d in (root().glob("manual-labels*") if root().exists() else []):  # version ที่เลิกใช้แล้ว (เช่นเปลี่ยนชื่อ) → ลบทิ้ง
        if d.is_dir() and d.name not in VERSIONS:
            shutil.rmtree(d)
            changed = True
    if rescan and changed:
        registry.scan()
    return out
