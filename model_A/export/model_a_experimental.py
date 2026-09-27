"""
ตัวเชื่อมที่ signature ตรงกับ sandbox/inference/model_a.py: predict(ticker, date) -> dict และค่าคงที่ IS_STUB
เลือกกฎด้วย environment variable MODEL_A_RULE = "rule1" (ค่าเริ่มต้น) หรือ "rule2"

⚠️ ทดลองระบบ ข้อมูลไม่ครบ ไม่ใช่หลักฐานว่ากฎชนะตลาด — ห้ามใช้ผลใน sandbox เลือกหรือปรับกฎ
"""
import os

from .adapter import DISCLAIMER, IS_STUB, MODEL_VERSION, predict as _predict  # noqa: F401


def predict(ticker: str, date: str) -> dict:
    return _predict(ticker, date, os.environ.get("MODEL_A_RULE", "rule1"))
