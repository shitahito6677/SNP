"""
Condition Registry — ไฟล์ `sandbox/v2/conditions/*.py` แต่ละไฟล์ต้องมี

    NAME = "..."
    DESCRIPTION = "..."
    def decide(ctx) -> dict[str, float] | None   # {ticker: weight} ผลรวม ≤ 1.0 (ที่เหลือ = เงินสด), None = คงเป้าเดิม

ไฟล์นี้ **ไม่ exec โค้ดผู้ใช้** (ตรวจด้วย ast เท่านั้น) — การรันจริงเกิดใน process แยก (condition_worker.py)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from sandbox.v2 import config as cfg

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{1,60}$")


def static_check(source: str) -> dict:
    """คืน {"ok", "errors", "name", "description"} — ตรวจ syntax, NAME, DESCRIPTION, def decide(ctx)"""
    errs, name, desc = [], None, None
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"ok": False, "errors": [f"SyntaxError บรรทัด {e.lineno}: {e.msg}"], "name": None, "description": None}
    decide = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            tgt = node.targets[0].id
            if tgt in ("NAME", "DESCRIPTION"):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    if tgt == "NAME":
                        name = node.value.value
                    else:
                        desc = node.value.value
                else:
                    errs.append(f"{tgt} ต้องเป็นข้อความ (string literal)")
        if isinstance(node, ast.FunctionDef) and node.name == "decide":
            decide = node
    if not name:
        errs.append("ขาด NAME = \"...\"")
    if desc is None:
        errs.append("ขาด DESCRIPTION = \"...\"")
    if decide is None:
        errs.append("ขาด def decide(ctx)")
    else:
        a = decide.args
        n_pos = len(a.posonlyargs) + len(a.args)
        if n_pos != 1 or a.vararg or a.kwarg or a.kwonlyargs:
            errs.append("decide ต้องรับพารามิเตอร์เดียวคือ ctx: def decide(ctx)")
    return {"ok": not errs, "errors": errs, "name": name, "description": desc}


def list_conditions() -> list:
    out = []
    for p in sorted(cfg.CONDITIONS_DIR.glob("*.py")):
        if p.name.startswith("_"):
            continue
        src = p.read_text(encoding="utf-8")
        chk = static_check(src)
        out.append({"id": p.stem, "file": str(p.relative_to(cfg.REPO)), "name": chk["name"] or p.stem,
                    "description": chk["description"] or "", "ok": chk["ok"], "errors": chk["errors"],
                    "template": p.stem in TEMPLATES})
    return out


def source(cid: str) -> str:
    if not ID_RE.match(cid):
        raise ValueError(f"condition id ไม่ถูกต้อง: {cid!r}")
    p = cfg.CONDITIONS_DIR / f"{cid}.py"
    if not p.exists():
        raise KeyError(f"ไม่พบ condition {cid!r}")
    return p.read_text(encoding="utf-8")


def save_new(cid: str, src: str) -> Path:
    """บันทึกเป็นไฟล์ใหม่ — ห้ามเขียนทับไฟล์เดิม"""
    if not ID_RE.match(cid):
        raise ValueError("ชื่อไฟล์ต้องเป็น A-Z, a-z, 0-9, _ (2–61 ตัว) เช่น my_condition_v2")
    p = cfg.CONDITIONS_DIR / f"{cid}.py"
    if p.exists():
        raise FileExistsError(f"มี condition ชื่อ {cid!r} อยู่แล้ว — ห้ามเขียนทับ ตั้งชื่อใหม่")
    chk = static_check(src)
    if not chk["ok"]:
        raise ValueError("; ".join(chk["errors"]))
    p.write_text(src, encoding="utf-8")
    return p


TEMPLATES = {"equal_weight_A", "follow_A_weights", "hold_SPY", "B_filter_then_EW", "c_veto_dca_buyback"}
