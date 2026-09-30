"""
Unit test สำหรับ sandbox/engine/combine.py + sandbox/rules/rule_v1_logic.py
(DoD เดิม: "unit test combine() อย่างน้อย 5 case ผ่าน") ใช้ unittest จาก stdlib

รัน (จาก project root): python3 -m unittest sandbox.scripts.test_combine -v
"""

import json
import tempfile
import unittest
from pathlib import Path

from sandbox.engine.combine import combine
from sandbox.rules import rule_v1_logic
from sandbox.rules.versions import RULES_DIR, latest_version, load_version, version_path


class TestRuleV1Logic(unittest.TestCase):
    """เทส decide() ตรงๆ (ไม่ผ่านไฟล์ JSON) — logic: "A เป็นหลัก, B/C เป็น veto" """

    def test_01_buy_with_no_veto_stays_buy(self):
        self.assertEqual(rule_v1_logic.decide("buy", "positive", "positive"), "buy")
        self.assertEqual(rule_v1_logic.decide("buy", "neutral", "neutral"), "buy")

    def test_02_buy_vetoed_by_negative_b(self):
        self.assertEqual(rule_v1_logic.decide("buy", "negative", "positive"), "hold")

    def test_03_buy_vetoed_by_negative_c(self):
        self.assertEqual(rule_v1_logic.decide("buy", "positive", "negative"), "hold")

    def test_04_sell_with_no_veto_stays_sell(self):
        self.assertEqual(rule_v1_logic.decide("sell", "negative", "negative"), "sell")
        self.assertEqual(rule_v1_logic.decide("sell", "neutral", "neutral"), "sell")

    def test_05_sell_vetoed_by_positive_b(self):
        self.assertEqual(rule_v1_logic.decide("sell", "positive", "negative"), "hold")

    def test_06_sell_vetoed_by_positive_c(self):
        self.assertEqual(rule_v1_logic.decide("sell", "negative", "positive"), "hold")

    def test_07_hold_always_stays_hold_regardless_of_bc(self):
        for b in ("positive", "neutral", "negative"):
            for c in ("positive", "neutral", "negative"):
                self.assertEqual(rule_v1_logic.decide("hold", b, c), "hold")

    def test_08_all_27_combinations_return_valid_decision(self):
        for a in ("buy", "hold", "sell"):
            for b in ("positive", "neutral", "negative"):
                for c in ("positive", "neutral", "negative"):
                    self.assertIn(rule_v1_logic.decide(a, b, c), {"buy", "hold", "sell"})


class TestCombineAgainstLatestRuleVersion(unittest.TestCase):
    """เทส combine() กับ rule_v1.json จริงที่ repo ใช้อยู่ (ไม่ mock) — regenerated จาก
    rule_v1_logic.decide() ผ่าน generate_rule_table.py ต้องตรงกับผลของ decide() ตรงๆ เป๊ะ"""

    @classmethod
    def setUpClass(cls):
        cls.n = latest_version()
        cls.path = str(version_path(cls.n))
        cls.payload = load_version(cls.n)

    def test_09_json_table_matches_decide_function_exactly(self):
        # rule_v1.json ต้องเป็นผลลัพธ์ของ rule_v1_logic.decide() เป๊ะทุกแถว (regenerate แล้ว
        # ต้องตรงกัน ไม่งั้นแปลว่ามีคนแก้ JSON มือหรือ generator พัง)
        for row in self.payload["table"]:
            expected = rule_v1_logic.decide(row["a"], row["b"], row["c"])
            self.assertEqual(
                row["decision"], expected,
                f"rule_v1.json มี {row} แต่ decide() ให้ {expected!r}",
            )

    def test_10_combine_reads_through_to_decide_correctly(self):
        self.assertEqual(combine("buy", "positive", "positive", self.path), "buy")
        self.assertEqual(combine("buy", "negative", "positive", self.path), "hold")
        self.assertEqual(combine("sell", "positive", "negative", self.path), "hold")

    def test_11_all_27_combinations_resolve_without_error(self):
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

    def test_12_missing_combination_raises_valueerror_not_fallback(self):
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

    def test_13_missing_rule_file_raises_filenotfounderror(self):
        with self.assertRaises(FileNotFoundError):
            combine("buy", "positive", "positive", str(RULES_DIR / "rule_v9999_missing.json"))


if __name__ == "__main__":
    unittest.main()
