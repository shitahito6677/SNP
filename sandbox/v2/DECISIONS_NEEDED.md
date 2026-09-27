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
