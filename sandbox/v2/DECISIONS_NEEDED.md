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

## 9. (F1) ไฟล์ fixture `manual_news_sample.csv` — ไม่มีวางไว้ตอนเริ่มงาน
- สเปคบอกว่าผู้ใช้จะ copy ไฟล์มาวางที่ `sandbox/v2/tests/fixtures/` แต่ตอนเริ่มงานยังไม่มี
- เจอ 2 ไฟล์ที่ header ตรงกับที่สเปคบรรยาย: `~/Desktop/model_b_pilot_META_news.csv` (META ล้วน 9 แถว, 2021-10-25 → 2023-04-26) และ `~/Downloads/model_b_pilot_META_news.csv` (20 แถว, 7 ticker)
- **เลือก:** copy ไฟล์บน Desktop เป็น fixture — META ทุกแถวและช่วงวันที่ตรงกับสเปคเป๊ะ; **ไฟล์มี 10 บรรทัด = หัวตาราง 1 + ข่าว 9 แถว** (สเปคเขียน "10 แถว" — test ตรวจ 9 แถวตามไฟล์จริง)
- ไฟล์ 20 แถวใน Downloads ก็นำเข้าได้ครบ 20/20 (ตรวจด้วยมือ ไม่ได้ใส่ใน test)
- ย้อนกลับ: วางไฟล์ที่ถูกต้องทับ แล้วแก้ `EXPECTED_ROWS` ใน `tests/test_csv_import.py`

## 10. (F1) label ตัวเลข -2..+2 → สเกลภายใน
- ระบบเดิมใช้ 3 ระดับ `sentiment` ∈ {positive, neutral, negative} + `score` ∈ {1, 0, -1} (condition/B/C อ่านทั้ง `class` และ `score`)
- **เลือก:** class ตามเครื่องหมาย (>0 positive, 0 neutral, <0 negative); `score = label / สเกล` → -2 → **-1.0** (แย่สุด = เท่ากับข่าว negative ที่พิมพ์เอง), -1 → -0.5, +1 → +0.5, +2 → +1.0; เก็บค่าดิบใน `label_raw` + `label_scale` ("±2")
- สเกลอ่านจากหัว column (`(-2..+2)`) ถ้ามี ไม่งั้นใช้ |label| สูงสุดในไฟล์ (ปัดขึ้น); ค่านอกสเกล/ข้อความที่ไม่รู้จัก → ข้ามแถวพร้อมเหตุผล (ไม่เดา)
- ถ้าผู้ใช้เปลี่ยน sentiment ในหน้า preview → score กลับเป็น ±1/0 ตาม class (ค่าดิบยังเก็บไว้)
- ย้อนกลับ/ปรับ: `parse_label()` ใน `news.py`

## 11. (F1) หา 500 ของ CSV ตามภาพไม่เจอ — เจอแค่ 400
- รันไฟล์ fixture ผ่าน endpoint จริง (test client, server ที่ผู้ใช้เปิดอยู่ port 5090, server ใหม่แบบ cold start + request พร้อมกัน, และลากไฟล์ผ่าน UI ด้วย Playwright): **ได้ 400 `หา column headline ไม่เจอ` ทุกครั้ง ไม่ใช่ 500** (โค้ด news/server ไม่เปลี่ยนตั้งแต่ W7)
- root cause ของ "นำเข้าไม่ได้" ที่ยืนยันได้ = mapping เดิม match ชื่อ column แบบตรงตัว (`headline`, `title`…) → column `ข่าวแบบย่อ (short_news)` ไม่ match เลย
- 500 ในภาพอาจมาจาก request อื่น/สถานะอื่นที่ reproduce ไม่ได้ → **ไม่เดา**; ใส่ global error handler: exception ใด ๆ → JSON ภาษาไทย + `error_id` + traceback เต็มใน `sandbox/v2/logs/server.log` — ถ้าเจออีก ให้ค้น `error_id` ใน log
