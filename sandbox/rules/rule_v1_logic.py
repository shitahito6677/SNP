"""
rule_v1 decision logic — "A เป็นหลัก, B/C เป็น veto"

ยึด Model A (Piotroski fundamental) เป็นทิศทางหลักเสมอ Model B/C (sentiment) ทำหน้าที่แค่
**ยับยั้ง** ทิศทางของ A เมื่อขัดแย้งกันชัดเจน ไม่ใช่มาช่วย "ยืนยัน/เสริม" ให้แรงขึ้น:

    - A=buy  แต่มีข่าว (B หรือ C) เป็น negative -> ลดเป็น hold (กันซื้อทั้งที่มีข่าวร้าย)
    - A=sell แต่มีข่าว (B หรือ C) เป็น positive -> ยกเป็น hold (กันขายทิ้งทั้งที่มีข่าวดี)
    - A=hold -> hold เสมอ (ไม่มีทิศทางให้ B/C veto อยู่แล้ว)

B/C เป็น positive/neutral ตอน A=buy ไม่ทำให้แรงขึ้นเป็นอะไรมากกว่า buy (ไม่มี "strong buy")
และ B/C เป็น neutral ไม่นับเป็น veto (แค่ negative/positive ที่ชัดเจนเท่านั้นที่ veto ได้)

ไฟล์นี้เป็น**ต้นทางของจริง** (source of truth) ของ `rule_v1.json` — รัน
`python3 sandbox/scripts/generate_rule_table.py --logic rule_v1_logic` เพื่อ regenerate
(ปลอดภัยรันซ้ำได้เสมอ เพราะ deterministic และไฟล์เป้าหมายผูกกับชื่อ module นี้โดยตรง)

ตอนจะลอง logic ใหม่ (v2, v3, ...): copy ไฟล์นี้เป็น `rule_v2_logic.py` แก้ `decide()` แล้วรัน
`generate_rule_table.py --logic rule_v2_logic` — ได้ `rule_v2.json` ใหม่ทันที ไม่ต้องกรอก
ทีละแถวใน UI (แต่จะ manual tweak เฉพาะจุดผ่านหน้า Rules ทีหลังก็ยังทำได้ตามปกติ — "Save as
new version" จะสร้าง version ถัดไปเสมอ ไม่ทับ v2 นี้)
"""


def decide(a: str, b: str, c: str) -> str:
    """
    Args:
        a: Model A class — "buy" | "hold" | "sell"
        b: Model B class — "positive" | "neutral" | "negative"
        c: Model C class — "positive" | "neutral" | "negative"

    Returns:
        "buy" | "hold" | "sell"
    """
    if a == "buy":
        if b == "negative" or c == "negative":
            return "hold"
        return "buy"

    if a == "sell":
        if b == "positive" or c == "positive":
            return "hold"
        return "sell"

    return "hold"  # a == "hold" -> ไม่มีทิศทางให้ veto อยู่แล้ว
