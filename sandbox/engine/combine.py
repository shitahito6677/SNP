"""
Ensemble rule engine (Phase 4) — lookup ตรง (a, b, c) -> decision จาก rule version file
(`sandbox/rules/rule_v{n}.json`) ห้าม fallback/เดาเด็ดขาด ถ้าไม่เจอ combination ให้ raise
error ทันที (ตาม spec: "ไม่เจอ combination ให้ raise error ห้าม fallback เดา")
"""

import json
from pathlib import Path


def combine(a: str, b: str, c: str, rule_path: str) -> str:
    """
    lookup ตรง (a, b, c) -> decision จาก rule_path

    Args:
        a: Model A class — "buy" | "hold" | "sell"
        b: Model B class — "positive" | "neutral" | "negative"
        c: Model C class — "positive" | "neutral" | "negative"
        rule_path: path ไปยังไฟล์ rule version (เช่น "sandbox/rules/rule_v1.json")

    Returns:
        decision (str) จากแถวที่ตรงกับ (a, b, c) เป๊ะ

    Raises:
        FileNotFoundError: ถ้า rule_path ไม่มีอยู่จริง
        ValueError: ถ้าไม่เจอแถวไหนใน table ที่ตรงกับ (a, b, c) — ห้าม fallback/เดาเด็ดขาด
    """
    path = Path(rule_path)
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบ rule file: {rule_path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload["table"]:
        if row["a"] == a and row["b"] == b and row["c"] == c:
            return row["decision"]

    raise ValueError(
        f"ไม่พบ combination (a={a!r}, b={b!r}, c={c!r}) ใน {rule_path} "
        f"(version={payload.get('version', '?')}) — ห้าม fallback เดา ต้องเพิ่มแถวนี้เข้า "
        "rule table ก่อน"
    )
