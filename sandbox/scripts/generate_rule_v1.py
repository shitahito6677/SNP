"""
Generator สำหรับ sandbox/rules/rule_v1.json — 27-row lookup table (Model A x B x C ->
decision) ที่ `sandbox/engine/combine.py` lookup ตรง ไม่มี fallback/เดา

Design: "priority: A+B override C" (ตามที่ผู้ใช้ระบุใน description ของ rule_v1)
    1. แปลง class เป็น weight ทิศทาง: A buy=+1/hold=0/sell=-1, B/C positive=+1/neutral=0/negative=-1
    2. combined_ab = weight(A) + weight(B)
    3. ถ้า combined_ab > 0  -> decision = "buy"   (A+B เห็นตรงกันไปทาง buy หรือ A/B ฝ่ายใดฝ่าย
       หนึ่ง "ชนะ" ฝ่ายตรงข้าม -> C ไม่มีผลเลย, ถูก "override")
       ถ้า combined_ab < 0  -> decision = "sell"  (เหมือนกัน คนละทิศ)
       ถ้า combined_ab == 0 -> A กับ B หักล้างกันพอดี (เช่น buy+negative, hold+neutral,
       sell+positive) ตอนนี้ C ถึงมีสิทธิ์ตัดสิน: C positive->buy, negative->sell, neutral->hold
    ผลคือ 18/27 แถว (2 ใน 3 ของทั้งหมด) decision ไม่ขึ้นกับ C เลย (ถูก override จริงตามชื่อ)
    อีก 9 แถวที่เหลือ (3 คู่ A,B ที่หักล้างกันพอดี x 3 ค่าของ C) ให้ C เป็นคนตัดสิน

NOTE (สำคัญ): ค่า b/c ในตารางนี้ใช้ "positive"/"neutral"/"negative" ตาม contract จริงของ
Model B/C ที่ fix ไว้ใน sandbox/inference/README.md (ไม่ใช่ "buy"/"sell" ตามตัวอย่าง JSON
1 แถวที่ผู้ใช้แปะมาให้ดู format ซึ่งดูเหมือน typo/illustrative เท่านั้น — เปลี่ยนวิธีเข้ารหัส
ตรงนี้จะทำให้ dashboard/events ทั้งหมดที่ import model_b/model_c โดยตรงพังหมด เพราะทั้งคู่
คืนค่า positive/neutral/negative เสมอ ไม่มีทาง "buy"/"sell" ออกมาได้ — ดู
sandbox/OVERNIGHT_LOG.md สำหรับ decision นี้)

รัน: python3 sandbox/scripts/generate_rule_v1.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent.parent / "rules" / "rule_v1.json"

A_CLASSES = [("buy", 1), ("hold", 0), ("sell", -1)]
BC_CLASSES = [("positive", 1), ("neutral", 0), ("negative", -1)]


def build_table():
    table = []
    for a_cls, a_w in A_CLASSES:
        for b_cls, b_w in BC_CLASSES:
            combined_ab = a_w + b_w
            for c_cls, c_w in BC_CLASSES:
                if combined_ab > 0:
                    decision = "buy"
                elif combined_ab < 0:
                    decision = "sell"
                else:
                    decision = "buy" if c_w > 0 else "sell" if c_w < 0 else "hold"
                table.append({"a": a_cls, "b": b_cls, "c": c_cls, "decision": decision})
    return table


def main():
    table = build_table()
    assert len(table) == 27, f"expected 27 rows, got {len(table)}"

    from collections import Counter

    counts = Counter(r["decision"] for r in table)
    print(f"Generated {len(table)} rows: {dict(counts)}")

    payload = {
        "version": "v1",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "description": "priority: A+B override C",
        "table": table,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
