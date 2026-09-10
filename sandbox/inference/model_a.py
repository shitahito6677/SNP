"""
Model A — Piotroski Fundamental Screening — inference interface.

STUB — replace with real model when ready.

โมเดลจริง (ยังไม่ได้เขียน ณ วันที่สร้างไฟล์นี้ — ดู experiments/log.md) จะโหลดงบการเงิน/
fundamental data ของ ticker ในวันที่กำหนด คำนวณ Piotroski F-Score แล้วแปลงเป็นสัญญาณ
buy/hold/sell ตอนสลับเป็นของจริง ให้คง function signature `predict(ticker, date) -> dict`
กับ key ใน return dict ให้เหมือนเดิมทุกตัว (ดู sandbox/inference/README.md สำหรับ contract
เต็ม) แล้วลบ `is_stub` / เปลี่ยนเป็น False, ลบ dependency บน `_stub_utils` ออก
"""

from sandbox.inference._stub_utils import deterministic_seed, pick_class, pick_score

CLASSES = ["buy", "hold", "sell"]


def predict(ticker: str, date: str) -> dict:
    """
    STUB — replace with real model when ready.

    Args:
        ticker: stock ticker symbol เช่น "NVDA" (ต้องอยู่ใน sandbox.config.TICKERS)
        date: ISO date string "YYYY-MM-DD"

    Returns:
        dict:
            class (str): "buy" | "hold" | "sell"
            score (float): confidence ของ class ที่เลือก อยู่ในช่วง [0, 1]
            is_stub (bool): True เสมอ จนกว่าจะสลับเป็นโมเดลจริง (ค่อยเป็น False)
    """
    seed = deterministic_seed("model_a", ticker, date)
    return {
        "class": pick_class(seed, CLASSES),
        "score": pick_score(seed),
        "is_stub": True,
    }
