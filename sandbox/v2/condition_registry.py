"""
Condition Registry — ไฟล์ `sandbox/v2/conditions/*.py` แต่ละไฟล์ต้องมี

    NAME = "..."
    DESCRIPTION = "..."
    def decide(ctx) -> dict[str, float] | None   # {ticker: weight} ผลรวม ≤ 1.0 (ที่เหลือ = เงินสด), None = คงเป้าเดิม

(ไม่บังคับ) ค่าที่ปรับได้จากหน้าเว็บ — dict ตัวอักษรล้วน (ast.literal_eval):

    PARAMS = {"MA_DAYS": {"type": "int", "default": 50, "min": 5, "max": 250, "label": "...", "help": "..."},
              "MA_TYPE": {"type": "choice", "default": "SMA", "choices": ["SMA", "EMA"], "label": "...", "help": "..."}}

    ค่าที่ผู้ใช้ตั้ง (config.condition.params) ถูกตั้งเป็นตัวแปร global ชื่อเดียวกันก่อนเรียก decide ทุกครั้ง

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
    errs, name, desc, params = [], None, None, {}
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"ok": False, "errors": [f"SyntaxError บรรทัด {e.lineno}: {e.msg}"], "name": None, "description": None, "params": {}}
    decide = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            tgt = node.targets[0].id
            if tgt == "PARAMS":
                try:
                    params = _check_params(ast.literal_eval(node.value))
                except (ValueError, SyntaxError, TypeError) as e:
                    errs.append(f"PARAMS ไม่ถูกต้อง: {e}")
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
    return {"ok": not errs, "errors": errs, "name": name, "description": desc, "params": params}


PARAM_TYPES = ("int", "float", "choice")


def _check_params(spec) -> dict:
    """ตรวจรูปแบบ PARAMS — คืน dict ชื่อ → spec (เรียงตามที่ประกาศ)"""
    if not isinstance(spec, dict):
        raise ValueError("ต้องเป็น dict {ชื่อ: {...}}")
    out = {}
    for k, v in spec.items():
        if not isinstance(k, str) or not re.match(r"^[A-Z][A-Z0-9_]{0,40}$", k):
            raise ValueError(f"ชื่อ {k!r} ต้องเป็นตัวพิมพ์ใหญ่ เช่น MA_DAYS")
        if not isinstance(v, dict) or v.get("type") not in PARAM_TYPES or "default" not in v:
            raise ValueError(f"{k}: ต้องมี type ({'/'.join(PARAM_TYPES)}) และ default")
        if v["type"] == "choice":
            if not isinstance(v.get("choices"), list) or v["default"] not in v["choices"]:
                raise ValueError(f"{k}: choice ต้องมี choices และ default อยู่ในนั้น")
        else:
            lo, hi = v.get("min"), v.get("max")
            if lo is None or hi is None or not lo <= v["default"] <= hi:
                raise ValueError(f"{k}: ต้องมี min/max และ min ≤ default ≤ max")
        out[k] = {"type": v["type"], "default": v["default"], "min": v.get("min"), "max": v.get("max"), "choices": v.get("choices"),
                  "label": str(v.get("label") or k), "help": str(v.get("help") or "")}
    return out


def resolve_params(spec: dict, given: dict | None) -> dict:
    """ค่าที่ใช้รันจริง = ค่าที่ผู้ใช้ตั้ง (ตรวจชนิด/ช่วง) หรือ default — ชื่อที่ไม่ได้ประกาศ = error"""
    given = dict(given or {})
    unknown = sorted(set(given) - set(spec))
    if unknown:
        raise ValueError(f"condition นี้ไม่มีค่าที่ปรับได้ชื่อ {', '.join(unknown)} (มี: {', '.join(spec) or 'ไม่มี'})")
    out = {}
    for k, sp in spec.items():
        v = given.get(k, sp["default"])
        if v in (None, ""):
            v = sp["default"]
        if sp["type"] == "choice":
            if v not in sp["choices"]:
                raise ValueError(f"{sp['label']} ({k}) ต้องเป็นหนึ่งใน {', '.join(map(str, sp['choices']))} (ได้ {v!r})")
        else:
            try:
                x = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{sp['label']} ({k}) ต้องเป็นตัวเลข (ได้ {v!r})") from None
            if sp["type"] == "int":
                if x != int(x):
                    raise ValueError(f"{sp['label']} ({k}) ต้องเป็นจำนวนเต็ม (ได้ {v!r})")
                x = int(x)
            if not sp["min"] <= x <= sp["max"]:
                raise ValueError(f"{sp['label']} ({k}) ต้องอยู่ระหว่าง {sp['min']}–{sp['max']} (ได้ {v!r})")
            v = x
        out[k] = v
    return out


def list_conditions() -> list:
    out = []
    for p in sorted(cfg.CONDITIONS_DIR.glob("*.py")):
        if p.name.startswith("_"):
            continue
        src = p.read_text(encoding="utf-8")
        chk = static_check(src)
        out.append({"id": p.stem, "file": str(p.relative_to(cfg.REPO)), "name": chk["name"] or p.stem,
                    "description": chk["description"] or "", "ok": chk["ok"], "errors": chk["errors"], "params": chk["params"],
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
