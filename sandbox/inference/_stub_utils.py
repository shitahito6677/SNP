"""
Helper ที่ใช้ร่วมกันระหว่าง stub ทั้ง 3 ตัว (model_a/b/c) — ไม่ใช่ inference จริง
แค่ทำให้ output ของ stub deterministic (seed จาก input string) และ format สม่ำเสมอ

จะถูกลบทิ้งได้เมื่อ stub ทั้งหมดถูกแทนที่ด้วยโมเดลจริงแล้ว
"""

import hashlib


def deterministic_seed(*parts: str) -> int:
    """
    สร้าง int seed แบบ deterministic จาก string หลายส่วน (เช่น ticker+date, headline+ticker)
    ใช้ sha256 แทน built-in hash() เพราะ hash() ของ str ถูกสุ่มด้วย PYTHONHASHSEED
    คนละ process — ผลจะไม่เท่ากันระหว่างการรันแต่ละครั้ง ขัดกับ requirement ที่ต้อง
    deterministic ข้ามการรัน (ไม่ใช่แค่ข้าม call ใน process เดียว)
    """
    key = "|".join(parts).encode("utf-8")
    return int(hashlib.sha256(key).hexdigest(), 16)


def pick_class(seed: int, classes: list) -> str:
    return classes[seed % len(classes)]


def pick_score(seed: int, low: float = 0.34, high: float = 1.0) -> float:
    """สุ่ม (deterministic) score ในช่วง [low, high] — เลข 0.34 กันไม่ให้ score ต่ำกว่า
    1/3 ซึ่งจะดูเหมือน "ไม่มั่นใจกว่า random guess ของ 3 class" จนแปลกตา"""
    span = high - low
    frac = (seed // 7) % 1000 / 1000  # ใช้ digit คนละตำแหน่งกับที่ pick_class ใช้ (mod len(classes))
    return round(low + span * frac, 4)
