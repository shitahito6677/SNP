
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

---
## exp_03 Phase R2 — Jarociński-Karadi shock classification — 2026-09-13 12:00

**วิธีที่ใช้:** เขียน `model_c_rulebase/scripts/r2_shock_classification.py` — implement 2×2
sign-restriction classification (Jarociński & Karadi 2020) จาก `rate_surprise` (ΔDGS2) ×
`equity_move` (SPY return) ที่มีอยู่แล้วจาก R1 แบ่งเป็น `policy_tightening` (+,−),
`info_positive` (+,+), `policy_easing` (−,+), `info_negative` (−,−) เพิ่มคอลัมน์ `shock_type`
ลงในไฟล์เดิม (`fomc_market_context.csv`) กรณีพิเศษที่ไม่อยู่ในสเปกเดิมแต่เจอจริงจากข้อมูล:
`rate_surprise == 0` เป๊ะ (DGS2 ไม่ขยับเลย) ไม่มีทิศทางให้เข้า quadrant ได้ → ใส่แยกเป็น
`no_rate_surprise` ไม่เดาว่าควรเอนไปทางไหน

**ข้อมูลที่ใช้:** `model_c_rulebase/data/fomc_market_context.csv` จาก Phase R1 (452 ข่าว, ไม่แก้
ค่า rate_surprise/equity_move ใดๆ)

**ผลลัพธ์:** การกระจาย shock_type จาก 452 ข่าว: `info_positive` 111 (24.6%), `policy_easing`
110 (24.3%), `info_negative` 88 (19.5%), `policy_tightening` 85 (18.8%), `no_rate_surprise` 58
(12.8% — ตรวจแล้วกระจุกช่วง ZIRP 2009-2018 ~31/58 ราย เพราะยีลด์ 2 ปีแทบไม่ขยับตอนดอกเบี้ย
นโยบายติดที่ 0 นาน ไม่ใช่บั๊ก)

Spot-check 6 เคสที่รู้คำตอบจากประวัติศาสตร์จริง (ผูกคำตอบตายตัว 4 เคส, เก็บไว้ดูประกอบอีก 2 เคส):
- 2020-03-03 (emergency 50bp cut) -> `info_negative` ✓ ตรงคาด
- 2020-03-15 (ประกาศวันอาทิตย์ ลดเหลือ 0%+QE, ตลาดร่วง Black Monday) -> `info_negative` ✓ ตรงคาด
- 2015-12-16 (ขึ้นดอกเบี้ยครั้งแรก telegraphed, ตลาดรับบวก) -> `info_positive` ✓ ตรงคาด
- 2007-09-18 (cut แรกวิกฤต subprime 50bp เกินคาด, DGS2 ลง+หุ้นขึ้นพร้อมกัน) -> `policy_easing` ✓
  ตรงคาด (เคสที่สะอาดที่สุด ไม่มี cross-current)
- 2008-09-16 (1 วันหลัง Lehman, Fed คงดอกเบี้ย) -> `info_positive` (ไม่ผูกคำตอบ, confound จาก
  วิกฤต Lehman เอง)
- 2001-01-03 (intermeeting cut 50bp, Nasdaq +14%) -> `info_positive` (ไม่ผูกคำตอบ — ดู
  "ข้อผิดพลาดที่แก้ไประหว่างทาง" ด้านล่าง)

ทุกเคสที่ผูกคำตอบไว้ (4/4) ตรงกับที่คาด

**ข้อผิดพลาดที่แก้ไขระหว่างทาง (สำคัญ, ตรงตามหลัก "ห้ามเดา" ของโปรเจคเอง):** ตอนเขียน known-case
แรก ตั้งคาดคำตอบของ 2001-01-03 ไว้ว่าต้องเป็น `policy_easing` จากความจำล้วนๆ ("Nasdaq +14% วันนั้น
= ตลาดได้สิ่งที่ต้องการ") โดยไม่ได้เช็ค DGS2 จริงก่อน — พอรันจริงได้ `info_positive` (ไม่ตรงคาด)
เลยดึงข้อมูล DGS2 ดิบจาก FRED มาดูตรงๆ พบว่า 2yr yield ขยับขึ้นเล็กน้อยวันประกาศเอง (4.87->4.92)
ก่อนจะร่วงต่อเนื่องวันถัดๆ ไป (4.92->4.77->4.56->4.54) — ไม่ใช่บั๊กของโค้ด แต่เป็นข้อจำกัดจริงของ
นิยาม `rate_surprise=ΔDGS2 วันเดียว`: yield 2 ปีฝัง forward-path expectation ไว้ล่วงหน้าแล้ว
intermeeting cut ที่สุดโต่งจึงมี cross-current ทำให้ปฏิกิริยาวันแรกซับซ้อนกว่าสัญชาตญาณง่ายๆ —
แก้โดยเปลี่ยนเคสนี้เป็น "ไม่ผูกคำตอบตายตัว" (เก็บไว้ดูประกอบ) แล้วแทนที่ด้วยเคส 2007-09-18 ที่
สะอาดกว่า (ทั้งบอนด์และหุ้นเคลื่อนไปทางเดียวกันจริง ไม่มี cross-current) เป็น known-case ตัวที่ 4
แทน — บทเรียน: การตั้ง "คำตอบที่รู้อยู่แล้ว" ต้องเช็คจากข้อมูลจริงก่อนตั้งเป็นเกณฑ์ ไม่ใช่ใช้ความจำ
ล้วนๆ แม้จะมั่นใจแค่ไหนก็ตาม (ห้ามเดาแม้แต่ตอนออกแบบ test case เอง ไม่ใช่แค่ตอนรายงานผล)

**มุมมอง/การตีความ:** การกระจาย 4 quadrant ค่อนข้างสมดุล (18.8-24.6% ต่อ quadrant) ไม่มี
quadrant ไหนครอบงำผิดปกติ บ่งชี้ว่า policy shock กับ information shock เกิดขึ้นถี่พอๆ กันในข้อมูล
จริง 27 ปีที่ผ่านมา ซึ่งสมเหตุสมผลตามทฤษฎี Fed information effect (ไม่ควรมี quadrant ไหนหายไป
เกือบหมด) เคส 2001-01-03 ที่ "ผิดจากสัญชาตญาณ" ยืนยันประเด็นทฤษฎีของ Gürkaynak-Sack-Swanson
(2005) ที่บอกว่า target factor กับ path factor อาจสวนทางกันได้จริง ไม่ใช่แค่ทฤษฎีลอยๆ

**ขั้นต่อไปที่ควรลอง:** Phase R3 — เขียน prompt สกัดตัวแปรโครงสร้างจาก Qwen (ห้ามพูดถึง sector
เด็ดขาด), บังคับ evidence quote, self-consistency 2 รอบ รันกับ 452 ข่าว

---
## exp_03 Phase R4 — rule engine (loading matrix × channel activation) — 2026-09-13 12:13

**วิธีที่ใช้:** เขียน `model_c_rulebase/engine/sector_rules.py` — ชั้น 3 ของสถาปัตยกรรม รับ
`shock_type` (จาก R2) + structured variables ที่ LLM สกัดมา (จาก R3, ยังไม่มีให้ใช้จริงตอนเขียน
R4 เพราะรันคู่ขนานกันอยู่ — ทดสอบด้วยข้อมูลสังเคราะห์ที่ตรงสเปกแทน) + market data ดิบ (R1) แล้ว
ตัดสิน `sector_impact_score` ของทั้ง 11 sector ผ่าน loading matrix (7 channels: duration/discount
rate, cyclical growth, NIM, credit risk, dollar, inflation pass-through, leverage/refinancing) x
channel activation ทุกฟังก์ชันคืนคำอธิบายที่มาของคะแนนเป็นข้อความเสมอ (`explain()`) — ตรงตาม
หลักการ "explainability ต้องมาก่อน accuracy" ที่กำหนดไว้

**สิ่งที่ต้องเปิดเผยชัดเจน (ไม่ใช่ implementation detail ธรรมดา):** loading matrix ทั้งหมดคือค่า
จากทฤษฎีตามสเปก (ห้ามถือเป็นค่าจริง ต้อง calibrate ใน R6) — **แต่เพิ่มเติมจากนั้น** ค่าคงที่
ตัวคูณ/amplifier ในฟังก์ชัน `compute_channel_activations()` (C1 dampener 0.5 สำหรับ info_positive,
C2 amplifier 1.5 สำหรับ info_positive/negative, C7 balance-sheet weight 0.3, VIX amplifier 1.4
[ค่ากลางของช่วง 1.3-1.5 ที่สเปกให้]) เป็นการตีความเชิงตัวเลขของคำอธิบายเชิงคุณภาพในสเปก (ลูกศร
ขึ้น/ลง + คำอธิบายวงเล็บ เช่น "C1↓ อ่อน") เพราะสเปกไม่ได้ให้สูตรตัวเลขตรงๆ ไว้ — ต้อง calibrate
ใน R6 เหมือน loading matrix เช่นกัน ไม่ใช่ค่าที่พิสูจน์แล้ว ระบุไว้ชัดใน module docstring กัน
เข้าใจผิดว่าเป็นค่าทฤษฎีล้วนๆ

**การตัดสินใจเติมช่องว่างที่สเปกไม่ได้ระบุไว้ตรงๆ (ต้องบันทึกไว้ตรวจสอบย้อนได้):**
- C3 (NIM) และ C7 (leverage) ใช้ activation เดียวกันทุก shock_type (ไม่ผูกกับ quadrant) เพราะเป็น
  กลไกโครงสร้าง (ความชันของ curve, ต้นทุนรีไฟแนนซ์ตามระดับดอกเบี้ยจริง) ไม่ใช่ narrative-dependent
- C4 (credit risk) activate เฉพาะ policy_tightening (ผูกกับ uncertainty/financial_stability
  language) และ info_positive/info_negative (ผูกกับ growth_delta ตรงข้าม) — **policy_easing ไม่
  activate เลย (0)** เพราะสเปกไม่ได้ระบุกลไกไว้สำหรับ quadrant นี้ ไม่เดาเพิ่มเติมเอง
- C5 (dollar) เมื่อ dxy_delta หายไป (ข่าวก่อน 2006, พบจริง 111/452 จาก R1) -> activation = 0
  พร้อม flag ในคำอธิบายว่า "ไม่มีข้อมูล" ไม่ใช่การเดาว่าควรเป็นเท่าไหร่
- XLF C7 ระบุ "n/a" ในสเปกต้นฉบับ -> ใช้ loading=0 ในการคำนวณจริง แต่ flag แยกต่างหากว่าเป็น
  "n/a เชิงทฤษฎี" ไม่ใช่ "0 เชิงทฤษฎี" (สองอย่างมีความหมายต่างกัน)

**ข้อมูลที่ใช้:** ไม่มีข้อมูลจริงจาก R3 ตอนเขียน (รันคู่ขนานกันอยู่เบื้องหลัง) — unit test ใช้ข้อมูล
สังเคราะห์ที่ตรงตามช่วงค่าจริงของ schema (rate_surprise, vix_delta ฯลฯ) แทน จะ integration-test
กับข้อมูลจริงทั้งหมดใน Phase R5

**ผลลัพธ์:** `model_c_rulebase/engine/test_sector_rules.py` — 214 assertion ผ่านทั้งหมด (0 fail)
ครอบคลุมตามที่กำหนดใน Definition of Done:
- ทุก 5 shock_type (4 ตามสเปก + `no_rate_surprise` จาก R2) ให้คะแนนครบ 11 sector และอธิบายได้
- Edge case 1 (XLF pivot): ทดสอบทั้ง trigger จาก financial_stability_concern>=1, จาก
  curve_slope_delta<0 อย่างเดียว, และกรณีไม่ trigger เลย — loading เปลี่ยนถูกต้องทุกกรณี
- Edge case 2 (VIX amplifier): ยืนยันคะแนนสเกล x1.4 พอดีเมื่อ vix_delta เกิน p90 (1.128 จาก
  ข้อมูลจริง R1) ทุก sector ที่ score != 0
- Edge case 3 (low_confidence dampener): ยืนยันคะแนนสเกล x0.5 พอดี และรวมกับ VIX amplifier
  แบบคูณ (x0.7) ได้ถูกต้องเมื่อ active พร้อมกัน
- spot-check loading matrix ตรงกับตารางในสเปกต้นฉบับ (กัน typo ตอน implement)

**มุมมอง/การตีความ:** engine ทำงานตามที่ออกแบบไว้ทุกจุดที่ทดสอบได้ — จุดที่ต้องระวังที่สุดตอนนี้
ไม่ใช่ความถูกต้องของโค้ด (ทดสอบแล้ว) แต่คือ**ค่าคงที่ตัวคูณที่ตีความเอง**ยังไม่มีข้อมูลจริงมายืนยัน
เลยว่าเหมาะสม — R5 จะเป็นตัวบอกว่าค่าเหล่านี้ (รวมถึง loading matrix) ให้สัญญาณตรงกับ CAR จริงหรือไม่
ถ้าไม่ตรง R6 จะต้อง calibrate ทั้งสองชุดพร้อมกัน ไม่ใช่แค่ loading matrix อย่างเดียว

**ขั้นต่อไปที่ควรลอง:** รอ Phase R3 (LLM extraction) รันจบ (กำลังรันอยู่เบื้องหลัง, checkpoint/
resume ได้) แล้วนำ shock_type (R2) + structured vars จริง (R3) + market data จริง (R1) มาป้อนเข้า
engine นี้จริงทั้ง 452 ข่าว จากนั้นเข้า Phase R5 (validation กับ CAR จริง ตามเกณฑ์ที่กำหนดไว้ล่วงหน้า)
