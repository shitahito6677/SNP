"""
Rule version management (Phase 4) — list/load/save `sandbox/rules/rule_v{n}.json`
"Save as new version" ต้องสร้างไฟล์ใหม่เสมอ (`rule_v{n+1}.json`) **ห้ามทับไฟล์เดิมเด็ดขาด**
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent
VERSION_RE = re.compile(r"^rule_v(\d+)\.json$")

REQUIRED_KEYS = {"a", "b", "c", "decision"}
A_VALUES = {"buy", "hold", "sell"}
BC_VALUES = {"positive", "neutral", "negative"}
DECISION_VALUES = {"buy", "hold", "sell"}


def list_versions() -> list:
    """คืน list ของ version number (int) ที่มีอยู่จริง เรียงจากน้อยไปมาก"""
    versions = []
    for f in RULES_DIR.glob("rule_v*.json"):
        m = VERSION_RE.match(f.name)
        if m:
            versions.append(int(m.group(1)))
    return sorted(versions)


def version_path(n: int) -> Path:
    return RULES_DIR / f"rule_v{n}.json"


def latest_version() -> int:
    versions = list_versions()
    if not versions:
        raise FileNotFoundError(
            f"ไม่พบ rule_v*.json เลยใน {RULES_DIR} — ต้องมีอย่างน้อย rule_v1.json "
            "(รัน sandbox/scripts/generate_rule_v1.py)"
        )
    return versions[-1]


def load_version(n: int) -> dict:
    path = version_path(n)
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบ {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_table(table: list) -> None:
    """เช็คว่า table มีครบ 27 combination ไม่ซ้ำ, ค่า a/b/c/decision อยู่ใน enum ที่กำหนด
    — ป้องกันการ save table ที่พังผ่าน UI"""
    seen = set()
    for row in table:
        missing = REQUIRED_KEYS - set(row)
        if missing:
            raise ValueError(f"แถวขาด field: {missing} ({row})")
        if row["a"] not in A_VALUES:
            raise ValueError(f"a={row['a']!r} ไม่อยู่ใน {A_VALUES}")
        if row["b"] not in BC_VALUES:
            raise ValueError(f"b={row['b']!r} ไม่อยู่ใน {BC_VALUES}")
        if row["c"] not in BC_VALUES:
            raise ValueError(f"c={row['c']!r} ไม่อยู่ใน {BC_VALUES}")
        if row["decision"] not in DECISION_VALUES:
            raise ValueError(f"decision={row['decision']!r} ไม่อยู่ใน {DECISION_VALUES}")
        key = (row["a"], row["b"], row["c"])
        if key in seen:
            raise ValueError(f"combination ซ้ำ: {key}")
        seen.add(key)

    expected = {
        (a, b, c)
        for a in A_VALUES
        for b in BC_VALUES
        for c in BC_VALUES
    }
    missing_combos = expected - seen
    if missing_combos:
        raise ValueError(f"ตารางไม่ครบ 27 combination — ขาด: {sorted(missing_combos)}")


def save_new_version(table: list, description: str = "") -> dict:
    """สร้าง rule_v{n+1}.json ใหม่เสมอ ห้ามทับไฟล์เดิม — คืน payload ที่เขียนไปพร้อม path"""
    validate_table(table)

    try:
        current = latest_version()
    except FileNotFoundError:
        current = 0
    next_n = current + 1
    path = version_path(next_n)

    if path.exists():
        # กันชนกรณี race condition/ไฟล์ค้าง — ไม่มีทาง overwrite เด็ดขาด
        raise FileExistsError(f"{path} มีอยู่แล้ว — ห้ามทับไฟล์เดิม (ผิดปกติ ควรรายงาน bug)")

    payload = {
        "version": f"v{next_n}",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "description": description or f"edited from v{current} via Rules page",
        "table": table,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"path": str(path), "version": f"v{next_n}", **payload}
