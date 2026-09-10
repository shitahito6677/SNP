"""
Unit test สำหรับ sandbox/engine/combine.py (Phase 4 DoD: "unit test combine() อย่างน้อย
5 case ผ่าน") ใช้ unittest จาก stdlib ไม่ต้องติดตั้ง dependency เพิ่ม

รัน (จาก project root): python3 -m unittest sandbox.scripts.test_combine -v
"""

import json
import tempfile
import unittest
from pathlib import Path

from sandbox.engine.combine import combine
from sandbox.rules.versions import RULES_DIR, latest_version, load_version, version_path


class TestCombineAgainstLatestRuleVersion(unittest.TestCase):
    """เทส combine() กับ rule_v1.json จริงที่ repo ใช้อยู่ (ไม่ mock) — priority: A+B override C"""

    @classmethod
    def setUpClass(cls):
        cls.n = latest_version()
        cls.path = str(version_path(cls.n))
        cls.payload = load_version(cls.n)

    def test_01_buy_plus_positive_ignores_negative_c(self):
        # A=buy(+1) + B=positive(+1) = +2 > 0 -> buy, ไม่สนใจ C เลย (override)
        self.assertEqual(combine("buy", "positive", "negative", self.path), "buy")

    def test_02_sell_plus_negative_ignores_positive_c(self):
        # A=sell(-1) + B=negative(-1) = -2 < 0 -> sell, ไม่สนใจ C เลย (override)
        self.assertEqual(combine("sell", "negative", "positive", self.path), "sell")

    def test_03_tie_broken_by_positive_c(self):
        # A=hold(0) + B=neutral(0) = 0 -> tie, C=positive(+1) ตัดสินเป็น buy
        self.assertEqual(combine("hold", "neutral", "positive", self.path), "buy")

    def test_04_tie_broken_by_negative_c(self):
        # A=hold(0) + B=neutral(0) = 0 -> tie, C=negative(-1) ตัดสินเป็น sell
        self.assertEqual(combine("hold", "neutral", "negative", self.path), "sell")

    def test_05_tie_broken_by_neutral_c_stays_hold(self):
        # A=hold(0) + B=neutral(0) = 0 -> tie, C=neutral(0) -> hold
        self.assertEqual(combine("hold", "neutral", "neutral", self.path), "hold")

    def test_06_all_27_combinations_resolve_without_error(self):
        classes_a = ["buy", "hold", "sell"]
        classes_bc = ["positive", "neutral", "negative"]
        seen = set()
        for a in classes_a:
            for b in classes_bc:
                for c in classes_bc:
                    decision = combine(a, b, c, self.path)
                    self.assertIn(decision, {"buy", "hold", "sell"})
                    seen.add((a, b, c))
        self.assertEqual(len(seen), 27)

    def test_07_missing_combination_raises_valueerror_not_fallback(self):
        # ห้าม fallback เดา — ตัดแถวหนึ่งออกจาก table ชั่วคราวแล้วยืนยันว่า raise จริง
        with tempfile.TemporaryDirectory() as tmp:
            broken_table = [
                row for row in self.payload["table"]
                if not (row["a"] == "buy" and row["b"] == "positive" and row["c"] == "positive")
            ]
            broken_path = Path(tmp) / "rule_broken.json"
            broken_path.write_text(
                json.dumps({**self.payload, "table": broken_table}), encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                combine("buy", "positive", "positive", str(broken_path))

    def test_08_missing_rule_file_raises_filenotfounderror(self):
        with self.assertRaises(FileNotFoundError):
            combine("buy", "positive", "positive", str(RULES_DIR / "rule_v9999_missing.json"))


if __name__ == "__main__":
    unittest.main()
