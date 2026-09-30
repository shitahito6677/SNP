# Round 011 — EXPLORE2 T3: opportunistic insider buying (เขียนก่อนรัน)

## ที่มา
Cohen, Malloy & Pomorski (2012) "Decoding Inside Information" — การซื้อขายของ insider แบบ "ไม่เป็นประจำ" (opportunistic) มีข้อมูลเชิงทำนาย
ส่วนแบบประจำ (routine) ไม่มี

## ข้อมูล
SEC Insider Transactions Data Sets 2006Q1–2023Q2 (`lib/insider.py`), เฉพาะบริษัทใน S&P 500 (CIK), รายการ non-derivative
วันที่ใช้ได้ = FILING_DATE (point-in-time); joint filing นับให้เจ้าของคนแรกคนเดียว; **ไม่มีธง 10b5-1 ก่อน 2023 → ตัดไม่ได้ (ข้อจำกัด)**

## นิยาม (CMP 2012)
- insider i ในปี Y จัดกลุ่มได้เมื่อมีรายการซื้อขาย (code P หรือ S) ในทุกปี Y−3, Y−2, Y−1
- routine = มีเดือนปฏิทินเดียวกันที่ซื้อขายในทั้งสามปีนั้น; ที่เหลือ = opportunistic; ที่จัดกลุ่มไม่ได้ = ไม่ใช้
- สัญญาณ ณ สิ้นเดือน R: **จำนวนรายการซื้อในตลาด (TRANS_CODE = P) ของ insider แบบ opportunistic ที่ยื่นใน 6 เดือนย้อนหลัง** (สัญญาณ > 0 = มีการซื้อ)

## Trial (2 → สะสม 123)
1. `r011_INSIDER_OPP_BUY_M`: rebalance รายเดือน ถือ EW ทุกหุ้นใน U(R) ที่สัญญาณ > 0; benchmark EW(U) รายเดือน
   (จำนวนหุ้นต่อเดือนถูกรายงาน; ถ้า < 20 ตัวในเดือนส่วนใหญ่ → บันทึกว่า "ใช้กับ S&P 500 ไม่ได้" และ S6 จะตก)
2. `r011_LOWACC_INSIDER_TILT`: พอร์ต `r001_Q_LOWACC_overall` (top 20% ขั้นต่ำ 50, รายปี มิ.ย.) แต่หุ้นที่สัญญาณ ณ มิ.ย. > 0 ได้น้ำหนัก 2 เท่า
   (ตัวอื่น 1 เท่า แล้ว normalize); benchmark EW(U) รายปี
- S5: ไม่มี factor proxy อิสระของ insider → ตก S5 โดยอัตโนมัติ (สูงสุดระดับ B)
- grid S4 (เฉพาะผู้เข้ารอบ): หน้าต่างสัญญาณ ∈ {3, 6, 12 เดือน}; น้ำหนัก tilt ∈ {1.5, 2, 3}
## ความคาดหมาย: หุ้นใหญ่มี opportunistic buying น้อย → จำนวนหุ้นต่อเดือนน่าจะน้อย ผลไม่น่าผ่าน S6/S1
