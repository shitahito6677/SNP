# AUTORUN STATE (อ่านไฟล์นี้ก่อนทำงานทุกครั้ง)

- อัปเดตล่าสุด: 2026-09-27 — จบ round 001
- branch: feature/model-a-rebuild (push เฉพาะ branch นี้; ปิดบัง token ใน output ของ git)
- เกณฑ์ล็อกใน: `model_A/PREREG_AUTORUN.md` (ห้ามแก้) — ความเบี่ยงเบน: `autorun/DEVIATIONS.md`
- held-out lock: `lib/guard.py` (cutoff 2023-06-30; FINAL_EVAL=1 เฉพาะขั้น Final)
- trial สะสม: **45** (v1 12 + r001 33) — `model_A/trials.csv`
- ผู้เข้ารอบ (ผ่าน S1+S2+S3+S6): **ยังไม่มี** — ใกล้สุด `r001_Q_LOWACC_overall` (ผ่าน S1/S2/S6, DSR 0.860)
- ตระกูลที่ held-out ถูกใช้แล้ว: ยังไม่มี
- โครงสร้างโค้ด: `lib/panel.py` (panel หุ้น×วัน, cache `data/interim/panel_<tag>.parquet`), `lib/strategy.py` (เลือกหุ้น/รัน/บันทึก),
  `lib/criteria.py` (S1/S2/S3/S6, DSR), `lib/reporting.py` (LEADERBOARD + กราฟ), runner ต่อ round: `rounds/round_NNN/run.py`

## แผน round
| round | ตระกูล | สถานะ |
|---|---|---|
| 001 | A สัญญาณเดี่ยว | ✅ เสร็จ — ไม่มีผู้เข้ารอบ (RESULTS.md) |
| 002 | B คะแนนรวม (quality+value, QARP, quality composite, shareholder yield) | ถัดไป |
| 003 | C สัญญาณราคา + พื้นฐาน×ราคา (monthly panel) | รอ |
| 004 | D การสร้างพอร์ต | รอ |
| 005 | E ตัวคุมความเสี่ยงระดับตลาด | รอ |
| 006 | F ML baseline | รอ |

## สิ่งที่ต้องทำต่อ
1. เขียน `rounds/round_002/HYPOTHESIS.md` → commit → รัน (ใช้ panel annual เดิม)
