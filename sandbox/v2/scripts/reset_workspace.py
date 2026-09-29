"""ล้างข้อมูลทดลอง (backup อัตโนมัติ) — ดู sandbox/v2/workspace.py"""
import argparse
import json
import sys

from sandbox.v2 import workspace


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="backup แล้วล้างจริง (ไม่ใส่ = แสดงแผนอย่างเดียว)")
    ap.add_argument("--restore", help="โฟลเดอร์ backup ที่จะกู้คืน")
    a = ap.parse_args(argv)
    if a.restore:
        print(json.dumps(workspace.restore(a.restore), ensure_ascii=False, indent=1))
    elif a.yes:
        res = workspace.reset(workspace.CONFIRM_TEXT)
        from sandbox.v2 import manual_labels
        manual_labels.build()
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("แผน (ยังไม่ลบ — ใส่ --yes เพื่อ backup แล้วล้าง):")
        print(json.dumps(workspace.plan(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
