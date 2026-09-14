
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

---
## exp_03 Phase R3 — LLM structured-variable extraction (Qwen) — 2026-09-14 03:07

**วิธีที่ใช้:** เขียน `model_c_rulebase/scripts/r3_llm_extraction.py` — ยิง Qwen (`qwen-plus`)
อ่านคู่เอกสาร (CURRENT vs PREVIOUS release ของ source เดียวกัน — FOMC เทียบ FOMC, Beige Book
เทียบ Beige Book เท่านั้น) แล้วกรอกฟอร์มตัวแปรโครงสร้าง 8 ตัว (`stance_delta`, `growth_delta`,
`inflation_delta`, `labor_delta`, `forward_guidance_delta`, `balance_sheet_signal`,
`uncertainty_language`, `financial_stability_concern`) **ห้ามพูดถึง sector เด็ดขาดในprompt**
บังคับ evidence quote สำหรับทุก field ที่ค่า != 0 (reject+retry ถ้าไม่มี ห้าม fallback เงียบๆ)
self-consistency ยิงซ้ำ 2 ครั้ง (temperature=0.7) ค่าสุดท้าย = round(mean ของ 2 รอบ), flag
`low_confidence=True` ถ้า field ใดต่างกันเกิน 1 ระดับ checkpoint แบบ append-JSONL + resume ได้
ปลอดภัย (ตามแนวทางเดียวกับ `src/s3_sector_views.py` เดิม)

**บั๊กที่เจอและแก้ระหว่าง dev (ก่อนรันจริง):** โมเดลตอบเลขบวกแบบ `+1` (เช่น `"growth_delta": +1`)
ซึ่งไม่ใช่ JSON number literal ที่ถูกต้อง (JSON ไม่รับ leading `+`) ทำให้ parse fail 100% ของข่าว
ที่มี field บวก — แก้ด้วย regex sanitize `+` หน้าตัวเลขหลัง `:` ก่อน parse (defense in depth ที่
2: เพิ่ม instruction ห้ามใช้ `+` prefix ใน prompt ด้วย)

**เหตุการณ์สำคัญระหว่างรันจริง — Qwen API key/account หมดปัญหาซ้ำหลายรอบ (ไม่ใช่บั๊กโค้ด):**
รันจริงต้องหยุด-resume หลายครั้งเพราะปัญหาบัญชี Qwen ไม่ใช่ปัญหา pipeline:
  1. Account เดิม (key 1): หยุดที่ 208/450 ด้วย `403 AllocationQuota.FreeTierOnly` (free quota
     ของ `qwen-plus` หมด)
  2. เปลี่ยน key ไป account ใหม่ (key 2): test call ผ่าน (HTTP 200) รันต่อได้จริงถึง 393/450
     ก่อนเจอ `403 AllocationQuota.FreeTierOnly` อีกครั้ง (free quota ของ account นี้เล็กกว่าที่คิด)
  3. เปลี่ยน key ไป account ใหม่อีก (key 3): เจอ `403 AccessDenied.Unpurchased` ซ้ำ 5 ครั้งติด
     ทั้งกับ `qwen-plus` และ `qwen-turbo` (ทดสอบแล้วว่าไม่ใช่ปัญหาเฉพาะโมเดล — ทั้งบัญชีไม่มี
     model access ที่ purchase ไว้เลย) — ตัดสินใจเลิกใช้ account นี้
  4. สลับ `.env` กลับไปใช้ key 1 เดิม — test ครั้งแรกยังเจอ `403 AccessDenied.Unpurchased`
     (ผิดคาด เพราะ error type ต่างจากตอน key 1 หยุดครั้งแรก ซึ่งเป็น quota หมดไม่ใช่ unpurchased)
     แต่ test ซ้ำอีกครั้งผ่าน (HTTP 200) — สรุปว่าเป็น propagation delay ของฝั่ง Qwen ไม่ใช่ปัญหา
     ถาวร จึงรันต่อด้วย **`qwen-plus` เดิมทั้งหมด** (ไม่ได้สลับไป `qwen-turbo` ตามแผนสำรองที่
     คุยไว้ระหว่างทาง เพราะ account 1 กลับมาใช้งานได้ก่อนจะต้องพึ่งแผนสำรอง) รันจบจนครบ 450/450
     ที่พยายาม (436 สำเร็จ) แบบไม่สะดุดอีกเลย
ทุกจุดตรวจสอบด้วยการ test call จริงก่อนแตะ checkpoint เสมอ (ไม่เดาว่า key ใช้ได้), เช็ค `.env`
mtime + ความยาว key (ไม่ print ค่าจริง) ยืนยันทุกครั้งว่าเป็น key ใหม่จริงก่อนสรุปผล — พบและแก้
ความสับสนจริง 1 ครั้ง (mtime ไม่เปลี่ยนหลังผู้ใช้บอกว่าเปลี่ยน key แล้ว แปลว่ายังไม่ได้ save จริง)

**ข้อมูลที่ใช้:** `data/raw/macro_news_raw.parquet` (ข้อความข่าวดิบ 452 ข่าว, ไม่แก้) จับคู่กับ
release ก่อนหน้าของ source เดียวกัน (450 ข่าวมี baseline เทียบได้, 2 ข่าวแรกสุดของแต่ละ source
ไม่มี — ข้าม ไม่เดา)

**ผลลัพธ์:** `model_c_rulebase/data/fomc_structured_vars.csv` — **436/450 ข่าวสำเร็จ (96.9%)**
(FOMC_statement 220, Beige_Book 216), **14 ข่าวล้มเหลว (3.1%)** — token รวมทั้งหมดที่ใช้จริงตลอด
การรัน (รวมทุก resume/key): ~2,111,000 tokens (452 ข่าว x 2 self-consistency runs)

**พบสิ่งสำคัญจาก 14 ข่าวที่ล้มเหลว (ไม่ใช่ random noise):** **ทั้ง 14 ข่าวล้มเหลวด้วยรูปแบบเดียวกัน
เป๊ะ** — โมเดลตอบ `uncertainty_language=-1` หรือ `financial_stability_concern=-1` ซึ่งอยู่นอกช่วง
ที่กำหนด (0..2, ตั้งใจให้เป็น unidirectional "มากขึ้นแค่ไหน") ทุกครั้ง ไม่ใช่ field อื่นเลย — แสดงว่า
โมเดลบางครั้ง "อยากบอก" ว่าความไม่แน่นอน/ความเสี่ยงเสถียรภาพการเงิน**ลดลง**เทียบครั้งก่อน (เป็น
สัญชาตญาณทางภาษาที่สมเหตุสมผล) แต่ schema ที่กำหนดไม่มีทางให้แสดงทิศทางลดได้เลย (ตั้งใจให้เป็น
unidirectional ตามสเปกต้นฉบับ) validation ปฏิเสธค่านี้ถูกต้องตามที่ออกแบบไว้ (ห้าม fallback เป็น 0
เงียบๆ) แต่ผลคือข่าวเหล่านั้นถูกข้ามไปแทนที่จะได้ค่า 0 ที่อาจจะถูกต้องกว่า

**low_confidence:** 6/436 (1.4%) — ต่ำมาก แสดงว่า self-consistency ระหว่าง 2 รอบเห็นตรงกันเกือบ
ทั้งหมด (ไม่ได้แปลว่าค่าถูกต้อง แค่แปลว่าโมเดลตอบสม่ำเสมอ)

**มุมมอง/การตีความ:** อัตราสำเร็จ 96.9% สูงพอจะใช้งานต่อได้จริง 14 ข่าวที่ขาดหายเป็น pattern
เดียวกันชัดเจน (ไม่กระจายสุ่ม) จึงไม่น่าจะทำให้เกิด bias เป็นระบบใน R4/R5 (เป็นข่าวที่กระจายทั้ง
ช่วงเวลา 1999-2025 ไม่กระจุกช่วงไหนช่วงหนึ่ง) แต่ถ้าจะปรับปรุงในอนาคต ควรพิจารณาขยาย range ของ
`uncertainty_language`/`financial_stability_concern` เป็น -2..2 (unidirectional -> bidirectional)
หรือเพิ่ม post-processing step แปลง -1 เป็น 0 แทนที่จะ reject ทั้ง response — ไม่ทำตอนนี้เพราะจะ
เปลี่ยน schema กลางทางหลังเห็นผลแล้ว (ขัดกับหลัก "ห้ามเปลี่ยนเกณฑ์หลังเห็นตัวเลข") บันทึกไว้เป็น
ข้อเสนอสำหรับรอบถัดไปแทน

**ขั้นต่อไปที่ควรลอง:** Phase R5 — รัน rule engine (R4) จริงบน 436 ข่าวที่มี structured vars
ครบ x shock_type (R2) x market data (R1) แล้ว validate กับ CAR จริง (R5a) ตาม protocol ที่กำหนด
ไว้ล่วงหน้า

---
## exp_03 Phase R5 — validation กับ CAR จริง (สำคัญที่สุด) — 2026-09-14 03:09

**วิธีที่ใช้:** ใช้ protocol ที่กำหนดไว้ล่วงหน้าทั้งหมด (metric, threshold, train/test split,
clustering) จากเอกสารสเปก **ไม่เปลี่ยนเกณฑ์ใดๆ หลังเห็นตัวเลข**:
1. `model_c_rulebase/scripts/r5a_car_windows.py` — เพิ่ม CAR N=1, N=3 วันทำการ ควบคู่กับ N=21
   เดิมจาก exp_01/exp_02 (`data/processed/labels.parquet`) สูตรเดียวกันเป๊ะ, t0/calendar เดียวกับ
   `src/s2_build_labels.py` — sanity check: recompute N=21 ตรงกับ 'score' เดิมเป๊ะ (max diff =
   0.0000000000 จาก 4,371 แถว) ยืนยันว่า methodology ตรงกันจริง ไม่ใช่แค่คิดว่าตรง
2. `model_c_rulebase/scripts/r5b_validate.py` — รัน rule engine (R4) จริงบน 436 ข่าวที่มี
   structured vars ครบ (R3) x shock_type (R2) x market data (R1) ได้ 4,796 แถว (436 ข่าว x 11
   sector) join กับ CAR (R5a) แล้ว **train/test split ใหม่ตามเวลา 80/20 บนหน่วย "ข่าว" (ไม่ใช่
   split เดิมของ exp_01/exp_02)**: train 348 ข่าว (2026-... ถึง cutoff 2020-12-02), test 87 ข่าว
   — **รายงานเฉพาะ train ในเฟสนี้ ไม่แตะตัวเลข test เลยแม้แต่ตัวเดียว** ตามที่กำหนด (สงวนไว้
   สำหรับตรวจครั้งสุดท้ายหลัง R6 calibration เสร็จ ถ้าจะทำ)
   Significance testing: cluster bootstrap (resample ที่ระดับ "วันข่าว" ไม่ใช่ระดับแถว, n_boot
   = 1,000) หา 95% CI ของ Spearman rho เคารพว่า 11 sector ของข่าวเดียวกันไม่อิสระจากกัน (ข้อ 4
   ของ protocol)

**ข้อมูลที่ใช้:** train set = 348 ข่าว x 11 sector = 3,256 แถว join สำเร็จ (583 แถวหาย จาก join —
ตรวจแล้วเป็น XLRE/XLC ที่ยังไม่มีราคา ETF ก่อนวันเปิดตัวจริง [XLRE เปิด 2015-10-08, XLC เปิด
2018-06-19] คำนวณ expected-missing ตรงกันพอดี ไม่ใช่บั๊ก join)

**ผลลัพธ์ (TRAIN ONLY, ตัวเลขจริงจากการรัน):**

POOLED rho (ทุก sector, ทุก shock_type รวมกัน):
| N | rho | 95% CI |
|---|---|---|
| 1  | +0.0081 | [-0.027, +0.047] |
| 3  | -0.0079 | [-0.044, +0.030] |
| 21 | -0.0153 | [-0.053, +0.022] |

ทั้ง 3 หน้าต่างมี rho ใกล้ 0 มาก และ 95% CI คร่อม 0 เสมอ (ไม่มีนัยสำคัญทางสถิติแม้แต่ระดับ pooled)

By-sector และ by-shock_type (33+15 cell): **มีแค่ 1 cell เดียวที่ CI ไม่คร่อม 0** — XLV ที่ N=1
(rho=-0.1222, CI=[-0.225,-0.015]) และ XLV ที่ N=21 (rho=-0.1184, CI=[-0.215,-0.018]) แต่ทั้งคู่
**|rho| < 0.3 (เกณฑ์ที่ตั้งไว้)** — สรุปว่า statistically significant (ไม่ใช่บังเอิญ) แต่ไม่ผ่าน
threshold ขนาดผลที่ตั้งไว้ล่วงหน้า

**0 จาก 216 cells (pooled + by_sector + by_shock_type + sector_x_shock เต็ม) ผ่านเกณฑ์ทั้งสองข้อ
พร้อมกัน (|rho|>0.3 AND CI ไม่คร่อม 0)**

**PASS/FAIL: ไม่ผ่าน — NEGATIVE RESULT**

**มุมมอง/การตีความ:** engine เวอร์ชันทฤษฎีล้วน (loading matrix + amplifier constants ที่ยังไม่ผ่าน
calibration ใดๆ) **ไม่แสดงสัญญาณที่ทั้งมีนัยสำคัญทางสถิติและมีขนาดผลใหญ่พอ**จะผ่านเกณฑ์ที่ตั้งไว้
ล่วงหน้าเลย สอดคล้องไปในทิศทางเดียวกับ baseline เดิม (exp_01/exp_02 ที่ accuracy ใกล้ random,
exp_02 แย่กว่า exp_01 ด้วยซ้ำ) — กล่าวคือ **สัญญาณ predictive ของ FOMC/Beige Book text ต่อ
sector-level CAR ยังคงอ่อนมากไม่ว่าจะแปลงข้อความเป็นตัวแปรด้วยวิธีไหน** (LLM sentiment ตรงๆ แบบ
exp_02, หรือ LLM สกัดตัวแปรโครงสร้าง + rule engine ทฤษฎีแบบรอบนี้)

จุดที่น่าสนใจที่สุดคือ **XLV (Health Care)** เป็น sector เดียวที่ให้ค่า CI ไม่คร่อม 0 ทั้งที่ N=1
และ N=21 (สัญญาณสม่ำเสมอข้ามหน้าต่างเวลา ไม่ใช่ noise สุ่ม) แต่ทิศทางน่าแปลกใจ: rho ติดลบ
(sector_impact_score สูง = CAR ต่ำ) ซึ่ง**ตรงข้าม**กับที่ theory คาด (XLV เป็น defensive sector,
engine ให้ loading ต่ำแทบทุก channel ตามทฤษฎี "defensive ไม่ค่อย react") — อาจบ่งชี้ว่า loading
matrix ของ XLV ที่ตั้งไว้ (เกือบเป็นศูนย์ทุกช่อง) ผิดทิศทาง ไม่ใช่แค่ผิดขนาด ถ้าจะ calibrate ใน R6
ควรเริ่มดู XLV เป็นจุดแรก

**ขั้นต่อไปที่ควรลอง (ตามที่สเปกกำหนดไว้สำหรับกรณี R5 ไม่ผ่าน):** บันทึกเป็น negative result ที่มี
ค่า (พิสูจน์ว่า FOMC/Beige Book text ให้สัญญาณ sector-level ที่จำกัดจริงด้วยวิธีการที่ทดสอบมาแล้ว
2 แบบ) — Phase R6 **ไม่ทำ full calibration** ตามเงื่อนไขที่กำหนด ("ถ้า R5 แสดงว่าไม่มีสัญญาณเลย ->
บันทึกไว้ว่าเป็น negative result แล้วย้ายน้ำหนักไปยัง component อื่นแทน") แต่ควรพิจารณา 2 อย่างก่อน
ปิด component นี้เต็มที่: (1) ตรวจทิศทางผิดปกติของ XLV ให้ชัดว่าเป็น data artifact หรือสัญญาณจริง
กลับทิศ (2) พิจารณาว่า amplifier constants ที่ตีความเองใน R4 (ไม่ใช่ loading matrix จากทฤษฎี)
อาจเป็นสาเหตุที่ signal จางไป ควรลอง sensitivity analysis ง่ายๆ (ปรับ constants เหล่านั้นแล้วดูว่า
rho เปลี่ยนไปมากน้อยแค่ไหน) ก่อนสรุปว่าไม่มีสัญญาณจริง — แต่ทั้งหมดนี้เป็น **exploratory เท่านั้น
ไม่ใช่ full R6 calibration** (จะไม่ fit บน train เพื่อ "หาค่าที่ดีที่สุด" เพราะจะขัดกับเกณฑ์ที่ตั้ง
ไว้ล่วงหน้าว่า "ห้ามสรุปว่าดีขึ้นถ้าตัวเลขไม่ผ่านเกณฑ์ที่กำหนดไว้ก่อนแล้ว")

Test set (87 ข่าว, 957 แถว) **ยังไม่ถูกแตะเลยตลอด phase นี้** ตามที่กำหนด

---
## exp_03 Phase R6 — Calibration decision (negative result branch) — 2026-09-14 03:11

**วิธีที่ใช้:** ตาม decision rule ที่กำหนดไว้ล่วงหน้าสำหรับกรณี R5 ไม่ผ่านเกณฑ์ ("ถ้า R5 แสดงว่า
ไม่มีสัญญาณเลย → บันทึกไว้ว่าเป็น negative result ที่มีค่า ... แล้วย้ายน้ำหนักไป component อื่น
แทน") — Phase R6 นี้**ไม่ทำ full calibration** (ไม่ fit loading matrix หรือ amplifier constants
ด้วย regression บน train set) เพราะ R5 แสดงชัดว่าไม่มี cell ไหนผ่านเกณฑ์ที่ตั้งไว้ล่วงหน้าเลย
(0/216 cells) การไป fit ต่อตอนนี้จะเป็นการ "หาค่าที่ทำให้ตัวเลขดีขึ้น" หลังเห็นผลแล้ว ซึ่งขัดกับ
กฎที่กำหนดไว้เองว่า "ห้ามสรุปว่าดีขึ้นถ้าตัวเลขไม่ผ่านเกณฑ์ที่กำหนดไว้ก่อนแล้ว"

**สิ่งที่ตั้งใจ "ไม่ทำ" ในเฟสนี้ (ระบุไว้ชัดเจน กันเข้าใจผิดว่าลืม):**
- ไม่ fit loading matrix ใหม่จาก train data
- ไม่ปรับ amplifier constants (C1 dampener, C2 amplifier, C7 weight, VIX amplifier) ตามตัวเลขที่
  เห็นจาก R5 — แม้จะรู้ว่าค่าเหล่านี้เป็นการตีความเอง (ไม่ใช่ทฤษฎีล้วน ตามที่ระบุใน R4) ก็ตาม
  เพราะการปรับหลังเห็นผลถือเป็นการ peek แล้วเปลี่ยนเกณฑ์ ขัดกับ pre-registration
- ไม่แตะ test set (87 ข่าว, 957 แถว) เลย — ยังคงสภาพเดิมที่ไม่เคยถูกใช้คำนวณอะไรทั้งสิ้น

**ผลลัพธ์:** ตัดสินใจ (formal decision, ไม่ใช่แค่สังเกต):
1. **Component "FOMC/macro" ของ Model C ตัวนี้ (rule-based, ทฤษฎีล้วน) ให้สัญญาณต่อ CAR
   sector-level จำกัดเกินกว่าจะใช้เป็น component หลักในทันที** — ยืนยันด้วยผลจริง 2 วิธีที่ต่างกัน
   (exp_02: Qwen sentiment ตรงๆ → XGBoost, ทำให้แย่กว่า baseline; exp_03: LLM สกัดตัวแปรโครงสร้าง
   → rule engine ทฤษฎี, ไม่มี cell ไหนผ่านเกณฑ์ที่ตั้งไว้ล่วงหน้าเลย)
2. **ย้ายน้ำหนักเริ่มต้นในระบบ ensemble ไปทาง component sector-news (Model C ตัวที่ 2, sandbox
   `feature/ensemble-sandbox`) และ Model A/B แทน** จนกว่าจะมีข้อมูล/หลักฐานใหม่มายืนยันว่า
   FOMC/macro component ใช้งานได้จริง — ไม่ใช่การตัดทิ้งถาวร (มีค่าไว้ใช้เป็น weak/auxiliary
   signal หรือ risk-flag เสริมได้ ไม่ใช่ signal หลักที่ตัดสินทิศทาง)
3. **สิ่งที่ทำไว้ตลอด R1-R5 ยังมีค่าเก็บไว้ใช้ต่อได้** แม้ engine เวอร์ชันนี้จะยังไม่ผ่านเกณฑ์:
   - `model_c_rulebase/scripts/r1_market_data.py`, `r2_shock_classification.py` — reusable
     สำหรับ component อื่นที่ต้องการ market-based shock classification (ไม่ผูกกับ rule engine
     เวอร์ชันนี้โดยเฉพาะ)
   - `model_c_rulebase/data/fomc_structured_vars.csv` — LLM structured extraction ที่ validate
     คุณภาพแล้วบางส่วน (spot-check R3, low_confidence 1.4%) เป็น input ที่ reusable ถ้าจะลอง
     rule engine เวอร์ชันใหม่ในอนาคตโดยไม่ต้องรัน Qwen ซ้ำ
   - `model_c_rulebase/engine/sector_rules.py` + unit tests — โครงสร้าง engine (loading matrix
     x channel activation x edge case) พร้อม explainability สมบูรณ์ ถ้าจะ calibrate ในอนาคต
     (เช่น มีข้อมูลมากขึ้น, หรือมี hypothesis ใหม่ที่ควร pre-register ก่อนทดสอบ) ใช้โครงเดิมได้
     ไม่ต้องเขียนใหม่ตั้งแต่ต้น

**มุมมอง/การตีความ:** การได้ negative result ที่ตรวจสอบอย่างละเอียด (ไม่ใช่แค่ "ลองแล้วไม่เวิร์ค")
มีค่าจริงต่อโปรเจค — ตัดความเป็นไปได้ที่จะเสียเวลา build เต็มระบบ (Model C แบบ FOMC-only) ที่ไม่มี
สัญญาณพอ แล้วหันไปทุ่มทรัพยากรกับ sector-news component และ Model A/B ที่ยังไม่ได้ทดสอบอย่าง
เข้มงวดขนาดนี้แทน ข้อสังเกตเรื่อง XLV (ทิศทางผิดปกติ, ดูรายละเอียดใน R5) ควรเก็บไว้เป็น hypothesis
สำหรับรอบทดลองถัดไปที่จะ pre-register ใหม่ ไม่ใช่ไปตรวจเพิ่มตอนนี้ (จะกลายเป็น peek)

**ขั้นต่อไปที่ควรลอง:** เปิด PR `feature/model-c-rulebase` -> `main` (`exp_03: rule-based sector
impact engine`) อ้างอิงผลสรุปจากทั้ง 6 phase ใน log นี้ — งานถัดไปที่ควรทำนอก branch นี้คือกลับไป
ทุ่มเวลาที่ `feature/ensemble-sandbox` (sector-news component) และพิจารณา weighted ensemble ที่ให้
น้ำหนัก FOMC/macro component ต่ำ/เป็น auxiliary signal เท่านั้น

---
## exp_04 Phase E1 — non-overlapping price paths — 2026-09-14 07:11

**วิธีที่ใช้:** เริ่ม `exp_04` (branch `feature/model-c-event-clustering`, แยกจาก
`feature/model-c-rulebase` ซึ่ง PR #1 ยังไม่ merge เข้า main ณ ตอนแยก branch — ใช้ branch ต้นทาง
โดยตรงแทนเพราะไฟล์ที่ต้องใช้อยู่ที่นั่น) เป้าหมาย: triangulate ผลลบของ `exp_03`/R5 ด้วยวิธีต่างไป
(ดู "รูปร่าง" ของเส้นราคาทั้งเส้นแทนที่จะดู CAR endpoint เดียว) เขียน
`model_c_event_clustering/scripts/e1_price_paths.py` คำนวณ `window_days` ต่อข่าวอัตโนมัติ
(`min(10, gap_to_next//2, gap_to_prev//2)` คำนวณจากลำดับข่าว**รวมทุก source** เพราะ Beige Book/
FOMC ออกสลับกันถี่) กันหน้าต่างราคาทับกันระหว่างข่าวที่ออกใกล้กัน ข่าวที่ `window_days < 5` ตัด
ออกทั้งข่าว (ไม่ยัดเข้าไป)

**นิยามที่ตัดสินใจเอง (ไม่ได้ระบุไว้ตายตัวในสเปก ต้องบันทึกไว้):** `cum_ar` (cumulative abnormal
return) นิยามให้ต่อเนื่องผ่าน 0 ที่ `t0` พอดี — ก่อน `t0` สะสม "ถอยหลัง" จาก `t0` (ติดลบตาม
นิยาม), หลัง `t0` สะสมไปข้างหน้าแบบ CAR เดิมทุกประการ — validate ด้วยมือ 1 ตัวอย่าง
(1999-12-08, XLF) คำนวณ cumsum ตามสูตรเทียบกับที่โค้ดให้มา **ตรงกันทุกตำแหน่ง**

**ข้อมูลที่ใช้:** `data/processed/labels.parquet` (452 ข่าว, ไม่แก้), `data/raw/
sector_prices_raw.parquet` (price cache เดิมจาก exp_01/02, 7,720 trading days)

**ผลลัพธ์:** `model_c_event_clustering/data/price_paths.csv` — **424/452 ข่าวผ่าน** (93.8%),
**28 ข่าวถูกตัดออก (6.2%)** เพราะ `window_days < 5`: จำแนกตาม window_days ที่คำนวณได้ —
window_days=3 (13 ข่าว), =0 (6 ข่าว, ส่วนใหญ่คือคู่ 2014-09-17 ที่มี 2 press release วันเดียวกัน),
=1 (4 ข่าว), =4 (3 ข่าว รวมถึง **2020-03-15 emergency COVID cut** — ตัดออกเพราะอยู่ใกล้ 2020-03-03
เกินไป), =2 (2 ข่าว) — 42,252 แถว (ข่าว x sector x offset วัน) ทั้งหมด, `window_days` จริง:
min=0, median=7, max=10

**มุมมอง/การตีความ:** อัตราคงเหลือ 93.8% สูงพอใช้งานต่อได้จริง ที่น่าสนใจคือ 2020-03-15 (ตัวอย่าง
สำคัญที่ใช้ใน R2/R3 ของ exp_03) ถูกตัดออกจาก exp_04 เพราะ window ทับกับ 2020-03-03 — เป็นข้อจำกัด
จริงของวิธี non-overlapping window (ช่วงวิกฤตที่ Fed ประชุมถี่ผิดปกติ จะเสีย sample พอดีตอนที่
น่าจะมีสัญญาณแรงที่สุด) ต้องระบุไว้เป็น limitation ของ exp_04 เทียบกับ exp_03 ที่ไม่มีปัญหานี้
(ใช้ fixed ±30 วันได้เพราะไม่สนใจเรื่อง window ทับกัน)

**ขั้นต่อไปที่ควรลอง:** Phase E2 — สกัด feature (cum_return_pre, cum_return_post_short/full,
peak_day, reversion_ratio) จาก price path นี้ต่อ (ข่าว x sector), สุ่มตรวจ 5 แถวด้วยมือเทียบกราฟจริง

---
## exp_04 Phase E2 — feature extraction จาก price path — 2026-09-14 07:13

**วิธีที่ใช้:** เขียน `model_c_event_clustering/scripts/e2_features.py` สรุป price path ราย
วัน (E1) เป็น 5 feature ต่อ (ข่าว x sector): `cum_return_pre` (= cum_ar ที่ offset −1),
`cum_return_post_short` (= cum_ar ที่ offset +3), `cum_return_post_full` (= cum_ar ที่ offset
สุดท้ายฝั่ง post), `peak_offset`/`peak_value` (จุดสุดขั้วฝั่ง post ในทิศทางเดียวกับการเคลื่อนไหว
สุทธิ), `reversion_ratio` (= cum_return_post_full ÷ peak_value, เป็น `NaN` ถ้า peak ≈ 0 กัน
หารเลขใกล้ 0 จนได้ค่าพิสดาร)

**ข้อมูลที่ใช้:** `model_c_event_clustering/data/price_paths.csv` (E1, 42,252 แถว, 424 ข่าว)

**ผลลัพธ์:** `model_c_event_clustering/data/event_features.csv` — 4,113 แถว (424 ข่าว x
sector, เฉลี่ย ~9.7 sector/ข่าวเพราะ XLC/XLRE ขาดในข่าวก่อนเปิดตัว ETF) **0 แถวเป็น NaN ทั้ง
`cum_return_post_short` และ `reversion_ratio`** (ทุก window ที่ผ่าน E1 กว้างพอมี offset+3 จริง
และไม่มี peak ที่ ≈ 0 เป๊ะเลยสักแถว) `reversion_ratio` เฉลี่ย = 0.787 (std=0.289) — บ่งชี้ว่าโดย
เฉลี่ยราคาหลังข่าวมักมี partial reversion เล็กน้อยจาก peak ไม่ใช่ full momentum ต่อเนื่องหรือ
full reversal เต็มที่

**สุ่มตรวจ 5 แถวด้วยมือ (เทียบ feature ที่คำนวณได้กับ cum_ar series ทั้งเส้นตรงๆ ไม่ใช่แค่เชื่อ
สูตร):**
- 2000-03-21 (XLP): ราคาไหลลงต่อเนื่องตลอด post window (offset 1→4: −0.014→−0.066) peak ตรงที่
  offset สุดท้ายพอดี, reversion_ratio=1.000 (ไม่มีการสะท้อนกลับเลย ถูกต้องตามรูปเส้น)
- 2000-05-16 (XLK): จุดต่ำสุดที่ offset 3 (−0.040) แล้วฟื้นเล็กน้อยที่ offset 4 (−0.037) →
  reversion_ratio=0.925 ตรงกับที่เห็นในเส้นจริง
- 2002-10-23 (XLP): จุดต่ำสุดที่ offset 3 (−0.024) แล้ว**สะท้อนกลับแรงมาก**เหลือ −0.003 ที่
  offset 5 → reversion_ratio=0.145 (ตัวอย่างที่ metric นี้จับพฤติกรรม mean-reversion ได้ชัดเจน)
- 2015-09-17 (XLK): ราคาขึ้นต่อเนื่องตลอด → reversion_ratio=1.000 ถูกต้อง
- 2017-02-01 (XLB): จุดต่ำสุดที่ offset 4 (−0.019) ฟื้นเล็กน้อยที่ offset 5 (−0.018) →
  reversion_ratio=0.947 ตรงกับเส้นจริง
ทุกตัวอย่างตัวเลขที่คำนวณได้ตรงกับรูปเส้น cum_ar จริงเป๊ะ ไม่มีความคลาดเคลื่อน

**มุมมอง/การตีความ:** feature ทั้ง 5 ตัวจับพฤติกรรมได้ตามที่ตั้งใจ (ทิศทาง, ขนาด, และการสะท้อน
กลับของราคา) — reversion_ratio โดยเฉพาะดูมีความหมายและกระจายตัวได้ดี (ไม่กระจุกที่ 0 หรือ 1)
พร้อมป้อนเข้า clustering ใน E3

**ขั้นต่อไปที่ควรลอง:** Phase E3 — standardize feature แล้ว clustering แยกต่อ sector (k=3-5)
พร้อม bootstrap stability check (ARI) ก่อนเลือก k

---
## exp_04 Phase E3 — clustering price-path shape ต่อ sector — 2026-09-14 07:17

**วิธีที่ใช้:** เขียน `model_c_event_clustering/scripts/e3_clustering.py` — standardize feature
ทั้ง 6 ตัวจาก E2 (ไม่คัดเลือกบางส่วน กัน fishing) แล้ว K-means แยกทีละ sector ลอง k=3,4,5 เลือก
k จาก **bootstrap stability (ARI>=0.5) ก่อน แล้วค่อยใช้ silhouette ตัดสินในกลุ่มที่เสถียร** —
bootstrap stability คำนวณโดย resample ข้อมูล 100 รอบ (with replacement), fit K-means บน resample
แต่ละรอบ แล้วใช้ centroid ที่ได้ predict label ของข้อมูลเต็มชุดเดิม เทียบกับ label จาก fit เต็มชุด
เดิมด้วย Adjusted Rand Index — ค่าเฉลี่ย ARI จาก 100 รอบ = stability score

**ข้อมูลที่ใช้:** `model_c_event_clustering/data/event_features.csv` (E2, 4,113 แถว, 11 sector,
n ต่อ sector = 424 [ปกติ] หรือ 127/170 [XLC/XLRE ที่ ETF เปิดตัวทีหลัง])

**ผลลัพธ์:** `model_c_event_clustering/data/e3_cluster_assignments.csv` +
`e3_stability_report.csv` — **ทั้ง 11 sector มี cluster ที่เสถียร (ARI ผ่าน 0.5 ทุก k ที่ลองจริง)**
ARI เฉลี่ยของ k ที่เลือกอยู่ในช่วง 0.62-0.90 (สูงมาก) k ที่เลือกส่วนใหญ่คือ k=3 (8/11 sector),
k=4 สำหรับ XLC, XLF, XLY

**มุมมอง/การตีความ:** ผลที่ cluster เสถียรทุก sector **ไม่ใช่เรื่องน่าแปลกใจหรือสัญญาณบวกใดๆ
ต่อคำถามวิจัยหลัก** — feature ที่ใช้ (cum_return_pre/post, reversion_ratio ฯลฯ) เป็นตัวชี้วัด
ต่อเนื่องที่มี variance ตามธรรมชาติ (บางข่าวราคาขึ้นแรง บางข่าวลงแรง บางข่าวแทบไม่ขยับ) K-means
แทบจะหา partition ที่เสถียรทางเรขาคณิตได้เสมอจากข้อมูลแบบนี้ — **คำถามที่แท้จริงยังไม่ได้ตอบ**คือ
cluster เหล่านี้สอดคล้องกับ `sector_impact_score` จาก rule engine (exp_03) หรือเป็นแค่การแบ่งกลุ่ม
ตามขนาดโดยไม่เกี่ยวกับตัวแปรที่ rule engine ใช้เลย — ต้องรอ Phase E5 (Kruskal-Wallis ตาม
pre-registered criteria ใน E4) ถึงจะตอบได้จริง

**ขั้นต่อไปที่ควรลอง:** Phase E4 — เขียน pre-registered test criteria (commit ก่อนเห็นผล E5
เท่านั้น) แล้ว Phase E5 — join กับ sector_impact_score จาก exp_03 รัน Kruskal-Wallis ตามที่
pre-register ไว้เป๊ะ

---
## exp_04 Phase E4 — pre-register เกณฑ์ทดสอบ E5 — 2026-09-14 07:19

**วิธีที่ใช้:** เขียน `model_c_event_clustering/PRE_REGISTERED_TEST.md` **ก่อน** join
`e3_cluster_assignments.csv` กับ `sector_impact_score`/channel score จาก `exp_03` เลยแม้แต่ครั้ง
เดียว (ยังไม่มีการคำนวณ test statistic ใดๆ ณ จุดที่เขียนไฟล์นี้ — commit นี้จึงมี timestamp
ก่อน commit ของ Phase E5 เสมอ ตรวจสอบย้อนหลังได้จาก git log) กำหนดตายตัวไว้ล่วงหน้า:
- Metric: Kruskal-Wallis (ไม่ใช้ ANOVA เพราะ return ไม่ normal), effect size = eta-squared
  ประมาณจาก H statistic (Tomczak & Tomczak, 2014)
- ขอบเขต: เฉพาะ sector ที่ E3 พบ cluster เสถียร (ทั้ง 11 sector ตามผล E3), ตัวแปรหลักคือ
  `sector_impact_score` เท่านั้น (channel C1-C7 เป็น exploratory รอง กัน multiple-comparison
  จากการเลือกตัวแปรที่ดูดีที่สุดหลังเห็นผล)
- เกณฑ์ผ่าน: `p < 0.05` **และ** `eta_squared > 0.06` พร้อมกันทั้งสองข้อ — ไม่ปรับ correction
  ข้าม sector (รายงานผลดิบตรงไปตรงมา พร้อม caveat เรื่อง false positive จาก multiple testing)
- Triangulation protocol: ต้องเทียบทุก sector กับผล R5 เดิมเสมอ — สอดคล้องกัน (negative ทั้งคู่)
  = หลักฐานแข็งแรงขึ้น, ขัดแย้งกัน = ตั้งเป็นคำถามเปิด ไม่ฟันธง

**ข้อมูลที่ใช้:** ไม่มี — เป็น phase เขียนเกณฑ์ล้วนๆ ไม่แตะข้อมูลผลลัพธ์ใดๆ

**ผลลัพธ์:** ไฟล์ `PRE_REGISTERED_TEST.md` commit แล้ว (ตรวจสอบ diff ว่าไม่มีตัวเลขผลทดสอบใดๆ
ปนอยู่ในไฟล์นี้เลย เป็นแค่ methodology/threshold ล้วนๆ)

**มุมมอง/การตีความ:** ไม่มี — phase นี้ไม่มีผลให้ตีความ เป็นการล็อกกฎก่อนเห็นข้อมูลตามหลัก
"ห้าม fishing" ที่กำหนดไว้

**ขั้นต่อไปที่ควรลอง:** Phase E5 — join กับ `sector_impact_score` จาก exp_03 จริง รัน
Kruskal-Wallis ตามที่ pre-register ไว้เป๊ะ ไม่ปรับอะไรเพิ่มหลังเห็นผล

---
## exp_04 Phase E5 — รันเทสตาม pre-registered criteria + triangulation — 2026-09-14 07:22

**วิธีที่ใช้:** เขียน `model_c_event_clustering/scripts/e5_validate.py` — รัน rule engine ของ
`exp_03` จริง (reuse `run_engine_on_all_news()` จาก `model_c_rulebase/scripts/r5b_validate.py`
โดยตรง ไม่เขียน logic คำนวณคะแนนใหม่ กัน engine 2 เวอร์ชันเพี้ยนจากกัน) join
`sector_impact_score` กับ cluster label จาก E3 แล้วรัน Kruskal-Wallis ตามที่ pre-register ไว้ใน
E4 เป๊ะ (ไม่ปรับ metric/threshold ใดๆ เพิ่มหลังเห็นผล)

**บั๊กที่เจอระหว่างรัน (แก้ก่อนได้ผลจริง):** channel score บางช่อง (เช่น C3 สำหรับทุก sector
ยกเว้น XLF ที่ loading=0 เสมอ) เป็นค่าเดียวกันหมดทุกแถวของ sector นั้น (ไม่มี variance เลย) ทำให้
`scipy.stats.kruskal` raise `ValueError: All numbers are identical` — แก้โดยเช็ค variance ก่อน
เรียก kruskal ถ้าไม่มี variance เลยให้บันทึกเป็น `NaN`/`note="no variance"` ไม่ใช่เดา p-value
หรือข้ามเงียบๆ

**ข้อมูลที่ใช้:** `sector_impact_score` จาก exp_03 R4 (rerun จริงผ่านโค้ดเดียวกับ R5b, 436 ข่าว
x 11 sector = 4,796 แถว), cluster label จาก E3 (4,113 แถว, ทั้ง 11 sector), หลัง join เหลือ
3,955 แถว (ส่วนต่างจากข่าวที่ R3 สกัดไม่สำเร็จ 16 ข่าว + จุดตัดจาก E1's window exclusion)

**ผลลัพธ์ (ตัวเลขจริง, primary test = sector_impact_score):**

| Sector | n | k | H | p | eta² | ผ่าน/ไม่ผ่าน | R5 rho(N=1) | R5 rho(N=21) |
|---|---|---|---|---|---|---|---|---|
| XLB | 408 | 3 | 1.711 | 0.4251 | −0.0007 | fail | −0.019 | −0.098 |
| XLC | 121 | 4 | 2.266 | 0.5191 | −0.0063 | fail | +0.213 | +0.190 |
| XLE | 408 | 3 | 0.428 | 0.8072 | −0.0039 | fail | +0.037 | −0.063 |
| XLF | 408 | 4 | 1.050 | 0.7892 | −0.0048 | fail | +0.080 | +0.104 |
| XLI | 408 | 3 | 0.420 | 0.8105 | −0.0039 | fail | +0.078 | +0.052 |
| XLK | 408 | 3 | 1.104 | 0.5758 | −0.0022 | fail | −0.033 | −0.091 |
| XLP | 408 | 3 | 1.867 | 0.3933 | −0.0003 | fail | −0.058 | +0.012 |
| XLRE| 162 | 3 | 1.145 | 0.5642 | −0.0054 | fail | −0.019 | +0.070 |
| XLU | 408 | 3 | 1.571 | 0.4559 | −0.0011 | fail | +0.061 | +0.006 |
| XLV | 408 | 3 | 2.994 | 0.2238 | +0.0025 | fail | −0.122 | −0.118 |
| XLY | 408 | 4 | 1.887 | 0.5962 | −0.0028 | fail | −0.024 | +0.018 |

**0/11 sector ผ่านเกณฑ์ (p<0.05 AND eta²>0.06) — negative result เต็มรูปแบบ ทั้ง primary test**

**Secondary/exploratory (channel C1-C7, 77 การทดสอบ = 11 sector x 7 channel):** **0/77 ผ่าน
เกณฑ์เช่นกัน** — ที่น่าสนใจ: XLP channel C4 (credit risk) ได้ p=0.0389 (< 0.05 เดี่ยวๆ) แต่
eta²=0.0111 (< 0.06 ขาดลอย) → **ไม่ผ่าน** ตามเกณฑ์คู่ที่ pre-register ไว้ — เป็นตัวอย่างที่ตรง
เป้าหมายการออกแบบเกณฑ์นี้พอดี (กัน sample size ใหญ่ [n=408] ทำให้ p ต่ำได้ง่ายโดยไม่มี effect
ขนาดที่มีความหมายจริง) ถ้าไม่มี eta² threshold คู่ไว้ อาจรายงานผิดว่า XLP มีสัญญาณ

**Triangulation check กับ R5 (ตามที่ pre-register ไว้):** **ทั้ง 11 sector สอดคล้องกับ R5 เดิม
100%** — ไม่มี sector ไหนขัดแย้งกัน (ไม่มีเคสที่ผ่านเกณฑ์ exp_04 แต่ R5 บอกไม่มีสัญญาณ หรือกลับกัน)
ทุก sector ทั้งสองวิธีให้ข้อสรุปเดียวกัน: ไม่มีสัญญาณที่มีนัยสำคัญและขนาดผลใหญ่พอ

**มุมมอง/การตีความ:** นี่คือ **triangulation ที่สำเร็จตามเป้าหมาย** — exp_04 ใช้วิธีวัดที่ต่างไป
โดยสิ้นเชิงจาก exp_03 (ดูรูปร่างเส้นราคาทั้งเส้น + cluster แทนที่จะดู correlation กับ CAR
endpoint เดียว) แต่ได้ข้อสรุปเดียวกันเป๊ะ: **rule-based sector_impact_score จาก exp_03 ไม่มี
ความสัมพันธ์ที่ตรวจจับได้กับพฤติกรรมราคาจริงไม่ว่าจะวัดด้วยวิธีไหน** — ความสอดคล้อง 100% ระหว่าง
สองวิธีที่เป็นอิสระจากกัน (correlation-based vs. cluster-based) ทำให้ข้อสรุป negative ของ exp_03
**หนักแน่นขึ้นมาก** ไม่ใช่แค่เป็น artifact ของวิธีวัดแบบใดแบบหนึ่ง

**ขั้นต่อไปที่ควรลอง:** ไม่มี Phase E6 (ตามที่ pre-register ไว้ — เป้าหมาย exp_04 คือ triangulate
ไม่ใช่สร้างโมเดลใหม่) ปิด exp_04 ด้วยผลนี้ เปิด PR ทิ้งไว้ให้ผู้ใช้ตัดสินใจเรื่อง merge — ข้อเสนอ
สำหรับงานถัดไปนอก exp_04: ทุ่มเวลาที่ sector-news component (`feature/ensemble-sandbox`) แทน
ตามที่ exp_03 R6 แนะนำไว้แล้ว ยืนยันซ้ำด้วยหลักฐานที่แข็งแรงขึ้นจาก exp_04 นี้
