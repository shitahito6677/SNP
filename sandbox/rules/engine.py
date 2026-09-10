"""
Rule engine — combine Model A/B/C predict() output เป็นสัญญาณเดียว (BUY/HOLD/SELL)
โดย lookup จาก sandbox/rules/rule_table.json (27 แถว, ดูที่มาใน
sandbox/scripts/generate_rule_table.py)

ทำงานกับทั้ง stub และโมเดลจริงเหมือนกัน — รับแค่ dict ที่มี key `class` (และเช็ค `is_stub`
เพื่อ propagate คำเตือนต่อ) ไม่สนใจว่า predict() ข้างในเป็น stub หรือของจริง
"""

import json
from pathlib import Path

_TABLE_PATH = Path(__file__).resolve().parent / "rule_table.json"


def _load_table() -> dict:
    payload = json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
    lookup = {
        (r["model_a_class"], r["model_b_class"], r["model_c_class"]): r
        for r in payload["rows"]
    }
    if len(lookup) != 27:
        raise ValueError(
            f"rule_table.json ควรมี 27 แถวไม่ซ้ำกัน (A x B x C แบบ 3x3x3) แต่มี {len(lookup)} "
            "— ตรวจว่าไฟล์ถูกแก้จนมีแถวซ้ำ/ขาดหรือไม่"
        )
    return {"lookup": lookup, "meta": payload["meta"]}


_TABLE = _load_table()


def combine(model_a_result: dict, model_b_result: dict, model_c_result: dict) -> dict:
    """
    Args:
        model_a_result: dict จาก sandbox.inference.model_a.predict() — ต้องมี key `class`
        model_b_result: dict จาก sandbox.inference.model_b.predict() — ต้องมี key `class`
        model_c_result: dict จาก sandbox.inference.model_c.predict() — ต้องมี key `class`

    Returns:
        dict:
            signal (str): "BUY" | "HOLD" | "SELL"
            weighted_score (float): คะแนนที่ table ใช้ตัดสิน signal (สำหรับ debug/แสดงผล)
            is_stub (bool): True ถ้า input ใดตัวหนึ่งมาจาก stub (is_stub=True หรือไม่มี key
                `is_stub` เลย ก็ถือว่าไม่ยืนยันว่าไม่ใช่ stub -> True เพื่อความปลอดภัย)
            inputs (dict): class ที่ใช้ lookup จริงของแต่ละโมเดล (สำหรับแสดงผล/debug)
    """
    a_cls = model_a_result["class"]
    b_cls = model_b_result["class"]
    c_cls = model_c_result["class"]

    key = (a_cls, b_cls, c_cls)
    row = _TABLE["lookup"].get(key)
    if row is None:
        raise ValueError(
            f"ไม่พบแถวใน rule table สำหรับ combo {key} — ตรวจว่า class ที่โมเดลคืนมาตรงกับ "
            "ค่าที่ระบุใน sandbox/inference/README.md หรือไม่ (buy/hold/sell สำหรับ A, "
            "positive/neutral/negative สำหรับ B/C)"
        )

    is_stub = any(
        r.get("is_stub", True) for r in (model_a_result, model_b_result, model_c_result)
    )

    return {
        "signal": row["signal"],
        "weighted_score": row["weighted_score"],
        "is_stub": is_stub,
        "inputs": {"model_a_class": a_cls, "model_b_class": b_cls, "model_c_class": c_cls},
    }


def table_meta() -> dict:
    """คืน metadata ของ rule table ปัจจุบัน (weights, thresholds, signal distribution)
    สำหรับให้ dashboard แสดงอธิบายว่าตัดสินใจยังไง"""
    return _TABLE["meta"]
