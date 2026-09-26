"""
Held-out lock (AUTORUN ข้อ 2): ห้ามโหลด/คำนวณ/ดูข้อมูลหลัง 2023-06-30 เว้นแต่ตั้ง FINAL_EVAL=1 (ใช้ได้เฉพาะขั้น Final)

ทุก loader ของข้อมูลที่มีมิติเวลา (ราคา, factor) ต้องผ่านฟังก์ชันในไฟล์นี้:
  - clip(df)      : ตัดแถวหลัง CUTOFF ทิ้ง (ถ้าไม่ได้อยู่ในโหมด FINAL_EVAL)
  - check_end(d)  : raise ถ้าผู้เรียกขอวันที่หลัง CUTOFF ตรง ๆ
"""

import os

import pandas as pd

CUTOFF = pd.Timestamp("2023-06-30")


class HeldOutError(RuntimeError):
    pass


def final_eval() -> bool:
    return os.environ.get("FINAL_EVAL") == "1"


def check_end(end) -> None:
    if end is not None and pd.Timestamp(end) > CUTOFF and not final_eval():
        raise HeldOutError(f"ขอข้อมูลถึง {pd.Timestamp(end).date()} ซึ่งเกิน held-out cutoff {CUTOFF.date()} "
                           "(ตั้ง FINAL_EVAL=1 ได้เฉพาะขั้น Final ตาม AUTORUN ข้อ 5)")


def clip(df):
    if final_eval():
        return df
    return df.loc[:CUTOFF]
