# Round 012 — EXPLORE2 T4: "Lazy Prices" (การเปลี่ยนถ้อยคำใน 10-K) (เขียนก่อนรัน)

## ที่มา
Cohen, Malloy & Nguyen (2020) "Lazy Prices" — บริษัทที่ 10-K เปลี่ยนน้อย (similarity สูง) ได้ผลตอบแทนดีกว่า โดยเฉพาะส่วน Risk Factors;
มีงาน replicate ด้วยข้อมูลฟรีหลังตีพิมพ์ใน S&P 100 ที่ไม่พบผล → **คาดหวังต่ำ**

## ข้อมูล (`lib/lazyprices.py`)
- 10-K (และ 10-K405/10-KT) ของบริษัทที่เป็นสมาชิก S&P 500 (CIK จาก cik_segments), filed 2010-01-01 – 2023-06-30 (held-out lock)
- ไฟล์เอกสารหลัก (primaryDocument) จาก SEC submissions API; User-Agent ระบุตัวตน; ≤ 8 คำขอ/วินาที; cache ความถี่คำ ลบ HTML หลังประมวลผล
- **ไม่ใช้ LLM** — วิธีคลาสสิกเท่านั้น: ตัด HTML → คำภาษาอังกฤษตัวพิมพ์เล็ก (a–z, ≥ 2 ตัวอักษร) → term frequency
- Item 1A: ช่วงข้อความจาก "Item 1A ... Risk Factors" ถึง "Item 1B" หรือ "Item 2" ที่ยาวที่สุด (< 1,000 ตัวอักษร = ไม่มี)
- similarity ของ 10-K ปีนี้กับ 10-K ก่อนหน้าของบริษัทเดียวกัน (ห่าง 9–15 เดือน): cosine (TF) และ Jaccard (ชุดคำ)

## Trial (2 → สะสม 125)
- rebalance รายเดือน; ณ R ใช้ similarity ของ 10-K ล่าสุดที่ filed ≤ R − 1 วัน (ไม่เก่ากว่า 15 เดือน)
- ถือ **quintile ที่ similarity สูงสุด** (เปลี่ยนน้อย) EW; ขั้นต่ำ 50 ตัว (ถ้า quintile < 50 ใช้ 50 อันดับแรก); benchmark EW(U) รายเดือน
1. `r012_LAZY_COS_FULL` — cosine ทั้งเอกสาร
2. `r012_LAZY_COS_1A` — cosine เฉพาะ Item 1A
- Jaccard รายงานเป็นข้อมูลประกอบ (correlation กับ cosine) ไม่นับ trial
- S5: ไม่มี factor proxy → ตก S5 อัตโนมัติ
## งบเวลาเตรียมข้อมูล: 2 ชั่วโมงนับจาก 10:19 — ถ้าไม่ครบจะหยุด บันทึก DEVIATIONS และรายงานว่าทำไม่ได้/ทำได้บางส่วน (ไม่ประเมินจากข้อมูลไม่ครบ)
