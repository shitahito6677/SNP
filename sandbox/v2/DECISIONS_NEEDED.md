# DECISIONS NEEDED — Sandbox v2

รูปแบบ: เรื่อง / ตัวเลือก / เลือกอะไรไป / ย้อนกลับยังไง
(โหมด unattended: เลือกทางที่ย้อนกลับง่ายที่สุดแล้วทำต่อ — ผู้ใช้ตรวจทีหลังได้)

## 1. `model_c_rulebase/` ไม่อยู่บน branch ฐาน (PR #1/#2 ยังไม่ merge)
- ตัวเลือก: (ก) merge branch PR #2 เข้ามา (ข) copy เฉพาะโฟลเดอร์ `model_c_rulebase/` แบบไม่แก้ (ค) รอ merge
- **เลือก (ข)** — commit `c3dede5`, ไฟล์ byte-identical กับ branch PR → merge PR ทีหลังไม่ conflict
- ย้อนกลับ: `git revert c3dede5` (และ build_export/manifest ของ C จะหายไปด้วย)

## 2. ช่วงราคา 5 ปี (PRICE_START = 2021-09-27) สั้นเกินสำหรับ rule รายปี
- ช่วงก่อน held-out มีแค่ ~21 เดือน → Model A รายปี rebalance ได้แค่ 2 รอบ (มิ.ย. 2021 ที่ถือต่อมา, มิ.ย. 2022)
- **เลือก:** default 5 ปีตามที่ผู้ใช้ขอ; เปลี่ยนเป็น `"2010-06-01"` ได้โดยแก้บรรทัดเดียวใน `sandbox/v2/config.py` แล้วรัน `python3 -m sandbox.v2.scripts.update_prices`
- ตัว signal ของ A สร้างไว้ครบตั้งแต่ 2011-06 อยู่แล้ว (ไม่ต้องสร้างใหม่เมื่อขยายช่วงราคา)

## 3. Model A execution timing ต่างจาก backtest เดิม
- Model A backtest: ซื้อที่ close วัน R / sandbox v2: `next_close` (R+1) ตามสเปค
- **เลือก:** ตามสเปค (next_close) — ผลไม่เท่ากับ NAV ของ Model A เป๊ะ; แสดงเป็นข้อจำกัดในหน้า About
- ย้อนกลับ: `EXECUTION` ใน config (ยังไม่รองรับ same-close — ถ้าต้องการต้องเพิ่ม)

## 4. Legacy v1 ไม่ mount เป็น blueprint
- v1 สร้าง `app` แบบ module-global และห้ามแก้ v1 → ลิงก์ไป `http://127.0.0.1:5050` (รัน v1 แยก)

## 5. Model C rulebase: `vix_p90` ใช้ข้อมูลทั้งช่วง (look-ahead เล็กน้อยใน exp_03)
- ไม่แก้โค้ด exp_03 (ห้ามแก้ข้อมูล/ผลของ exp_01–04) → ใช้ตามเดิมและติดป้ายใน manifest `notes`
- ถ้าต้องการ strict: เขียน export version ใหม่ที่คำนวณ `vix_p90` แบบ expanding window (ยังไม่ได้ทำ)

## 6. commit ไฟล์ signal (parquet) ของ export
- สเปคห้าม commit ราคา/parquet ของผลทดลอง แต่ signal ของโมเดลไม่ใช่ราคาดิบ และ **สร้างใหม่ไม่ได้ถ้าไม่มี `model_A/data/` (gitignored, 3 GB)**
- **เลือก:** commit `model_A/export/A*/signals.parquet` (~3.8 MB), `model_c_rulebase/export/rulebase-exp03/signals.parquet`, `sandbox/v2/stubs/*` (~0.3 MB)
- ย้อนกลับ: เพิ่ม `model_A/export/*/signals.parquet` ใน .gitignore แล้ว `git rm --cached`

## 7. Model C rulebase: ช่วง sandbox อยู่ใน test set ของ exp_03 ทั้งหมด
- exp_03 แบ่ง train/test ตามเวลา: test เริ่ม **2020-12-02** และ R5 "ห้ามแตะ test set จนกว่า R6 เสร็จ" — R6 ตัดสินแล้ว (negative, ไม่ calibrate)
- การรัน sandbox ด้วย C rulebase-exp03 = ดูผลของ engine (ที่ไม่ได้ calibrate) บนช่วง test → **ไม่ควรเอาผล sandbox ไปปรับ engine ของ exp_03**
- ติดคำเตือนใน manifest + reasons ของทุกแถวที่อยู่ใน test set แล้ว

## 8. class ของ C rulebase: neutral band ±0.10
- engine ให้ score ต่อเนื่อง ไม่มี class → ตั้ง |score| ≤ 0.10 = neutral (ค่าแสดงผล **ไม่ได้ tune** กับผลตอบแทน)
- ย้อนกลับ/ปรับ: `NEUTRAL_BAND` ใน `model_c_rulebase/export/build_export.py` แล้วรันใหม่ (condition ใช้ `score` ดิบได้อยู่แล้ว)
