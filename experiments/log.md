
---
## exp_03 Phase R1 — market data pipeline สำหรับ rule-based sector impact engine — 2026-09-13 11:55

**วิธีที่ใช้:** เริ่ม component ที่ 1 ของ Model C ใหม่ (`feature/model-c-rulebase` branch, แยก
จาก `feature/ensemble-sandbox` เดิม) แนวทางเปลี่ยนจาก "Qwen ตัดสิน sector ตรงๆ" (exp_02, พบ
bias/inconsistent — ดู results.md) เป็น 3 ชั้น: LLM สกัดตัวแปรโครงสร้างอย่างเดียว (R3) → shock
classification จาก market data (R2) → rule base ที่มีทฤษฎีรองรับตัดสิน sector (R4)

Phase R1 นี้: เขียน `model_c_rulebase/scripts/r1_market_data.py` ดึง DGS2, DGS10, DTWEXBGS,
VIXCLS จาก FRED (`fredapi`) + SPY จาก yfinance จับคู่กับวันที่ข่าว 452 ข่าว FOMC/Beige Book
เดิม (จาก `labels.parquet`) คำนวณ rate_surprise (ΔDGS2), equity_move (SPY return),
curve_slope_delta (Δ(DGS10−DGS2)), vix_delta, dxy_delta โดยใช้ trading calendar เดียวกับที่
`s2_build_labels.py` ใช้สร้าง CAR (t0 = trading day แรก >= วันข่าว) เพื่อให้ market context
อ้างอิงช่วงเวลาเดียวกันกับ label เป๊ะ

**ข้อมูลที่ใช้:** `data/processed/labels.parquet` (exp_01/exp_02 เดิม, ไม่แตะ ไม่สร้าง label
ใหม่) — ดึงแค่ (date, source, url) unique = 452 ข่าว, FRED 4 series (DGS2 n=12,566 ตั้งแต่
1976, DGS10 n=16,158 ตั้งแต่ 1962, VIXCLS n=9,271 ตั้งแต่ 1990, DTWEXBGS n=5,184 ตั้งแต่
2006-01-02 เท่านั้น), SPY จาก yfinance (7,724 trading days ตั้งแต่ 1996)

**ผลลัพธ์:** `model_c_rulebase/data/fomc_market_context.csv` — 452/452 ข่าวมี rate_surprise +
equity_move + curve_slope_delta + vix_delta ครบ (0 ข่าวถูกข้าม) มีแค่ `dxy_delta` ที่ขาดจริง
111/452 ข่าว (24.6%) เพราะ DTWEXBGS ไม่มีข้อมูลก่อน 2006-01-02 (ข้อจำกัดของแหล่งข้อมูล ไม่ใช่
บั๊ก — เก็บเป็น NaN ไม่เดา ไม่ทิ้งทั้งแถวเพราะ dxy_delta ป้อนแค่ channel C5 เดียวใน R4)

Spot-check เหตุการณ์ที่รู้คำตอบล่วงหน้า (ยืนยันว่า pipeline ไม่ผิด ไม่ใช่แค่รันผ่าน):
- **16 ธ.ค. 2015** (ขึ้นดอกเบี้ยครั้งแรกในรอบ ~9 ปี แต่ telegraphed ไว้ล่วงหน้าแล้วทั้งตลาด):
  rate_surprise=+0.04 (เล็กน้อยตามคาดเพราะตลาดรู้ล่วงหน้า), equity_move=+1.46% (relief rally),
  vix_delta=−3.09 (ความไม่แน่นอนลดหลังรู้ผลชัดเจน)
- **3 มี.ค. 2020** (ลดฉุกเฉิน 50bp นอกรอบประชุมปกติ): rate_surprise=−0.13, equity_move=−2.86%
  (ตลาดตกใจว่า Fed ต้องลดฉุกเฉิน มากกว่าดีใจที่ลด — ตรงกับ "information effect" ที่คาด)
- **15 มี.ค. 2020** (ประกาศวันอาทิตย์ ลดเหลือ 0%): t0 ปรับเป็น 2020-03-16 ถูกต้อง (trading day
  แรกหลังประกาศ), equity_move=−10.9% (Black Monday), vix_delta=+24.86 (พุ่งแรงสุดในชุดข้อมูล)
  ทั้งสามเคสตรงกับข้อเท็จจริงทางประวัติศาสตร์ที่ทราบอยู่แล้ว

**มุมมอง/การตีความ:** pipeline ให้ตัวเลขที่ sensible และตรงกับเหตุการณ์จริงที่รู้คำตอบล่วงหน้า
— พร้อมป้อนเข้า Phase R2 (shock classification) การที่ dxy_delta ขาดหายไปเกือบ 1 ใน 4 ของข่าว
เป็นข้อจำกัดที่ต้องพกไปตลอดจนถึง R5 (channel C5 จะ activate ไม่ได้เลยสำหรับข่าวก่อน 2006 —
ต้องรายงานแยกในผล R5 ว่าช่วงก่อน/หลัง 2006 ต่างกันหรือไม่)

**ขั้นต่อไปที่ควรลอง:** Phase R2 — Jarociński-Karadi 2×2 shock classification จาก
rate_surprise × equity_move แล้ว spot-check ด้วยเคสที่รู้คำตอบอยู่แล้ว (มี.ค. 2020 ควรได้
info_negative, ธ.ค. 2015 ควรได้ info_positive หรือ policy_tightening อ่อนๆ) ตามที่กำหนดไว้ใน
definition of done ของ R2
