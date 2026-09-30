"""
ล้างข้อมูลทดลองของ sandbox v2 (ข่าว manual · condition ที่ผู้ใช้เพิ่มเอง · ผลการทดลองที่บันทึกไว้) — **backup ก่อนเสมอ**

    python3 -m sandbox.v2.scripts.reset_workspace            # ดูว่าจะล้างอะไร (ไม่ลบ)
    python3 -m sandbox.v2.scripts.reset_workspace --yes      # backup แล้วล้าง
    python3 -m sandbox.v2.scripts.reset_workspace --restore sandbox/v2/backups/<timestamp>

ไม่แตะ: export ของ Model A / Model C, ราคา, registry, template condition ที่มากับระบบ, stub
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

from sandbox.v2 import config as cfg

BACKUP_ROOT = cfg.V2 / "backups"  # gitignored
# template ที่มากับระบบ (อยู่ใน git) — ไม่ลบ
SYSTEM_CONDITIONS = {"B_filter_then_EW", "a_score_threshold", "c_veto_dca_buyback", "condition_fixed", "equal_weight_A",
                     "exclude_negative_B", "follow_A_weights", "hold_SPY"}
CONFIRM_TEXT = "ล้างข้อมูลทดลอง"


def _user_conditions() -> list:
    return sorted(p for p in cfg.CONDITIONS_DIR.glob("*.py") if p.stem not in SYSTEM_CONDITIONS and not p.name.startswith("_"))


def _experiments() -> list:
    return sorted(p for p in cfg.EXPERIMENTS_DIR.iterdir() if p.is_dir()) if cfg.EXPERIMENTS_DIR.exists() else []


def _news_rows() -> list:
    if not cfg.MANUAL_NEWS.exists():
        return []
    return [json.loads(x) for x in cfg.MANUAL_NEWS.read_text(encoding="utf-8").splitlines() if x.strip()]


def plan() -> dict:
    rows = _news_rows()
    return {"news": sum(1 for r in rows if not r.get("deleted")), "news_rows_total": len(rows),
            "conditions": [p.name for p in _user_conditions()], "experiments": [p.name for p in _experiments()],
            "keeps": "Model A/C export, ราคา, template condition ของระบบ (" + ", ".join(sorted(SYSTEM_CONDITIONS)) + "), "
                     "ค่าที่ตั้งในกล่อง Pipeline (เก็บในเบราว์เซอร์ — ถ้า condition ที่เลือกไว้ถูกลบ หน้า Pipeline จะเปลี่ยนเป็นค่าเริ่มต้นพร้อมแจ้ง)"}


def backup(ts: str | None = None) -> Path:
    ts = ts or datetime.now().strftime("%Y%m%d-%H%M%S")
    d = BACKUP_ROOT / ts
    d.mkdir(parents=True, exist_ok=False)
    rows = _news_rows()
    if cfg.MANUAL_NEWS.exists():
        shutil.copy2(cfg.MANUAL_NEWS, d / "manual_news.jsonl")  # กู้คืนได้ตรงทุก field
    keys = sorted({k for r in rows for k in r})
    with open(d / f"manual_news_backup_{ts}.csv", "w", encoding="utf-8-sig", newline="") as f:  # เปิดดูใน Excel ได้
        wr = csv.DictWriter(f, fieldnames=keys)
        wr.writeheader()
        for r in rows:
            wr.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in r.items()})
    cdir = d / f"conditions_backup_{ts}"
    cdir.mkdir()
    for p in _user_conditions():
        shutil.copy2(p, cdir / p.name)
    edir = d / f"experiments_backup_{ts}"
    edir.mkdir()
    for p in _experiments():
        shutil.copytree(p, edir / p.name)
    (d / "BACKUP.json").write_text(json.dumps(dict(plan(), created=ts), ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def reset(confirm: str) -> dict:
    """backup → ลบ; คืนสรุป + ที่อยู่ backup"""
    if confirm != CONFIRM_TEXT:
        raise PermissionError(f"ต้องพิมพ์ยืนยัน '{CONFIRM_TEXT}' ก่อนล้าง")
    before = plan()
    d = backup()
    # ตรวจ backup ครบก่อนลบ
    ts = d.name
    assert len(list((d / f"conditions_backup_{ts}").glob("*.py"))) == len(before["conditions"])
    assert len([p for p in (d / f"experiments_backup_{ts}").iterdir() if p.is_dir()]) == len(before["experiments"])
    assert not cfg.MANUAL_NEWS.exists() or (d / "manual_news.jsonl").read_bytes() == cfg.MANUAL_NEWS.read_bytes()
    if cfg.MANUAL_NEWS.exists():
        cfg.MANUAL_NEWS.write_text("", encoding="utf-8")
    for p in _user_conditions():
        p.unlink()
    for p in _experiments():
        shutil.rmtree(p)
    return {"backup": str(d.relative_to(cfg.REPO)) if d.is_relative_to(cfg.REPO) else str(d), "removed": before, "after": plan()}


def restore(d: Path) -> dict:
    """คืนค่าจาก backup (เขียนทับข่าว, เพิ่ม condition/ผลที่ไม่มีอยู่ — ไม่ลบของใหม่)"""
    d = Path(d)
    ts = d.name
    if (d / "manual_news.jsonl").exists():
        shutil.copy2(d / "manual_news.jsonl", cfg.MANUAL_NEWS)
    n_c = n_e = 0
    for p in (d / f"conditions_backup_{ts}").glob("*.py"):
        if not (cfg.CONDITIONS_DIR / p.name).exists():
            shutil.copy2(p, cfg.CONDITIONS_DIR / p.name)
            n_c += 1
    for p in (d / f"experiments_backup_{ts}").iterdir():
        if p.is_dir() and not (cfg.EXPERIMENTS_DIR / p.name).exists():
            shutil.copytree(p, cfg.EXPERIMENTS_DIR / p.name)
            n_e += 1
    return {"news": plan()["news"], "conditions_restored": n_c, "experiments_restored": n_e}
