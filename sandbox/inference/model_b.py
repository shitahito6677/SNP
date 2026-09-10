"""
Model B — FinBERT Company News Sentiment — inference interface.

STUB — replace with real model when ready.

โมเดลจริง (ยังไม่ได้เขียน ณ วันที่สร้างไฟล์นี้ — ดู experiments/log.md) จะรับ headline ข่าว
รายบริษัท ผ่าน FinBERT fine-tuned เพื่อจับ sentiment ต่อหุ้นตัวนั้น ตอนสลับเป็นของจริง
ให้คง function signature `predict(headline, ticker) -> dict` กับ key ใน return dict ให้
เหมือนเดิมทุกตัว (ดู sandbox/inference/README.md สำหรับ contract เต็ม) แล้วลบ `is_stub` /
เปลี่ยนเป็น False, ลบ dependency บน `_stub_utils` ออก
"""

from sandbox.inference._stub_utils import deterministic_seed, pick_class, pick_score

CLASSES = ["positive", "neutral", "negative"]

# module-level flag ให้ caller เช็คได้ถูกๆ (ไม่ต้องเรียก predict() จริง) ว่ายังเป็น stub อยู่ไหม
# — เปลี่ยนเป็น False ตอน swap เป็นโมเดลจริง (ดู sandbox/inference/README.md)
IS_STUB = True


def predict(headline: str, ticker: str) -> dict:
    """
    STUB — replace with real model when ready.

    Args:
        headline: ข้อความข่าวรายบริษัท (free text)
        ticker: stock ticker symbol เช่น "NVDA" (ต้องอยู่ใน sandbox.config.TICKERS)

    Returns:
        dict:
            class (str): "positive" | "neutral" | "negative"
            score (float): confidence ของ class ที่เลือก อยู่ในช่วง [0, 1]
            is_stub (bool): True เสมอ จนกว่าจะสลับเป็นโมเดลจริง (ค่อยเป็น False)
    """
    seed = deterministic_seed("model_b", headline, ticker)
    return {
        "class": pick_class(seed, CLASSES),
        "score": pick_score(seed),
        "is_stub": True,
    }
