"""
r2_shock_classification.py — Phase R2: Jarociński–Karadi (2020) sign-restriction shock
classification สำหรับ Model C rule-based sector impact engine

ทฤษฎี: Jarociński & Karadi (2020) แยกผลของแถลงการณ์ธนาคารกลางออกเป็น 2 มิติพร้อมกันด้วย
sign restriction ของ (การเปลี่ยนแปลงดอกเบี้ยระยะสั้น, ผลตอบแทนหุ้นกว้าง) ในวันประกาศเดียวกัน:

    rate_surprise (+) & equity_move (−)  -> policy_tightening  (ตึงตัวจริง ตลาดตกใจดอกเบี้ยขึ้น)
    rate_surprise (+) & equity_move (+)  -> info_positive      (ดอกเบี้ยขึ้นแต่ตลาดอ่านว่า
                                                                  Fed มองเศรษฐกิจแข็งแรง — Fed
                                                                  information/Delphic effect,
                                                                  Nakamura & Steinsson 2018)
    rate_surprise (−) & equity_move (+)  -> policy_easing      (ผ่อนคลายจริง ตลาดชอบ)
    rate_surprise (−) & equity_move (−)  -> info_negative      (ดอกเบี้ยลงแต่ตลาดตกใจไปกับ Fed
                                                                  ว่าเศรษฐกิจแย่กว่าที่คิด)

สำคัญ (ย้ำจากสเปค): `policy_tightening` กับ `info_positive` ดอกเบี้ยขึ้นเหมือนกัน (rate_surprise
บวกทั้งคู่) แต่ทิศทางผลต่อ sector ตรงข้ามกันเกือบทั้งหมดเพราะกลไกคนละอย่าง (ตึงตัวจริงทำร้าย
cyclical, ส่วน info positive หนุน cyclical) — เป็นเหตุผลที่ต้องแยกให้ชัดในชั้นนี้ก่อนส่งต่อ
ไปยัง rule engine (R4) ไม่ให้ rule ใช้แค่เครื่องหมายดอกเบี้ยเฉยๆ

Input : model_c_rulebase/data/fomc_market_context.csv (จาก R1 — ไม่แก้ค่า rate_surprise/
        equity_move ใดๆ ในไฟล์นี้)
Output: เขียนทับไฟล์เดิม เพิ่มคอลัมน์ `shock_type`

กรณีพิเศษ "ห้ามเดา": ถ้า `rate_surprise == 0` เป๊ะ (DGS2 ไม่เปลี่ยนแปลงเลยเทียบวันก่อน — พบจริง
58/452 = 12.8% ของข่าว กระจุกตัวช่วง ZIRP 2009-2018 ที่ยีลด์ 2 ปีแทบไม่ขยับเพราะดอกเบี้ยนโยบาย
ติดที่ 0 เป็นเวลานาน ไม่ใช่บั๊ก) ไม่มีทิศทางให้ใช้จัด quadrant ได้จริง — ใส่ `shock_type =
"no_rate_surprise"` แยกออกมาต่างหาก **ไม่เดาว่าควรเอนไปทาง quadrant ไหน**
(`equity_move` ไม่เคยเป็น 0 เป๊ะเลยในข้อมูลจริง 452 ข่าว จึงไม่ต้องมีกรณีพิเศษฝั่งนั้น)

รัน (จาก project root): python3 -m model_c_rulebase.scripts.r2_shock_classification
"""

import logging
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CTX_PATH = PROJECT_ROOT / "model_c_rulebase" / "data" / "fomc_market_context.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("r2_shock_classification")


def classify(rate_surprise: float, equity_move: float) -> str:
    if rate_surprise == 0:
        return "no_rate_surprise"
    if rate_surprise > 0 and equity_move < 0:
        return "policy_tightening"
    if rate_surprise > 0 and equity_move > 0:
        return "info_positive"
    if rate_surprise < 0 and equity_move > 0:
        return "policy_easing"
    return "info_negative"  # rate_surprise < 0 and equity_move < 0


# 5 เคสที่รู้คำตอบล่วงหน้าจากประวัติศาสตร์ตลาดจริง (ไม่ใช่เดา — เหตุการณ์ที่มีบันทึกทาง
# ประวัติศาสตร์ชัดเจน) ใช้ตรวจว่า pipeline ไม่ได้พังทั้งที่รันผ่านโดยไม่ error
KNOWN_CASES = [
    ("2020-03-03", "emergency 50bp cut กลางเดือน ก่อนตลาดจะรู้ขนาดวิกฤต COVID เต็มที่ — "
                    "ตลาดตกใจว่า Fed ต้องรีบลดฉุกเฉิน (ไม่ใช่ปกติ) มากกว่าดีใจที่ได้ลด",
     "info_negative"),
    ("2020-03-15", "ประกาศวันอาทิตย์ ลดเหลือ 0% + QE ขนาดใหญ่ ตลาดตอบสนองวันจันทร์ถัดมา "
                    "(t0 เลื่อนเป็น 16 มี.ค. ตาม trading calendar) ด้วยการร่วงหนักที่สุดวันหนึ่งใน "
                    "ประวัติศาสตร์ (Black Monday 2020) — หมายเหตุ: ค้นด้วยวันที่ข่าว (`date`) "
                    "ไม่ใช่ `t0` เพราะ market context ผูกกับ trading day ถัดไป",
     "info_negative"),
    ("2015-12-16", "ขึ้นดอกเบี้ยครั้งแรกในรอบเกือบ 10 ปี แต่ telegraphed ไว้ล่วงหน้าจนตลาดรู้ทัน "
                    "เต็มที่ — ตลาดตอบรับเชิงบวก (relief rally) เพราะการขึ้นดอกเบี้ยครั้งนี้ถูกอ่านว่า "
                    "Fed มั่นใจเศรษฐกิจแข็งแรงพอ ไม่ใช่สัญญาณตึงตัวเกินคาด",
     "info_positive"),
    ("2007-09-18", "cut แรกของรอบ easing วิกฤต subprime 50bp ทั้งที่ตลาดคาด 25bp — ทั้งฝั่งบอนด์ "
                    "(DGS2 ลง) และฝั่งหุ้น (S&P +2.9% วันนั้น) เคลื่อนไหวไปทางเดียวกันชัดเจน ไม่มี "
                    "ความกำกวมแบบ intermeeting cut — เคสสะอาดที่สุดของ policy_easing ในชุดข้อมูลนี้",
     "policy_easing"),
    ("2008-09-16", "1 วันหลัง Lehman Brothers ล้มละลาย Fed คงดอกเบี้ยไว้เท่าเดิม (ไม่ลดทั้งที่ "
                    "ตลาดคาดหวังว่าจะลด) ตลาดหุ้นยังคงผันผวนหนักจากวิกฤตการเงินเอง ไม่ใช่จาก FOMC "
                    "โดยตรง — คาดว่า rate_surprise ใกล้ 0 หรือเป็นบวกเล็กน้อย (ไม่ได้ลดตามคาด) "
                    "equity_move ขึ้นกับข่าววิกฤตธนาคารมากกว่า",
     None),  # ไม่ผูกคำตอบตายตัว เพราะมี confound จากข่าว Lehman เอง — ดูไว้เป็นข้อมูลประกอบเท่านั้น
    ("2001-01-03", "ลดดอกเบี้ยฉุกเฉิน 50bp นอกรอบประชุมปกติ (intermeeting cut) — Nasdaq +14% "
                    "วันนั้น (ข้อเท็จจริงทางประวัติศาสตร์ที่ชัดเจน) แต่ตรวจ DGS2 จริงจาก FRED "
                    "(4.87 -> 4.92, +0.05, วันที่ 2 ม.ค. -> 3 ม.ค.) พบว่า 2yr yield ขยับขึ้นเล็กน้อย "
                    "วันประกาศเอง ก่อนจะร่วงต่อเนื่องวันถัดๆ ไป (4.92 -> 4.77 -> 4.56 -> 4.54) — "
                    "ไม่ใช่บั๊ก เป็นข้อจำกัดจริงของนิยาม rate_surprise=ΔDGS2 วันเดียว: 2yr yield "
                    "ฝัง forward-path expectation ไว้แล้วล่วงหน้า การ cut แบบ intermeeting/ฉุกเฉิน "
                    "ที่สุดโต่งจึงมี cross-current ทำให้ปฏิกิริยาวันแรกซับซ้อนกว่าที่สัญชาตญาณ "
                    "('cut = ราคาพันธบัตรขึ้น yield ลง') บอกไว้ — เหตุนี้จึง **ไม่ผูกคำตอบตายตัว** "
                    "กับเคสนี้ (บทเรียนสำคัญ: อย่าเดาคำตอบ known-case จากความจำ ต้องเช็คข้อมูลจริง "
                    "ก่อนตั้งเป็นเกณฑ์ตัดสิน — เจอจริงตอน dev script นี้ เดิมตั้งคาดไว้ว่าต้องได้ "
                    "policy_easing จากความจำ 'ตลาดขึ้นแรง' เฉยๆ โดยไม่ได้เช็ค DGS2 ก่อน)",
     None),
]


def main():
    df = pd.read_csv(CTX_PATH)
    df["date"] = pd.to_datetime(df["date"])

    df["shock_type"] = df.apply(lambda r: classify(r["rate_surprise"], r["equity_move"]), axis=1)

    log.info("=" * 60)
    log.info("SUMMARY — Phase R2: การกระจาย shock_type (452 ข่าว)")
    log.info("=" * 60)
    counts = df["shock_type"].value_counts()
    for shock_type, n in counts.items():
        log.info(f"  {shock_type:20s}: {n:4d}  ({n/len(df)*100:5.1f}%)")

    log.info("")
    log.info("=" * 60)
    log.info("Spot-check 5 เคสที่รู้คำตอบล่วงหน้า")
    log.info("=" * 60)
    all_match = True
    for date_str, note, expected in KNOWN_CASES:
        row = df[df["date"] == date_str]
        if row.empty:
            log.warning(f"  {date_str}: ไม่พบในข้อมูล (ข้าม)")
            continue
        row = row.iloc[0]
        actual = row["shock_type"]
        log.info(f"  {date_str}: rate_surprise={row['rate_surprise']:+.2f}, "
                  f"equity_move={row['equity_move']:+.2%} -> shock_type={actual}")
        log.info(f"      บริบท: {note}")
        if expected is not None:
            status = "ตรงกับคาด" if actual == expected else "*** ไม่ตรงกับคาด ***"
            log.info(f"      คาดว่า: {expected}  ->  {status}")
            if actual != expected:
                all_match = False
        else:
            log.info(f"      (ไม่ผูกคำตอบตายตัว — เก็บไว้ดูประกอบ)")

    log.info("")
    if all_match:
        log.info("ทุกเคสที่ผูกคำตอบไว้ตรงกับที่คาด — ไปต่อ Phase R3 ได้")
    else:
        log.error("มีเคสที่ไม่ตรงกับคำตอบที่รู้อยู่แล้ว — ต้องหยุดหาบั๊กก่อน ห้ามไปต่อ (ตามกฎที่กำหนดไว้)")

    df.to_csv(CTX_PATH, index=False)
    log.info(f"\nWrote shock_type column back to {CTX_PATH}")

    return df, all_match


if __name__ == "__main__":
    main()
