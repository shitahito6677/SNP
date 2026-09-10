# Experiment Log

บันทึกทุก experiment ตามกฎใน `CLAUDE.md` (หัวข้อ "กฎการบันทึก Experiment") — append รายการใหม่ต่อท้ายเสมอ ห้ามลบของเก่า

---
## exp_01_baseline_no_text — 2026-09-07 19:16 (+07:00)

**วิธีที่ใช้:** เทรน XGBoost multiclass (pooled, sector เป็น feature เดียวไม่แยกโมเดลต่อ sector)
ทำนาย label 5 ระดับ (-2,-1,0,1,2) โดยไม่ใช้ข้อมูลข่าว/sentiment เลย — เป็น baseline สำหรับเทียบกับ
exp_02 ที่จะเพิ่ม sentiment feature เข้าไป

**ข้อมูลที่ใช้:**
- `data/processed/labels.parquet` (จาก Stage 2, 4,371 แถว) — merge กับ VIX/US10Y (จาก yfinance, `^VIX`/`^TNX`)
- Feature: sector one-hot (11) + VIX + US10Y = 13 feature รวม
- Train/test split ตามคอลัมน์ `split` ในไฟล์ (เรียงเวลา, test = 2 ปีสุดท้าย, ห้ามสุ่ม): train=4,008, test=363

**ผลลัพธ์:**
- Accuracy = 0.2287 (22.87%)
- Macro F1 = 0.2238
- Per-class F1: -2=0.2472, -1=0.1923, 0=0.2361, 1=0.1905, 2=0.2529

**มุมมอง/การตีความ:** สูงกว่า random-guess (20% สำหรับ 5 class) เพียงเล็กน้อย บ่งชี้ว่า sector + VIX + US10Y
ล้วนๆ มีอำนาจพยากรณ์ผลกระทบ 21-วันของข่าวมหภาคต่อ sector ค่อนข้างอ่อน

**ขั้นต่อไปที่ควรลอง:** เทียบกับ exp_02 ที่เพิ่ม FinBERT sentiment feature เข้าไป ดูว่าช่วยเพิ่ม macro F1 ได้ไหม
---

## exp_02_full_pipeline — 2026-09-07 19:16 (+07:00)

**วิธีที่ใช้:** เหมือน exp_01 ทุกประการ (ใช้ `experiments/common.py` ร่วมกัน การันตี model config/split/metric
เหมือนกันเป๊ะ) เพิ่มแค่ feature `sent_XLK...sent_XLC` (11 คอลัมน์ FinBERT sentiment score จาก Stage 4)
เข้าไป — ทดสอบว่า pipeline เต็ม (Qwen → FinBERT → XGBoost) ช่วยอะไรเทียบ baseline หรือไม่

**ข้อมูลที่ใช้:**
- เหมือน exp_01 + `data/processed/sentiment.parquet` (จาก Stage 4, 477 แถว) merge ด้วย `url`
  (broadcast sentiment vector ของข่าวนั้นไปทุก sector-row ของข่าวเดียวกัน)
- Feature รวม 24 ตัว (13 เดิม + 11 sentiment) — train=4,008, test=363 (เท่ากับ exp_01 เป๊ะ ไม่มีแถวหายจาก merge)

**ผลลัพธ์:**
- Accuracy = 0.2176 (21.76%) — **ลดลงจาก exp_01 -4.8%**
- Macro F1 = 0.2114 — **ลดลงจาก exp_01 -5.5%**
- Per-class F1: -2=0.2500, -1=0.1709, 0=0.2073, 1=0.1538, 2=0.2750
- Feature importance top 10: 5 จาก 10 เป็น sentiment feature (นำโดย `sent_XLI` อันดับ 3)

**มุมมอง/การตีความ:** sentiment ไม่ได้ช่วย — ตรงข้าม ทำให้ macro F1 แย่ลง แม้โมเดลจะ "ใช้" sentiment feature
จริงในการแตกกิ่ง (เห็นจาก feature importance) เหตุผลที่ตรวจสอบได้จริงจาก Stage ก่อนหน้า:
(1) สัญญาณพื้นฐานอ่อนอยู่แล้วตั้งแต่ baseline, (2) FinBERT sentiment score ของหลาย sector
โดยเฉพาะ defensive sector (XLP, XLV) มี bias เป็นบวกเป็นระบบไม่ว่า Qwen จะเขียน direction ว่าอะไร
(ตรวจพบใน Stage 4 — XLP/XLV แทบไม่เคยได้ score ติดลบเลยตลอด 477 ข่าว), (3) เพิ่ม feature จาก 13→24
ตัวบน train แค่ 4,008 แถว เพิ่มความเสี่ยง overfit

**ขั้นต่อไปที่ควรลอง:** ปรับปรุงคุณภาพ sentiment signal ก่อน (เช่น ให้ FinBERT อ่านเฉพาะคำ direction
ที่ Qwen ระบุ แทนที่จะอ่านทั้งประโยค หรือปรับ prompt ของ Qwen ให้แยก direction กับเหตุผลชัดเจนกว่านี้)
มากกว่าจะไปปรับที่ XGBoost hyperparameter
---

## sandbox_phase0_data_validation — 2026-09-11 01:53 (+07:00)

**วิธีที่ใช้:** Phase 0 ของ ensemble sandbox (combine Model A+B+C signals) — เขียน
`sandbox/scripts/phase0_validate_universe.py` เพื่อตรวจ universe 5 ตัว (NVDA, META, TSLA, SCHW, FDX)
ก่อนต่อยอดใดๆ: (1) ดึงรายชื่อ S&P500 ปัจจุบันจาก Wikipedia จริงด้วย `pandas.read_html`
(ไม่สมมติว่าอยู่แน่นอน) (2) เช็ค GICS sector ปัจจุบันจากตารางเดียวกัน map ไปยัง sector ETF ที่ Model C
ใช้เทรน (3) ดึง OHLCV รายวัน 5 ปีล่าสุดผ่าน `yfinance` เก็บเป็น CSV ต่อตัว

**ข้อมูลที่ใช้:**
- S&P500 constituent table จาก https://en.wikipedia.org/wiki/List_of_S%26P_500_companies (ดึงสด ณ
  เวลารัน, ทั้งหมด 503 แถว/บริษัท)
- ราคา OHLCV จาก `yfinance` (`period="5y", interval="1d"`) → เขียนลง
  `sandbox/data/prices/{TICKER}.csv` (NVDA, META, TSLA, SCHW, FDX)

**ผลลัพธ์:**
- ทั้ง 5 ตัวอยู่ใน S&P500 ปัจจุบันจริง และ GICS sector ตรงกับที่ brief ระบุครบทุกตัว:
  NVDA=Information Technology(XLK), META=Communication Services(XLC),
  TSLA=Consumer Discretionary(XLY), SCHW=Financials(XLF), FDX=Industrials(XLI)
- ราคาดึงได้ครบทุกตัว ตัวละ 1,255 แถว ช่วงวันที่ 2021-09-10 ถึง 2026-09-10 (ตรงกันทั้ง 5 ตัว)
- รายงานเต็มอยู่ที่ `sandbox/data/validation_report.md`

**มุมมอง/การตีความ:** universe ที่เลือกใน brief ยังใช้ได้จริงตามเงื่อนไขทั้งหมด (membership + sector
mapping) ไม่มีตัวไหนหลุด S&P500 หรือเปลี่ยน sector — ปลอดภัยที่จะเริ่ม Phase 1 ต่อได้โดยไม่ต้องแก้ universe
ระหว่างตรวจ repo พบว่า `src/` ในโปรเจคนี้มีแค่ pipeline ของ Model C (s1-s4) เท่านั้น ยังไม่มีโค้ด Model A
(Piotroski) หรือ Model B (FinBERT company sentiment) จริง — ผู้ใช้ยืนยันว่ายังไม่ได้เขียน ไม่กระทบ Phase 0
แต่กระทบ phase ถัดไปที่ต้อง import inference code ของ A/B

**ขั้นต่อไปที่ควรลอง:** ก่อนเริ่ม Phase 1 (สร้าง ensemble signal) ต้องหาหรือเขียนโค้ด inference ของ
Model A และ Model B ให้พร้อมใช้งานใน `sandbox/` ก่อน เพราะตอนนี้มีแค่ Model C ที่ import ได้จริง
---
