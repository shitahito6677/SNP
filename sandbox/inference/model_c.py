"""
Model C — Macro/FOMC News → Qwen → FinBERT → XGBoost (per GICS sector) — inference
interface.

STUB — replace with real model when ready.

โมเดลจริงมีโค้ด train ครบแล้ว (`src/s1_fetch_news.py` .. `src/s4_sentiment.py`,
`experiments/exp_02_full_pipeline/train.py`) แต่ยังไม่ได้ wrap เป็น inference function
เดียวที่รับ headline สด ๆ แล้วคืนสัญญาณ — ดู experiments/log.md ตอนสลับเป็นของจริง ให้คง
function signature `predict(headline, sector) -> dict` กับ key ใน return dict ให้เหมือนเดิม
ทุกตัว (ดู sandbox/inference/README.md สำหรับ contract เต็ม) แล้วลบ `is_stub` / เปลี่ยนเป็น
False, ลบ dependency บน `_stub_utils` ออก

หมายเหตุ: exp_01/exp_02 (ดู experiments/log.md) แสดงว่า pipeline เต็มตัว ณ ตอนนี้ยังไม่ดีกว่า
baseline (macro F1 แย่ลงเมื่อเพิ่ม sentiment feature) — ตอน wrap เป็นของจริงควรพิจารณาแก้
คุณภาพ sentiment signal ก่อนตามที่บันทึกไว้ใน exp_02
"""

from sandbox.inference._stub_utils import deterministic_seed, pick_class, pick_score

CLASSES = ["positive", "neutral", "negative"]


def predict(headline: str, sector: str) -> dict:
    """
    STUB — replace with real model when ready.

    Args:
        headline: ข้อความข่าวมหภาค/FOMC (free text)
        sector: sector ETF code เช่น "XLK" (ไม่ใช่ GICS sector name — ต้องอยู่ใน
            sandbox.config.SECTOR_ETF.values(), ใช้ sandbox.config.ticker_to_etf(ticker)
            เพื่อแปลงจาก ticker)

    Returns:
        dict:
            class (str): "positive" | "neutral" | "negative"
            score (float): confidence ของ class ที่เลือก อยู่ในช่วง [0, 1]
            is_stub (bool): True เสมอ จนกว่าจะสลับเป็นโมเดลจริง (ค่อยเป็น False)
    """
    seed = deterministic_seed("model_c", headline, sector)
    return {
        "class": pick_class(seed, CLASSES),
        "score": pick_score(seed),
        "is_stub": True,
    }
