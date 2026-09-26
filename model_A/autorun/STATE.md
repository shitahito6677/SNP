# AUTORUN STATE (อ่านไฟล์นี้ก่อนทำงานทุกครั้ง)

- อัปเดตล่าสุด: 2026-09-27 — setup (round 000)
- branch: feature/model-a-rebuild (push เฉพาะ branch นี้)
- เกณฑ์ล็อกใน: `model_A/PREREG_AUTORUN.md` (ห้ามแก้) — ความเบี่ยงเบนบันทึกใน `autorun/DEVIATIONS.md`
- held-out lock: `lib/guard.py` (cutoff 2023-06-30; FINAL_EVAL=1 เฉพาะขั้น Final)
- trial สะสม: 12 (v1) — ดู `model_A/trials.csv`
- ผู้เข้ารอบ (ผ่าน S1+S2+S3+S6): ยังไม่มี
- ตระกูลที่ held-out ถูกใช้แล้ว: ยังไม่มี

## แผน round
| round | ตระกูล | สถานะ |
|---|---|---|
| 001 | A สัญญาณเดี่ยว (annual, top 20%/floor 50, overall + sector-neutral) | ถัดไป |
| 002 | B คะแนนรวม (quality+value, QARP, shareholder yield) | รอ |
| 003 | C สัญญาณราคา + พื้นฐาน×ราคา (monthly/quarterly panel) | รอ |
| 004 | D การสร้างพอร์ต (น้ำหนัก, ความถี่, คุม turnover, sector cap) | รอ |
| 005 | E ตัวคุมความเสี่ยงระดับตลาด | รอ |
| 006 | F ML baseline (walk-forward GBM → กฎจาก tree ตื้น) | รอ |

## สิ่งที่ต้องทำต่อ
1. rebuild annual facts (field ใหม่สำหรับ Altman/Beneish/shareholder yield) → เขียน HYPOTHESIS round 001 → commit → รัน
