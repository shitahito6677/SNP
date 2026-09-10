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

## sandbox_phase1_stub_interfaces — 2026-09-11 03:20 (+07:00)

**วิธีที่ใช้:** Phase 1 (นิยามใหม่ตามคำสั่งผู้ใช้ — เฉพาะ stub interface เท่านั้น ไม่ wrap
โมเดลจริง) เขียน `sandbox/inference/model_{a,b,c}.py` — `predict()` คืนค่า deterministic
(seed จาก sha256 ของ input ผ่าน `_stub_utils.py`, ไม่ใช้ `hash()` built-in เพราะไม่ stable
ข้าม process) ทุก return dict มี `is_stub: True` เสมอ, ทุก docstring ขึ้นต้นด้วย
"STUB — replace with real model when ready" ตามที่กำหนด, contract (input/output schema
ของทั้ง 3 โมเดล) documented ใน `sandbox/inference/README.md` แก้ contract ของ Model C ให้
`sector` เป็น sector ETF code (เช่น `"XLK"`) ตามที่ผู้ใช้ระบุล่าสุด (เดิม draft แรกใช้ GICS
sector name เต็ม เปลี่ยนแล้วทั้ง docstring และ README ให้ตรงกัน)

**ข้อมูลที่ใช้:** ไม่มีข้อมูลจริงเกี่ยวข้อง (stub ทั้งหมดเป็นค่า deterministic จาก seed
ไม่ใช่ prediction จริง)

**ผลลัพธ์:** รัน `python3 -m sandbox.scripts.smoke_test` ผ่านทั้ง 19 check ที่เกี่ยวข้อง
(determinism ของ stub ทั้ง 3 ตัวข้าม call ซ้ำ, output schema มี class/score/is_stub ครบ,
class อยู่ใน enum ที่กำหนด, `is_stub` เป็น `True` ทุกตัว) commit เฉพาะ `sandbox/inference/`
แยกจากส่วนอื่น (commit `dd10150`) แล้ว push ขึ้น `origin/feature/ensemble-sandbox` แล้ว
ตามที่ผู้ใช้กำหนด workflow ไว้

**มุมมอง/การตีความ:** stub 3 ตัวพร้อมใช้เป็น dependency ให้ Phase 2 (dashboard) เรียกได้แล้ว
โดยไม่ต้องรอโมเดลจริง — จุดที่ต้องระวังตอน swap เป็นของจริงคือ Model C: contract กำหนดให้
`sector` เป็น ETF code ตรงๆ (ไม่ใช่ GICS name) ดังนั้นโค้ดจริงที่จะ wrap ต้องรับ ETF code
เข้ามาเลย ไม่ต้อง map เพิ่มข้างในฟังก์ชัน (caller เป็นผู้ map จาก ticker ด้วย
`sandbox.config.ticker_to_etf()` ก่อนเรียก)

**ขั้นต่อไปที่ควรลอง:** Phase 2 — Flask + Plotly.js dashboard (dark theme, ตาม spec ผู้ใช้)
เรียก stub ทั้ง 3 นี้ผ่าน rule engine (`sandbox/rules/`) ที่มีอยู่แล้วจาก draft ก่อนหน้า
(ยังไม่ commit — จะ commit พร้อม Phase 2)
---

## sandbox_phase2_dashboard — 2026-09-11 02:45 (+07:00)

**วิธีที่ใช้:** Phase 2 (แก้ไข stack ตามคำสั่งผู้ใช้ — Flask + Plotly.js ผ่าน CDN แทน
Streamlit, dark theme บังคับ) เขียนใหม่ทั้งชุด แทนที่ dashboard เดิมจาก draft ก่อนหน้า
(ลบ `sandbox/app/static`, `sandbox/app/templates` เดิมทิ้ง):
- โครงไฟล์ใหม่ตามที่กำหนด: `sandbox/app/server.py` (entry point), `sandbox/static/css/style.css`,
  `sandbox/static/js/main.js`, `sandbox/templates/{base,dashboard,events,rules,experiments}.html`
- Dashboard: sidebar เลือก ticker (5 ตัวจาก Phase 0) + date range, กราฟแท่งเทียน (Plotly.js
  candlestick) ดึงจาก `GET /api/prices/<ticker>` (อ่าน `sandbox/data/prices/{TICKER}.csv`),
  เส้นประแนวตั้ง = macro event สีตาม class, จุดสีบนแท่งเทียน = company news event เฉพาะ ticker,
  คลิก marker เปิด popup (วันที่/class/score/is_stub badge)
- Events (manual event injection): ฟอร์ม inject event เอง — macro เรียก Model C แยกทุก
  sector ของ 5 ticker (เก็บผลต่อ ticker ใน `per_ticker`), company เรียก Model B ticker เดียว
  — เขียนใหม่เป็น `sandbox/events_store.py` (แทน `persistence.py` เดิมที่ concept ไม่ตรงกับ
  event-based chart) เก็บที่ `sandbox/data/events/events.jsonl`
- Rules: แสดง 27-row rule table เดิม (ไม่เปลี่ยน logic)
- Experiments: ตาราง event ทั้งหมดที่เคย inject
- STUB badge มุมขวาบนทุกหน้า คำนวณจาก module-level `IS_STUB` constant ที่เพิ่มใน
  `sandbox/inference/model_{a,b,c}.py` (ของใหม่ เพิ่มจาก Phase 1 ที่ commit ไปแล้ว — ไม่เรียก
  `predict()` จริงเพื่อเช็คแล้ว ประหยัดกว่า probe เดิม) พร้อมแก้ contract ของ Model C ให้ `sector`
  เป็น ETF code ให้ตรงกับ Phase 1 ที่แก้ไปแล้ว (`sandbox/inference/README.md` อัปเดตตาม)

**ข้อมูลที่ใช้:** ราคาจาก `sandbox/data/prices/*.csv` (Phase 0, 1,255 แถว/ตัว) event ที่ใช้
ทดสอบเป็น headline สมมติที่พิมพ์เองผ่าน curl (ไม่ใช่ข่าวจริง — เคลียร์ทิ้งจาก
`data/events/events.jsonl` หลังทดสอบแล้ว เพราะ gitignored อยู่แล้ว)

**ผลลัพธ์:** รัน `python3 -m sandbox.app.server` จริงที่ port 5050 ทดสอบครบ:
- หน้า `/`, `/dashboard`, `/events`, `/rules`, `/experiments` → ทุกหน้า HTTP 200
- `GET /api/prices/NVDA` → 1,255 วัน (2021-09-10 → 2026-09-10) ตรงกับไฟล์ Phase 0
- `GET /api/prices/AAPL` (ticker ไม่อยู่ใน universe) → 400 พร้อม error message
- `POST /api/events` (company, NVDA) → 200, ได้ class/score/is_stub ถูก schema
- `POST /api/events` (macro) → 200, ได้ `per_ticker` ครบทั้ง 5 ticker แยกผลกันจริง (เช่น
  NVDA/SCHW/TSLA ได้ negative, META/FDX ได้ neutral จาก headline เดียวกัน — ยืนยันว่า sector
  ต่างกันจริงทำให้ seed/ผลต่างกัน ไม่ใช่ hardcode ค่าเดียวซ้ำ)
- `POST /api/events` ที่ไม่ครบ field (ไม่มี headline) → 400 พร้อม error message
- `GET /api/events?ticker=NVDA` หลัง inject → เห็น event ที่เพิ่งสร้างครบทั้ง macro/company
- หน้า `/experiments` render ตารางแสดง event ที่เพิ่ง inject ถูกต้อง (grep เจอ "ล่าสุด 2 รายการ")
- หน้า `/rules` render ครบ 27 แถว (grep count = 27)
- `node --check sandbox/static/js/main.js` ผ่าน (ไม่มี syntax error)
- `python3 -m sandbox.scripts.smoke_test` ยังผ่านครบ 19 check เหมือนเดิม (แก้ smoke test ให้
  ส่ง ETF code ให้ model_c ตาม contract ใหม่)

**มุมมอง/การตีความ:** dashboard ทำงานจบ end-to-end จริงตาม spec ที่กำหนด (dark theme, Plotly
candlestick, event marker แยก macro/company, popup, STUB badge) จุดออกแบบที่ตัดสินใจเอง
(ไม่ได้ระบุในโจทย์ตรงๆ ต้องคิดต่อเอง): (1) macro event เก็บผลแยกต่อ ticker/sector ใน event
เดียว แทนที่จะบังคับ class เดียวกันทุก ticker เพราะ Model C เทรนแยกตาม GICS sector จริง
เป็นการตีความที่ตรงกับตัวโมเดลมากกว่า (2) Rules/Experiments page ไม่ได้ระบุ detail มาก
ในโจทย์ ใช้ rule table เดิมและ event history ตามลำดับ ตีความจาก nav bar name ที่ให้มา

**ขั้นต่อไปที่ควรลอง:** ให้อาจารย์ดู UI จริงเพื่อ feedback รูปแบบ/สี ก่อนลงลึก Phase ถัดไป
(เช่น เพิ่ม Model A signal เข้า dashboard ด้วย — ตอนนี้ Model A ยังไม่ได้ใช้ใน dashboard เลย
เพราะไม่มี "event" ที่ผูกกับวันที่ชัดเจนแบบ B/C ต้องคิด UI แยกสำหรับมันทีหลัง)
---
