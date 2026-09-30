"""
In-browser code editor backend (หน้า Rules) — validate + save `decide(a, b, c)` source code
ที่พิมพ์ในเบราว์เซอร์ แล้ว generate `rule_v{N+1}.json` อัตโนมัติ

⚠️ SECURITY NOTE: ฟังก์ชันนี้ `exec()` python source code ที่มาจาก browser request ตรงๆ —
เป็น arbitrary code execution โดยเจตนา (ตามที่ร้องขอ: แก้ decide() ในเบราว์เซอร์แล้วรันได้เลย)
ยอมรับได้เพราะ sandbox นี้รันบน localhost คนเดียวใช้ ไม่มี auth ใดๆ — **ถ้าจะ bind
Flask ให้เข้าถึงได้จากเครื่องอื่น (0.0.0.0, ngrok, ฯลฯ) ห้ามเปิด endpoint นี้เด็ดขาด** เพราะ
ใครก็ตามที่ยิง request มาถึงจะรันโค้ด python อะไรก็ได้บนเครื่องที่รัน server

Naming/versioning ต่างจาก `sandbox/scripts/generate_rule_table.py` (CLI) ตรงนี้:
    - CLI script: regenerate rule_v{N}.json จากไฟล์ rule_v{N}_logic.py ที่ตั้งชื่อ N ไว้แล้ว
      (overwrite ได้เพราะเป็นการ rebuild จาก source ที่ commit ไว้)
    - โค้ดตรงนี้ (มาจาก UI): เขียน**ไฟล์ใหม่เสมอ** ที่เลขเวอร์ชันถัดไป (auto-increment แบบ
      เดียวกับ `sandbox/rules/versions.py`) — ไม่มีทางทับไฟล์เดิมได้เลย
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from sandbox.rules.versions import RULES_DIR, latest_version, load_version, version_path

try:
    from sandbox.scripts.generate_rule_table import build_table
except ImportError:  # pragma: no cover
    build_table = None


def _logic_path(n: int) -> Path:
    return RULES_DIR / f"rule_v{n}_logic.py"


def list_logic_versions() -> list:
    """คืน list ของเลขเวอร์ชันที่มีไฟล์ rule_v{N}_logic.py จริง (ไม่ใช่ทุก rule_v{N}.json
    มี logic ไฟล์คู่กันเสมอ — version ที่มาจากการ manual tweak ผ่าน dropdown UI ไม่มี)"""
    import re

    versions = []
    for f in RULES_DIR.glob("rule_v*_logic.py"):
        m = re.match(r"^rule_v(\d+)_logic$", f.stem)
        if m:
            versions.append(int(m.group(1)))
    return sorted(versions)


def load_logic_source(n: int) -> str:
    path = _logic_path(n)
    if not path.exists():
        raise FileNotFoundError(
            f"rule_v{n} ไม่มีไฟล์ logic คู่กัน ({path.name}) — อาจเป็น version ที่สร้างจาก "
            "manual tweak ผ่าน dropdown ใน UI ไม่ใช่จาก code editor"
        )
    return path.read_text(encoding="utf-8")


def validate_source(source_code: str) -> dict:
    """compile + execute (sandbox ในตัวแปร namespace แยก ไม่แตะ global) เพื่อเช็คว่า
    syntax ถูก, มีฟังก์ชัน decide(a,b,c), และเรียกได้จริงโดยไม่ raise คืนค่า buy/hold/sell
    **ไม่เขียนไฟล์ใดๆ** — แค่ validate เท่านั้น"""
    try:
        code_obj = compile(source_code, "<rule_logic_editor>", "exec")
    except SyntaxError as e:
        return {
            "valid": False,
            "error": f"SyntaxError บรรทัด {e.lineno}: {e.msg}",
            "lineno": e.lineno,
        }

    namespace = {}
    try:
        exec(code_obj, namespace)  # noqa: S102 — ตั้งใจ, ดู SECURITY NOTE ด้านบนไฟล์
    except Exception as e:  # noqa: BLE001 — โค้ด user พังแบบไหนก็ได้ ต้องจับให้หมด
        return {"valid": False, "error": f"{type(e).__name__}: {e}", "lineno": None}

    decide = namespace.get("decide")
    if not callable(decide):
        return {"valid": False, "error": "ไม่พบฟังก์ชัน decide(a, b, c) ใน source code", "lineno": None}

    try:
        sample = decide("buy", "positive", "positive")
    except Exception as e:  # noqa: BLE001
        return {
            "valid": False,
            "error": f"เรียก decide('buy','positive','positive') แล้ว error: {type(e).__name__}: {e}",
            "lineno": None,
        }
    if sample not in ("buy", "hold", "sell"):
        return {
            "valid": False,
            "error": f"decide() คืนค่า {sample!r} ซึ่งไม่ใช่ 'buy'/'hold'/'sell'",
            "lineno": None,
        }

    return {"valid": True, "error": None, "lineno": None}


def _distribution(table: list) -> dict:
    from collections import Counter

    return dict(Counter(r["decision"] for r in table))


def save_new_version_from_source(source_code: str, description: str = "") -> dict:
    """Validate อีกรอบ (ไม่เชื่อผล validate ก่อนหน้าจาก client) แล้วเขียนไฟล์ใหม่เสมอ —
    rule_v{next}_logic.py + rule_v{next}.json (next = max version ที่มีอยู่ + 1 ไม่ทับ
    ของเดิมเด็ดขาด) คืน distribution diff เทียบกับ version ก่อนหน้า"""
    if build_table is None:
        raise RuntimeError("import sandbox.scripts.generate_rule_table ไม่สำเร็จ")

    validation = validate_source(source_code)
    if not validation["valid"]:
        raise ValueError(validation["error"])

    try:
        prev_n = latest_version()
        prev_table = load_version(prev_n)["table"]
        prev_dist = _distribution(prev_table)
    except FileNotFoundError:
        prev_n, prev_table, prev_dist = None, [], {}

    next_n = (prev_n or 0) + 1
    logic_path = _logic_path(next_n)
    json_path = version_path(next_n)
    if logic_path.exists() or json_path.exists():
        # ไม่ควรเกิดขึ้นได้ (next_n มาจาก max+1 เสมอ) แต่เช็คซ้ำกันพลาด — ห้ามทับเด็ดขาด
        raise FileExistsError(f"{logic_path} หรือ {json_path} มีอยู่แล้ว — ห้ามทับไฟล์เดิม")

    namespace = {}
    exec(compile(source_code, str(logic_path), "exec"), namespace)  # noqa: S102 — ดู SECURITY NOTE
    new_table = build_table(namespace["decide"])
    new_dist = _distribution(new_table)

    logic_path.write_text(source_code, encoding="utf-8")
    payload = {
        "version": f"v{next_n}",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "description": description or f"edited via Rules page code editor (from v{prev_n})",
        "table": new_table,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    all_decisions = ("buy", "hold", "sell")
    changed_rows = sum(
        1
        for old_row, new_row in zip(
            sorted(prev_table, key=lambda r: (r["a"], r["b"], r["c"])),
            sorted(new_table, key=lambda r: (r["a"], r["b"], r["c"])),
        )
        if old_row["decision"] != new_row["decision"]
    ) if prev_table else None

    return {
        "version": f"v{next_n}",
        "logic_path": str(logic_path),
        "json_path": str(json_path),
        "distribution_diff": {
            "previous_version": f"v{prev_n}" if prev_n else None,
            "before": {d: prev_dist.get(d, 0) for d in all_decisions} if prev_table else None,
            "after": {d: new_dist.get(d, 0) for d in all_decisions},
            "changed_rows": changed_rows,
            "changed_pct": round(changed_rows / 27 * 100, 1) if changed_rows is not None else None,
        },
    }
