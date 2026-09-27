"""
Model Registry — สแกนหา version ของ Model A/B/C อัตโนมัติจาก `<export root>/<version>/manifest.json`

เพิ่ม version ใหม่ = สร้างโฟลเดอร์ + manifest.json + signals.parquet → กด Rescan (POST /api/registry/rescan)
ตัวที่ manifest/signal ไม่ผ่าน validation จะอยู่ในรายการ `invalid` พร้อมเหตุผล (ไม่เงียบหาย)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sandbox.v2 import config as cfg

REQUIRED = ["model", "version", "short_label", "display_name", "is_stub", "result_badge", "signal_files",
            "coverage", "rebalance", "source_experiment", "created_at"]
BADGES = {"real", "stub", "negative"}
REBALANCE = {"annual_june", "monthly", "event", "daily"}
KEY_OF = {"A": "ticker", "B": "ticker", "C": "sector"}
SIGNAL_COLS = ["date", "class", "score", "applicable", "reasons", "model_version", "is_stub"]
DEFAULT_CLASSES = {"A": ["selected", "not_selected", "not_applicable"],
                   "B": ["positive", "neutral", "negative"], "C": ["positive", "neutral", "negative"]}

_state = {"valid": {}, "invalid": [], "scanned_at": None}
_signal_cache: dict = {}


def roots() -> list:
    out = []
    for m, r in cfg.MODEL_EXPORT_ROOTS.items():
        out.append((m, r))
        out.append((m, cfg.STUB_EXPORT_ROOT / m))
    return out


def _validate_manifest(m: dict, model: str, d: Path) -> list:
    errs = [f"ขาด field `{k}`" for k in REQUIRED if k not in m]
    if errs:
        return errs
    if m["model"] != model:
        errs.append(f"`model` = {m['model']!r} แต่อยู่ในโฟลเดอร์ของ Model {model}")
    if m["result_badge"] not in BADGES:
        errs.append(f"`result_badge` ต้องเป็นหนึ่งใน {sorted(BADGES)} (ได้ {m['result_badge']!r})")
    if m["rebalance"] not in REBALANCE:
        errs.append(f"`rebalance` ต้องเป็นหนึ่งใน {sorted(REBALANCE)} (ได้ {m['rebalance']!r})")
    if not isinstance(m["coverage"], dict) or "start" not in m["coverage"] or "end" not in m["coverage"]:
        errs.append("`coverage` ต้องมี start และ end")
    if bool(m["is_stub"]) != (m["result_badge"] == "stub"):
        errs.append("`is_stub` กับ `result_badge` ขัดกัน (stub ต้องติด badge stub เสมอ)")
    if m.get("runtime") == "on_demand":
        if not (d / "infer.py").exists():
            errs.append("runtime on_demand ต้องมี infer.py (def infer(tickers, dates) -> DataFrame)")
    elif not m["signal_files"]:
        errs.append("`signal_files` ว่าง")
    for f in m["signal_files"]:
        if not (d / f).exists():
            errs.append(f"ไม่พบไฟล์ signal `{f}`")
    return errs


def _read_signal(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        df = pd.read_csv(path)
        if "reasons" in df:
            df["reasons"] = df["reasons"].map(lambda s: json.loads(s) if isinstance(s, str) and s.startswith("[") else [s])
        return df
    raise ValueError(f"ไม่รองรับไฟล์ {path.suffix} (ใช้ .parquet หรือ .csv)")


def _validate_signals(df: pd.DataFrame, m: dict) -> list:
    key = KEY_OF[m["model"]]
    errs = [f"signal ขาด column `{c}`" for c in [key] + SIGNAL_COLS if c not in df.columns]
    if errs:
        return errs
    d = pd.to_datetime(df["date"], errors="coerce")
    if d.isna().any():
        errs.append(f"`date` แปลงไม่ได้ {int(d.isna().sum())} แถว")
    classes = set(m.get("classes") or DEFAULT_CLASSES[m["model"]])
    bad = set(df["class"].dropna().unique()) - classes
    if bad:
        errs.append(f"`class` มีค่าที่ไม่รู้จัก {sorted(bad)[:5]} (อนุญาต {sorted(classes)})")
    if df.duplicated(["date", key]).any():
        errs.append(f"(date, {key}) ซ้ำ {int(df.duplicated(['date', key]).sum())} แถว")
    if len(df) and not df["reasons"].map(lambda r: hasattr(r, "__len__") and not isinstance(r, str)).all():
        errs.append("`reasons` ต้องเป็น list ของข้อความ")
    if len(df) and bool(df["is_stub"].iloc[0]) != bool(m["is_stub"]):
        errs.append("`is_stub` ใน signal ไม่ตรงกับ manifest")
    return errs


def scan() -> dict:
    valid, invalid = {}, []
    for model, root in roots():
        if not root.exists():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
            mf = d / "manifest.json"
            if not mf.exists():
                continue
            rel = str(d.relative_to(cfg.REPO))
            try:
                m = json.loads(mf.read_text())
            except Exception as e:  # noqa: BLE001
                invalid.append({"model": model, "path": rel, "errors": [f"manifest.json อ่านไม่ได้: {e}"]})
                continue
            errs = _validate_manifest(m, model, d)
            if not errs and m.get("runtime") != "on_demand":
                try:
                    df = pd.concat([_read_signal(d / f) for f in m["signal_files"]], ignore_index=True)
                    errs = _validate_signals(df, m)
                except Exception as e:  # noqa: BLE001
                    errs = [f"อ่าน signal ไม่ได้: {e}"]
            vid = f"{model}:{m.get('version', d.name)}"
            if not errs and vid in valid:
                errs = [f"version id ซ้ำกับ {valid[vid]['path']}"]
            if errs:
                invalid.append({"model": model, "path": rel, "version": m.get("version"), "errors": errs})
                continue
            m = dict(m)
            m.update(id=vid, path=rel, key=KEY_OF[model], classes=m.get("classes") or DEFAULT_CLASSES[model])
            valid[vid] = m
    _state.update(valid=valid, invalid=invalid, scanned_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    _signal_cache.clear()
    return snapshot()


def snapshot() -> dict:
    if _state["scanned_at"] is None:
        scan()
    order = {"real": 0, "negative": 1, "stub": 2}
    models = {m: sorted([v for v in _state["valid"].values() if v["model"] == m],
                        key=lambda v: (order[v["result_badge"]], v["short_label"])) for m in "ABC"}
    return {"models": models, "invalid": _state["invalid"], "scanned_at": _state["scanned_at"]}


def get(vid: str) -> dict:
    if _state["scanned_at"] is None:
        scan()
    if vid not in _state["valid"]:
        raise KeyError(f"ไม่พบ version {vid!r} ใน registry (ลอง Rescan)")
    return _state["valid"][vid]


def signals(vid: str) -> pd.DataFrame:
    """signal ทั้งไฟล์ของ version (cache ต่อ process) — engine เป็นคนตัดตามวันที่ (as-of) เอง"""
    if vid in _signal_cache:
        return _signal_cache[vid]
    m = get(vid)
    d = cfg.REPO / m["path"]
    if m.get("runtime") == "on_demand":
        df = pd.DataFrame(columns=["date", m["key"]] + SIGNAL_COLS[1:])
    else:
        df = pd.concat([_read_signal(d / f) for f in m["signal_files"]], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", m["key"]]).reset_index(drop=True)
    _signal_cache[vid] = df
    return df
