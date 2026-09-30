"""
Generator สำหรับ rule_v{N}.json — import `decide(a, b, c) -> str` จาก logic module ที่ระบุ
(เช่น `sandbox/rules/rule_v1_logic.py`) วน loop ทุก combination 27 แบบ (A: buy/hold/sell ×
B/C: positive/neutral/negative) แล้ว export เป็น JSON — `sandbox/engine/combine.py` และหน้า
UI (Rules) อ่านไฟล์ผลลัพธ์เหมือนเดิมทุกอย่าง ไม่ต้องแก้อะไรฝั่งนั้น

Naming convention (คือกลไกความปลอดภัย ไม่ใช่แค่ชื่อไฟล์เฉยๆ): logic module ต้องชื่อ
`rule_v{N}_logic.py` เท่านั้น — script นี้ parse เลข N จากชื่อ module โดยตรง แล้วเขียนทับ
`sandbox/rules/rule_v{N}.json` **เสมอ** (regenerate จาก source ที่ commit ไว้ใน git ปลอดภัย
รันซ้ำได้ ไม่ใช่การ "ทับของเก่าที่แก้ผ่าน UI" — เส้นทางนั้นยังคงห้ามทับเหมือนเดิม ผ่าน
`sandbox/rules/versions.py`'s `save_new_version()` ซึ่งใช้ auto-increment แยกกันคนละทาง)

ตอนจะลอง logic ใหม่: copy `rule_vN_logic.py` เป็น `rule_v{N+1}_logic.py`, แก้ `decide()`,
รัน `generate_rule_table.py --logic rule_v{N+1}_logic` ได้ `rule_v{N+1}.json` ใหม่ทันที

รัน: python3 sandbox/scripts/generate_rule_table.py --logic rule_v1_logic
"""

import argparse
import importlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

A_CLASSES = ["buy", "hold", "sell"]
BC_CLASSES = ["positive", "neutral", "negative"]

LOGIC_MODULE_RE = re.compile(r"^rule_v(\d+)_logic$")


def build_table(decide) -> list:
    table = []
    for a in A_CLASSES:
        for b in BC_CLASSES:
            for c in BC_CLASSES:
                decision = decide(a, b, c)
                if decision not in ("buy", "hold", "sell"):
                    raise ValueError(
                        f"decide({a!r}, {b!r}, {c!r}) คืนค่า {decision!r} ซึ่งไม่ใช่ "
                        "buy/hold/sell — logic module พัง ไม่ export"
                    )
                table.append({"a": a, "b": b, "c": c, "decision": decision})
    return table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--logic",
        default="rule_v1_logic",
        help="ชื่อ module ใน sandbox/rules/ ที่มี decide(a,b,c) เช่น 'rule_v1_logic' "
        "(ต้องเป็นชื่อรูปแบบ rule_v{N}_logic เท่านั้น — N ใช้กำหนดว่าจะเขียนทับ rule_v{N}.json ไหน)",
    )
    args = parser.parse_args()

    m = LOGIC_MODULE_RE.match(args.logic)
    if not m:
        raise SystemExit(
            f"--logic ต้องเป็นชื่อรูปแบบ 'rule_v{{N}}_logic' เท่านั้น (ได้ {args.logic!r}) "
            "เช่น 'rule_v1_logic', 'rule_v2_logic'"
        )
    n = int(m.group(1))

    module = importlib.import_module(f"sandbox.rules.{args.logic}")
    if not hasattr(module, "decide"):
        raise SystemExit(f"sandbox.rules.{args.logic} ไม่มีฟังก์ชัน decide(a,b,c)")

    table = build_table(module.decide)
    assert len(table) == 27, f"expected 27 rows, got {len(table)}"

    counts = Counter(r["decision"] for r in table)
    print(f"Generated {len(table)} rows from {args.logic}.decide(): {dict(counts)}")

    out_path = RULES_DIR / f"rule_v{n}.json"
    payload = {
        "version": f"v{n}",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "description": f"generated from sandbox/rules/{args.logic}.py:decide()",
        "table": table,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
