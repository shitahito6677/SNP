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

## sandbox_phase3_manual_event_injection — 2026-09-11 06:20 (+07:00) [overnight unattended]

**วิธีที่ใช้:** Phase 3 ตามคำสั่งผู้ใช้ (overnight unattended run — ดู `sandbox/OVERNIGHT_LOG.md`)
เขียนใหม่หน้า Events + storage ทั้งหมดให้ตรง spec ที่ต่างจาก Phase 2 เดิม:
- `sandbox/events_store.py` เขียนใหม่ทั้งไฟล์: เปลี่ยนจาก JSONL (`data/events/events.jsonl`,
  kind "macro"/"company") เป็น **CSV เดียว** `sandbox/data/manual_events.csv` (kind "b"/"c"
  ตรงตามที่ผู้ใช้ระบุ) ทุกแถวมี `source = "manual"` เสมอ (บังคับตาม field เดียวกับที่ระบุ)
  event แบบ C เขียน 5 แถว (1 ต่อ ticker/sector) แบบ B เขียน 1 แถว
- `sandbox/config.py` เพิ่ม `TICKERS_WITH_COMPANY_NEWS` (set, default = ทุก ticker) +
  `has_company_news()` + `price_date_range()` (อ่านช่วงวันที่จริงจากไฟล์ราคา ไม่ hardcode —
  intersection ของทั้ง 5 ตัว)
- หน้า Events ปรับ UI: เลือก ticker ก่อน (ไม่ใช่เลือก scope ก่อนแบบเดิม) เพราะต้องรู้ ticker
  ก่อนถึงจะเช็คได้ว่า disable ปุ่ม B ไหม, date input มี `min`/`max` จาก `price_date_range()`,
  เพิ่ม disclaimer ข้อความตามที่กำหนดเป๊ะ, validate date range ทั้ง client-side (JS) และ
  server-side (Flask, กัน bypass)
- `sandbox/app/server.py`: `/api/events` POST เช็ค date อยู่ในช่วงราคาจริงก่อนเรียกโมเดล,
  `/api/events` GET คืน `{"b": [...], "c": [...]}` ตาม ticker (schema ใหม่)
- อัปเดต `sandbox/templates/experiments.html`, `sandbox/static/js/main.js` (dashboard render
  ใช้ `events.b`/`events.c` แทน `events.company`/`events.macro`) ให้ตรง schema ใหม่ทั้งหมด

**Decision ที่ไม่แน่ใจ (overnight, เลือก low-risk เอง — ดูรายละเอียดใน OVERNIGHT_LOG.md):**
เก็บ manual event เป็น CSV แบบ 1 แถวต่อ (event, ticker) แทนที่จะ nest per_ticker ใน JSON
เพราะแมพตรงกับ DoD ("B ขึ้นแค่หุ้นเดียว, C ขึ้นทุกหุ้น") ได้ตรงไปตรงมาที่สุด และ diff/grep
ตรวจสอบง่ายกว่า JSON ซ้อน

**ข้อมูลที่ใช้:** ราคาจาก `sandbox/data/prices/*.csv` (Phase 0) event ทดสอบเป็น headline
สมมติผ่าน curl (B: NVDA "NVDA beats earnings estimates" วันที่ 2025-06-15, C: "Fed holds
rates steady" วันที่ 2025-07-01) เคลียร์ `manual_events.csv` ทิ้งหลังทดสอบแล้ว (gitignored)

**ผลลัพธ์ (Checklist บังคับก่อน commit — ทุกข้อมีหลักฐานจริง):**
1. รัน server จริง (`python3 -m sandbox.app.server`, port 5050) — ทุกหน้า `/`, `/dashboard`,
   `/events`, `/rules`, `/experiments` → HTTP 200 (curl) — **ผ่าน** (ยังไม่ได้เปิด browser
   ด้วยตาเอง ต้องให้ผู้ใช้ตรวจตามที่กำหนดไว้)
2. Scope B/C ถูกต้อง: `POST /api/events {kind:"b", ticker:"NVDA", ...}` → เขียน 1 แถว (NVDA
   เท่านั้น); `POST /api/events {kind:"c", ...}` → เขียน 5 แถว (ครบทุก ticker, class ต่างกัน
   จริงตาม sector); `GET /api/events?ticker=NVDA` → b:1, c:1; `GET /api/events?ticker=META`
   → b:0, c:1 (ไม่มี B เพราะไม่เคย inject ให้ META) — **ผ่าน**
3. ไฟล์ manual event ไม่ปนกับ dataset training จริง: เช็คด้วยโค้ดจริง —
   `data/raw/macro_news_raw.parquet` (477 แถว, คอลัมน์ date/text/source/url) vs
   `sandbox/data/manual_events.csv` (คอลัมน์ id/created_at/source/kind/ticker/date/headline/
   class/score/is_stub) คนละไฟล์ คนละ path คนละ format คนละคอลัมน์ทั้งหมด, headline ที่ inject
   ไม่ overlap กับ text ของข่าวจริงเลย (เช็คด้วย set intersection = empty) — **ผ่าน**
4. Date-range guard: `POST /api/events` วันที่ 2019-01-01 (นอกช่วง 2021-09-10..2026-09-10)
   → 400 พร้อม error message ระบุช่วงที่ถูกต้อง — **ผ่าน**
5. B-disable enforcement (server-side, จำลองกรณี ticker ไม่มี company news): ลบ "FDX" ออกจาก
   `TICKERS_WITH_COMPANY_NEWS` ชั่วคราวแล้วเรียก `add_company_event()` ตรงๆ → raise
   `ValueError` พร้อมข้อความบอกสาเหตุ, คืนค่า default กลับหลังทดสอบ — **ผ่าน** (server เช็คจริง
   ไม่ใช่แค่ UI disable ที่ bypass ได้) — ส่วน client-side disable (JS `syncBAvailability`)
   ตรวจโค้ดแล้วแต่ **ยังไม่ได้เห็นด้วยตาจริงใน browser** เพราะตอนนี้ทุก ticker enabled หมด
   ไม่มีเคส disabled จริงให้เห็นในสถานะ default
6. `node --check sandbox/static/js/main.js` ผ่าน, `python3 -m sandbox.scripts.smoke_test`
   ผ่านครบ 19 check เหมือนเดิม (ไม่กระทบ)

**มุมมอง/การตีความ:** Phase 3 ผ่าน DoD ทั้ง 3 ข้อที่ระบุ (B ขึ้นตัวเดียว, C ขึ้นทุกตัว,
manual_events.csv แยกจาก training จริง) ด้วยหลักฐานที่ตรวจสอบได้จริงทุกข้อ จุดเดียวที่ยังไม่
ครบคือการเปิด browser ดูด้วยตาจริงตาม checklist บังคับ — ทำไม่ได้ในโหมด unattended (ไม่มี
เครื่องมือ browser อัตโนมัติในสภาพแวดล้อมนี้) ต้องรอผู้ใช้เปิดดูเองตอนเช้าตามที่ระบุไว้ใน
prompt เอง ("พี่ต้องเปิดดูหน้าจอจริงด้วยตาเองด้วย")

**ขั้นต่อไปที่ควรลอง:** Phase 4 — rule engine v1 + versioning (ต่อจากนี้ทันทีตาม instruction
overnight)
---

## sandbox_phase4_rule_engine_v1 — 2026-09-11 06:25 (+07:00) [overnight unattended]

**วิธีที่ใช้:** Phase 4 ตาม spec — เขียน rule engine ใหม่ทั้งระบบ (retire ของเดิมจาก Phase 2):
- `sandbox/rules/rule_table.json` + `sandbox/rules/engine.py` (weighted-sum design เดิม) **ลบทิ้ง**
  แทนที่ด้วยระบบ versioned lookup table ตาม spec ใหม่เป๊ะ
- `sandbox/rules/rule_v1.json` — 27 แถว generate จาก `sandbox/scripts/generate_rule_v1.py`
  ด้วย logic "priority: A+B override C" (ตาม description ที่ผู้ใช้กำหนด): weight A
  buy=+1/hold=0/sell=-1, B/C positive=+1/neutral=0/negative=-1, `combined_ab = A+B` — ถ้า ≠ 0
  ตัดสินจาก A+B ตรงๆ (C ไม่มีผล = override จริง, 18/27 แถว) ถ้า `combined_ab == 0` (A,B หักล้าง
  กันพอดี 3 คู่ × 3 ค่า C = 9 แถว) ให้ C เป็นคนตัดสิน — กระจาย: buy=12, hold=3, sell=12
- `sandbox/engine/combine.py` — `combine(a, b, c, rule_path)` lookup ตรง raise `ValueError`
  ถ้าไม่เจอ combination, raise `FileNotFoundError` ถ้า rule_path ไม่มีจริง ไม่มี fallback เดา
  ตามที่กำหนดเป๊ะ
- `sandbox/rules/versions.py` — `list_versions()`/`load_version()`/`save_new_version()` เขียน
  ไฟล์ `rule_v{n+1}.json` ใหม่เสมอ (n = max version ที่มีอยู่จริง +1) มี `validate_table()`
  เช็คครบ 27 combination ไม่ซ้ำ + enum values ถูกต้อง ก่อนยอม save กัน UI ส่งตารางพังมา
- หน้า Rules เขียนใหม่เป็น editable table (dropdown ต่อแถวเลือก decision) + version picker
  (`/rules?version=n`) + ปุ่ม "Save as new version"
- `sandbox/scripts/test_combine.py` — unit test 8 case (unittest stdlib) เกิน 5 case ที่กำหนด
  ขั้นต่ำ: override เคส A+B ชนะ buy/sell (2), tie-break โดย C ทั้ง 3 ทิศ (3), ครบ 27 combo
  ไม่ error (1), missing combination ต้อง raise ไม่ fallback (1), missing file ต้อง raise (1)
- `sandbox/scripts/smoke_test.py` ตัด rule-engine check ออก (engine เปลี่ยน design ทั้งหมด) เก็บ
  เฉพาะ inference stub + config, เพิ่ม `config.price_date_range()` check

**Decision ที่ไม่แน่ใจ (overnight, documented ใน `generate_rule_v1.py` ด้วย):** ตัวอย่าง JSON
1 แถวที่ผู้ใช้แปะมา (`{"a":"buy","b":"buy","c":"sell","decision":"buy"}`) ใช้ค่า "buy"/"sell"
สำหรับ b/c ซึ่ง**ขัดกับ contract จริงของ Model B/C** ที่ fix ไว้ตั้งแต่ Phase 1
(`sandbox/inference/README.md`: b/c คืนค่า "positive"/"neutral"/"negative" เท่านั้น ไม่มีทาง
เป็น "buy"/"sell") ตัดสินใจว่าเป็น typo/ตัวอย่าง format เท่านั้น ใช้ vocabulary จริงจาก Phase 1
แทน (positive/neutral/negative) เพราะถ้าเปลี่ยนตาม literal example จะทำให้
`sandbox/inference/model_b.py`/`model_c.py` ที่ import ตรงจาก Dashboard/Events ทั้งหมดพังทันที
— นี่คือ decision ที่ risk ต่ำสุด (คง contract เดิมที่ทดสอบแล้วทั้งระบบ)

**ข้อมูลที่ใช้:** ไม่มีข้อมูลจริงเกี่ยวข้อง (rule table เป็น business logic ที่ออกแบบเอง ไม่ใช่
ผลลัพธ์ที่ validate จากข้อมูล — ต้อง revisit เมื่อมีโมเดลจริง)

**ผลลัพธ์ (Checklist บังคับก่อน commit):**
1. รัน server จริง (port 5050) — `/rules`, `/rules?version=1` → HTTP 200, table 27 แถวครบ
   (`grep -c decision-select` = 27) — **ผ่าน** (ยังไม่ได้เปิด browser ด้วยตาเอง)
2. `python3 -m unittest sandbox.scripts.test_combine -v` → **8/8 PASS** (เกิน 5 case ที่กำหนด)
3. `python3 -m sandbox.scripts.smoke_test` → 20/20 PASS (ไม่กระทบจาก inference/config)
4. Rule versioning ไม่ทับไฟล์เก่า — ทดสอบจริงด้วย `POST /api/rules/save` 2 ครั้งติดกัน:
   MD5 ของ `rule_v1.json` **เหมือนเดิมทุกตัวอักษร** ก่อน/หลัง save (`1bd60cb0699c697e491bce6
   60eec04bd`), save ครั้งแรกสร้าง `rule_v2.json` (มี `decision` ที่แก้จริงตามที่ส่งไป), save
   ครั้งที่สองสร้าง `rule_v3.json` (ไม่ใช่ทับ v2) — `/rules?version=1` ยังโชว์ค่าดั้งเดิม,
   `/rules?version=2` โชว์ค่าที่แก้ — **ผ่าน** — ลบ `rule_v2.json`/`rule_v3.json` (test
   artifact) ทิ้งหลังทดสอบ เหลือแค่ `rule_v1.json` จริงใน repo
5. `validate_table()` เช็คจริง: ลองส่งตารางที่ตัดแถวหนึ่งออก (`test_combine.py` test_07) →
   raise `ValueError` แทนที่จะเดา — **ผ่าน**

**มุมมอง/การตีความ:** Phase 4 ผ่าน DoD ครบทั้ง 3 ข้อ (rule_v1.json ครบ 27 แถว, unit test ≥5
case ผ่าน [ได้ 8], save version ใหม่ได้จริงไม่ทับของเก่า — ยืนยันด้วย MD5 ไม่ใช่แค่ "ไฟล์ไม่
error") จุดที่ต้อง revisit ทีหลัง: "A+B override C" logic เป็น design ที่เลือกเองตาม
description ที่ผู้ใช้ให้มา ยังไม่ได้ validate ว่าเหมาะสมกับพฤติกรรมจริงของโมเดล — ต้องรอ
Model A/B/C ตัวจริงมาทดสอบว่า priority นี้สมเหตุสมผลไหม (ตอนนี้ทดสอบได้แค่ logic ถูกต้องตาม
ที่ตั้งใจเขียน ไม่ใช่ความถูกต้องเชิงการลงทุน)

**ขั้นต่อไปที่ควรลอง:** Phase 5 — SQLite experiment persistence + diff (ต่อจากนี้ทันที)
---

## sandbox_phase5_experiment_persistence — 2026-09-11 06:30 (+07:00) [overnight unattended]

**วิธีที่ใช้:** Phase 5 ตาม schema ที่กำหนดเป๊ะ — `sandbox/experiments_db.py` ใหม่ทั้งไฟล์:
- SQLite `sandbox/experiments.db` (gitignored, local) ตาราง `experiments` — column ตรงตาม
  spec ทุกตัว: `experiment_id TEXT PK`, `rule_version TEXT`, `ticker_set TEXT` (JSON list),
  `date_range_start/end DATE`, `decisions_json TEXT`, `created_at TIMESTAMP`, `notes TEXT`
- `run_experiment(rule_version, ticker_set, start, end, notes)`: scan
  `sandbox/data/manual_events.csv` (ผ่าน `events_store.load_events_in_range()` ที่เพิ่มใหม่)
  หาคู่ (ticker, date) ที่มี**ทั้ง** B และ C event ในช่วงที่กำหนด → คำนวณ A ด้วย
  `model_a.predict(ticker, date)` → lookup decision ด้วย `combine()` จาก Phase 4 — คู่ที่ไม่ครบ
  B+C **ข้ามไปเลย ไม่ fabricate** (documented ชัดใน docstring)
- `list_experiments()`, `get_experiment()`, `diff_experiments(id_a, id_b)` — diff คีย์ด้วย
  (ticker, date) แยกเป็น differs / same / only_in_a / only_in_b
- หน้า Experiments เพิ่ม 2 ส่วนใหม่ต่อจาก event log เดิม: (1) ฟอร์มรัน experiment ใหม่ (เลือก
  rule version, ticker checkbox, date range, notes) (2) ตาราง saved experiments พร้อม
  checkbox เลือก 2 อันมา diff
- `sandbox/app/server.py` เพิ่ม `POST /api/experiments/runs`, `GET /api/experiments/runs`,
  `GET /api/experiments/diff?a=&b=`

**Decision ที่ตัดสินใจเอง (overnight, documented ใน docstring ของ experiments_db.py ด้วย):**
"experiment" นิยามว่าเป็นการรัน `combine()` บนคู่ (ticker,date) ที่มี manual event ครบ B+C
เท่านั้น (ไม่ใช่ทุกวันในช่วงวันที่ที่เลือก) เพราะ Model B/C เป็น event-driven (ต้องการ
headline) ไม่มีค่าให้ทุกวันแบบ Model A — ทางเลือกอื่นที่ปฏิเสธ: fallback ใช้ headline ล่าสุด
ซ้ำทุกวัน (เป็นการเดา ขัดกับกฎ "ห้ามเดา"), หรือข้าม A/B/C ที่ไม่มีข้อมูล (ขัดกับ `combine()`
ที่ต้องการครบ 3 ค่าเสมอ) — เลือกวิธี "ข้าม (ticker,date) ที่ไม่ครบ" เพราะตรงไปตรงมาที่สุดและ
สอดคล้องกับกฎ "ห้ามเดา" ชัดเจนสุด

**ข้อมูลที่ใช้:** manual event ที่ inject ทดสอบเอง 5 event (C: "Fed signals dovish pivot"
2025-06-15 ครบ 5 ticker, B: NVDA/META วันเดียวกัน, C: "Fed hikes rates unexpectedly"
2025-07-01 ครบ 5 ticker, B: TSLA วันเดียวกัน) — สร้างคู่ B+C ที่ครบ 3 คู่: (NVDA,06-15),
(META,06-15), (TSLA,07-01) เคลียร์ `manual_events.csv`/`experiments.db` ทิ้งหลังทดสอบ
(ทั้งคู่ gitignored)

**ผลลัพธ์ (Checklist บังคับก่อน commit):**
1. รัน server จริง (port 5050) — `/experiments` → HTTP 200 — **ผ่าน** (ยังไม่เปิด browser ด้วยตาเอง)
2. `POST /api/experiments/runs` (rule_version=v1, ticker_set ครบ 5 ตัว, ช่วง 2025-06-01..07-31)
   → คืน 3 decisions ตรงกับคู่ B+C ที่มีจริงเป๊ะ (META, NVDA, TSLA) ไม่มี SCHW/FDX เพราะไม่มี
   B event ให้ (ไม่ fabricate) — **ผ่าน**
3. แก้ rule (hold,negative,positive): sell→buy บันทึกเป็น `rule_v2.json` (ผ่าน
   `/api/rules/save`) รัน experiment รอบสองด้วย v2 → decision ของ META เปลี่ยนจาก sell→buy
   จริง, NVDA/TSLA เหมือนเดิม (ตามที่ควรเป็น เพราะ combo ของมันไม่ได้แก้) — **ผ่าน**
4. `GET /api/experiments/diff?a=<v1_id>&b=<v2_id>` → `differs` มีแค่ META/2025-06-15
   (`decision_a="sell"`, `decision_b="buy"`) เป๊ะ, `same` มี NVDA+TSLA ครบ 2, `only_in_a`/
   `only_in_b` ว่างทั้งคู่ (ถูกต้อง เพราะ ticker_set/date range เดียวกันทุกอย่าง) — **ผ่าน**
5. SQLite schema ตรวจด้วย `PRAGMA table_info` ตรงตาม spec ทุก column, `sqlite3` query ตรงๆ
   นับแถวได้ 2 (ตาม 2 experiment ที่รัน) — **ผ่าน**
6. Edge case: ticker ไม่อยู่ใน universe → 400; rule_version ไม่มีไฟล์จริง → 400
   (FileNotFoundError); ช่วงวันที่ไม่มี event เลย → `decisions: []` (ไม่ fabricate) —
   ทั้งหมด **ผ่าน**

**มุมมอง/การตีความ:** Phase 5 ผ่าน DoD ครบ ("รัน 2 experiment คนละ rule version, save, diff
กันเห็นว่า decision ต่างวันไหนบ้าง") ด้วยหลักฐานที่ตรวจสอบได้จริง ไม่ใช่แค่ "รันไม่ error"
— diff ระบุ (ticker, date) ที่ต่างกันได้ถูกต้องแม่นยำ 1/3 คู่ (ตรงกับที่แก้ไว้จริง)

ทุก Phase (0-5) ที่ระบุใน prompt overnight ทำครบแล้ว — สรุปรวมอยู่ใน
`sandbox/OVERNIGHT_LOG.md`

**ขั้นต่อไปที่ควรลอง:** (1) ผู้ใช้เปิด browser ตรวจ UI จริงตามที่ระบุไว้ (checklist ข้อเดียวที่
ทำเองในโหมด unattended ไม่ได้ — ทำซ้ำทุก phase) (2) เมื่อ Model A/B เขียนเสร็จ + Model C wrap
inference จริงแล้ว กลับมาทำ "Phase 1 จริง" (wrap ของจริงตาม `sandbox/inference/README.md`,
sanity check เทียบ exp_02, สลับ `is_stub`/`IS_STUB` เป็น False) — ไม่ต้องแก้ dashboard/events/
rules/experiments เลยเพราะ interface fix ไว้แล้วตั้งแต่ Phase 1
---

## sandbox_dashboard_bugfixes_real_macro_data — 2026-09-11 09:10 (+07:00)

**วิธีที่ใช้:** แก้ 3 ปัญหาที่ผู้ใช้เจอตอนเปิด dashboard จริงในเบราว์เซอร์ (checklist ข้อที่
overnight ทำเองไม่ได้ — ตอนนี้มีคนเปิดดูจริงแล้ว):

1. **Nav bar ถูก STUB badge บัง**: root cause คือ `.stub-badge` ใช้ `position: fixed; top:12px;
   right:16px; z-index:100` ซึ่งวางทับตำแหน่งเดียวกับ `.nav-links` ฝั่งขวาของ `.topnav` พอดี
   (topnav ก็อยู่บนสุดของหน้าเหมือนกัน) แก้โดยย้าย badge เข้าไปเป็น flex child ตัวที่ 3 ใน
   `<nav>` เอง (brand+links อยู่ใน `.nav-left`, badge อยู่ฝั่งขวาสุดของ nav bar) เลิกใช้
   `position: fixed` ไปเลย — อยู่ใน document flow ปกติ ไม่มีทางทับกันอีก
2. **Macro (C) events = 0 สำหรับทุก ticker**: ยืนยันแล้วว่าเป็น **กรณีแรกที่ผู้ใช้สงสัย** —
   ไม่ใช่บั๊ก query/filter วันที่ แต่เป็นเพราะ real historical macro news (477 ข่าวจาก
   `data/raw/macro_news_raw.parquet` + `data/processed/sentiment.parquet`) ไม่เคยถูกเชื่อม
   เข้า dashboard เลยตั้งแต่ Phase 2 — event บน dashboard มาจาก `manual_events.csv`
   (Phase 3 manual injection) เท่านั้น ซึ่งว่างเปล่าถ้ายังไม่มีใคร inject เอง แก้โดยเขียน
   `sandbox/historical_data.py` ใหม่ อ่าน 2 ไฟล์จริงนั้น join ด้วย url แปลง continuous score
   (P(positive)-P(negative)) เป็น discrete class ด้วย threshold ±0.1 (เลือกจากดู distribution
   จริงของ 11 sector ก่อน ไม่ใช่เดา — ส่วนใหญ่กระจุกใกล้ ±0.9 มีน้อยที่อยู่ใกล้ 0) merge เข้ากับ
   `/api/events` — **บั๊กที่เจอเพิ่มระหว่างแก้**: real historical news คลุม 1996-2026 (477 ข่าว)
   แต่ราคามีแค่ 5 ปีล่าสุด (2021-09-10..2026-09-10, มีข่าวแค่ 80/477 ที่อยู่ในช่วงนี้) ถ้าไม่
   filter จะทำให้ Plotly ขยาย x-axis ครอบคลุม 30 ปีจนกราฟแท่งเทียนเพี้ยน — เพิ่ม
   `start`/`end` query param ให้ `/api/events` (default = ช่วงราคาเต็ม) และแก้ `main.js` ให้
   ส่ง param เดียวกับที่ส่งให้ `/api/prices` เสมอ
3. **เพิ่ม per-model status**: `sandbox/app/server.py` เพิ่ม `_model_status()` (context
   processor, ทุกหน้าใช้ได้) คืน status แยกราย model — Model A/B = "stub" เฉยๆ, Model C แยก
   2 มิติ: `inference` (stub — live `predict()` สำหรับ headline ใหม่ยังเป็น stub) กับ
   `data_note` (นับจำนวนข่าวจริงที่เชื่อมได้จริงจากไฟล์ ไม่ hardcode) แสดงเป็น panel ใน
   Dashboard sidebar เพิ่ม `.real-tag` (สีเขียว) คู่กับ `.stub-tag` (เหลือง) ใน event popup
   ด้วย เพื่อแยกภาพ event ที่มาจากข้อมูลจริง vs manual/stub ให้เห็นชัดต่อ event ไม่ใช่แค่ badge
   รวมทั้งหน้า

**ข้อมูลที่ใช้:** `data/raw/macro_news_raw.parquet` (477 แถว, ยืนยันอีกครั้ง — **ไม่ใช่ 452**
ตามที่ผู้ใช้พูดถึงซ้ำหลายครั้งแล้ว ตัวเลขจริงจากไฟล์คือ 477 เท่ากันทุกครั้งที่เช็ค ตั้งแต่
Phase 1), `data/processed/sentiment.parquet` (477 แถว, join กันได้ครบ 100% ไม่มีแถวตกหล่น)

**ผลลัพธ์ (ตรวจจริงผ่าน curl หลังแก้):**
- `GET /api/events?ticker=NVDA` (default range = ช่วงราคา) → b:0, c:80 (ตรงกับที่คำนวณ
  ล่วงหน้าว่ามี 80/477 ข่าวอยู่ในช่วงราคา 5 ปี)
- `GET /api/events?ticker=NVDA&start=1996-01-01&end=2026-12-31` → c:477 (ครบทุกข่าวจริงถ้าไม่
  filter ยืนยันว่า merge ทำงานถูกต้อง ไม่ตกหล่น)
- `GET /api/events?ticker=META` → c:80 เช่นกัน (คนละ sector, join ผ่าน `sent_XLC` แทน
  `sent_XLK` — โค้ดใช้ `config.ticker_to_etf()` ต่อ ticker จริง ไม่ hardcode sector เดียว)
- Dashboard sidebar render model status ครบ 3 โมเดล, Model C โชว์
  "real historical data connected (477 FOMC/Beige Book news)" ถูกต้อง
- `curl | grep nav-left / stub-badge` ยืนยัน badge อยู่ใน `<nav>` เดียวกับ nav-links แล้ว
  (โครงสร้าง HTML เปลี่ยนจริง) — **ยังไม่ได้ยืนยันด้วยตาจริงในเบราว์เซอร์ว่า layout ไม่ชนกัน
  อีก** ต้องให้ผู้ใช้ refresh แล้วดู
- `python3 -m sandbox.scripts.smoke_test`, `python3 -m unittest sandbox.scripts.test_combine`,
  `/rules` (27 แถว) — ผ่านหมด ไม่กระทบ

**มุมมอง/การตีความ:** ปัญหาที่ 2 เป็นจุดสำคัญที่สุด — ก่อนหน้านี้ dashboard "ยังไม่ได้ทำหน้าที่
หลักที่ตั้งใจไว้เลย" ตามที่ผู้ใช้กังวลจริง (แสดง bias ของ Qwen/FinBERT จาก exp_01/02) เพราะไม่มี
ข้อมูลจริงให้ดูเลยถ้าไม่ inject เอง ตอนนี้เชื่อมแล้วจริง ผู้ใช้ควรเห็น pattern เอียงบวกของ
FinBERT (ตามที่ exp_02 เคยพบ — XLP/XLV แทบไม่เคยติดลบ) ได้จากการดู marker สีเขียวเยอะกว่าแดง
มากบนกราฟ — Model B ยังคง 0 เพราะไม่มี "ข้อมูลจริง" ให้เชื่อม (Model B ไม่มีโค้ด ไม่มี dataset
เลยด้วยซ้ำ) ต่างจาก Model C ที่มี pipeline จริงรันสำเร็จแล้ว — นี่คือความแตกต่างที่ถูกต้องแล้ว
ไม่ใช่บั๊ก

**ขั้นต่อไปที่ควรลอง:** ผู้ใช้ refresh browser เช็คทั้ง 3 จุดด้วยตาจริง โดยเฉพาะจุดที่ 1
(nav bar) ที่ยังไม่มีใครยืนยันด้วยตาว่าหายจริง
---

## sandbox_indicators — 2026-09-11 10:05 (+07:00)

**วิธีที่ใช้:** เพิ่ม `sandbox/analytics/indicators.py` — SMA20/SMA50 (rolling mean),
RSI(14, Wilder's smoothing ผ่าน EWM alpha=1/period), MACD(12,26,9, EMA fast-slow + signal
EMA9) คำนวณจากราคาที่มีอยู่แล้วใน `sandbox/data/prices/*.csv` เท่านั้น ไม่ดึงข้อมูลใหม่
เพิ่ม `GET /api/indicators/<ticker>` (คำนวณจากราคาเต็มช่วงก่อนเสมอ แล้วค่อย filter วันที่
ทีหลัง กัน SMA50/MACD ของวันแรกๆ ในช่วงที่เลือกดูเป็น NaN เพราะข้อมูลย้อนหลังไม่พอ) หน้า
Dashboard เพิ่ม checkbox 5 ตัว (SMA20/50 เปิดโดย default, Volume/RSI/MACD ปิด) — SMA เป็น
overlay บนกราฟราคาเดิม (yaxis เดียวกัน) ส่วน Volume/RSI/MACD เป็น subplot แยกด้านล่าง
(yaxis2/3/4 คนละ domain, xaxis `matches: 'x'` ให้ zoom/pan sync กัน) คำนวณ domain แบบ
stack จากบนลงล่างให้เติมเต็มพอดี [0,1] ไม่มีช่องว่างเหลือไม่ว่าจะเปิดกี่ panel

**ข้อมูลที่ใช้:** `sandbox/data/prices/NVDA.csv` (Phase 0, 1,255 แถว) ทดสอบคำนวณ indicator
ตรงๆ ผ่าน python ก่อนต่อ API

**ผลลัพธ์:**
- ทดสอบ `indicators.compute_all()` ตรงๆ: RSI อยู่ในช่วง [18.8, 87.5] (valid, ไม่หลุด 0-100),
  NaN count ตรงตาม window (sma20=19, sma50=49, rsi14=14 แถวแรกเป็น NaN ตามที่ควรเป็น, macd=0
  เพราะ EWM ไม่ต้องการ min_periods)
- `GET /api/indicators/NVDA` (เต็มช่วง) → 1,255 วัน, sma20 non-null 1,236, sma50 non-null
  1,206 ตรงกับที่ทดสอบตรงๆ
- `GET /api/indicators/NVDA?start=2022-01-03&end=2022-01-10` → sma50 มีค่าจริงตั้งแต่วันแรก
  ของช่วงที่ขอ (29.44) ไม่ใช่ NaN — ยืนยันว่าคำนวณจากประวัติเต็มก่อน filter ทีหลังทำงานถูก
- `python3 -m sandbox.scripts.smoke_test` ผ่านครบ (ไม่กระทบ)

**มุมมอง/การตีความ:** backend ตรวจสอบได้ครบด้วยตัวเลขจริง ส่วน frontend (multi-panel Plotly
layout, domain stacking math) ตรวจแค่ syntax (`node --check`) + ทวนสูตรคำนวณ domain ด้วยมือ
เอง (nExtra=1,2,3 ทุกกรณีเติมเต็มพอดี [0,1] ไม่มี gap เหลือ) **ยังไม่เคยเห็นกราฟจริงในเบราว์เซอร์
ว่า subplot วางถูกจริง** — ต้องให้ผู้ใช้เปิดดู

**ขั้นต่อไปที่ควรลอง:** เรื่องที่ 2 — CSV bulk upload สำหรับ Events
---

## sandbox_csv_bulk_upload — 2026-09-11 10:40 (+07:00)

**วิธีที่ใช้:** เพิ่ม `sandbox/events_bulk.py` — parse+validate CSV (คอลัมน์: date, ticker,
type, headline; type B/C ไม่สนตัวพิมพ์, ticker ไม่ต้องกรอกถ้า type=C) แยก 2 ฟังก์ชันชัดเจน:
`parse_and_validate()` (validate อย่างเดียว ไม่เขียนอะไร — ใช้ตอน preview) กับ
`commit_valid_rows()` (validate ซ้ำอีกรอบไม่เชื่อ client เก่า แล้ว loop เรียก
`events_store.add_company_event`/`add_macro_event` ทีละแถวเหมือน manual form เดี่ยวทุก
อย่าง — เฉพาะแถว valid เท่านั้น ข้ามแถว error โดยไม่ทำให้ทั้งไฟล์ fail) validation ใช้กฎ
เดียวกับฟอร์มเดี่ยวทุกข้อ (date range, ticker ใน universe, `config.has_company_news()`
disable B) เพิ่ม `POST /api/events/bulk/preview` + `POST /api/events/bulk/commit`
(multipart file upload) หน้า Events เพิ่ม section "Bulk upload (CSV)" — เลือกไฟล์ → Preview
(เห็นตารางทุกแถวพร้อม status OK/ERROR) → Confirm & Run (เขียนจริงเฉพาะแถว valid)

**ข้อมูลที่ใช้:** ไฟล์ CSV ทดสอบเอง 8 แถว ครอบคลุมทุก error case ที่คิดได้ (date นอกช่วง,
ticker ไม่อยู่ใน universe, type ผิด, ticker หายสำหรับ type=B, type ว่าง, type ตัวพิมพ์เล็ก)

**ผลลัพธ์:**
- `POST /api/events/bulk/preview` กับไฟล์ 8 แถว → valid=3, error=5 ตรงตามที่ตั้งใจทุกแถว
  พร้อมข้อความ error เฉพาะเจาะจงต่อแถว (ไม่ใช่ error รวมๆ)
- `POST /api/events/bulk/commit` กับไฟล์เดิม → success=3, failed=5 (row number + เหตุผลตรง
  กับ preview เป๊ะ) `manual_events.csv` มี 7 แถวข้อมูลจริง (1 B-NVDA + 5 C ทุก ticker +
  1 B-TSLA lowercase "b" ก็ผ่าน) ทุกแถว `source=manual`
- ทดสอบ B-disable ผ่าน bulk โดยตรง (ตัด FDX ออกจาก `TICKERS_WITH_COMPANY_NEWS` ชั่วคราว) →
  `parse_and_validate()` reject แถว FDX/B ถูกต้อง พร้อมข้อความอธิบาย
- `smoke_test`, `test_combine` ผ่านครบ ไม่กระทบ

**มุมมอง/การตีความ:** ผ่านครบตามที่ระบุ (preview ก่อน confirm, กฎเดิมทุกข้อ, partial
success ต่อแถวไม่ fail ทั้งไฟล์) decision ที่ตัดสินใจเอง: ใช้ partial-success (ข้ามแถว error
แทนที่จะ reject ทั้งไฟล์ถ้ามีแถวเดียวพัง) เพราะน่าจะมีประโยชน์กว่าเวลา import ไฟล์ใหญ่ที่มี
typo ไม่กี่แถว — ยังไม่เคยเห็น UI (drag file, preview table) จริงในเบราว์เซอร์

**ขั้นต่อไปที่ควรลอง:** เรื่องที่ 3 — rule engine code-generation refactor (rule_v1_logic.py)
แล้วต่อด้วย Strategy engine
---

## sandbox_rule_engine_codegen_v1 — 2026-09-11 11:10 (+07:00)

**วิธีที่ใช้:** แก้ปัญหาที่ผู้ใช้ชี้ชัดว่า rule_v1.json เดิม (Phase 4) เป็น "A+B override C"
ที่ผมเดาขึ้นเองจาก description สั้นๆ — ถามผู้ใช้ตรงๆ ว่า logic จริงคืออะไร ได้คำตอบ: **"A
เป็นหลัก, B/C เป็น veto"** เขียนเป็น `sandbox/rules/rule_v1_logic.py:decide(a,b,c)` ชัดเจน
(A=buy แต่ B หรือ C เป็น negative → veto ลดเป็น hold, A=sell แต่ B หรือ C เป็น positive →
veto ยกเป็น hold, A=hold → hold เสมอ) แล้วเขียน `sandbox/scripts/generate_rule_table.py` ใหม่
(import decide() จาก logic module ที่ระบุผ่าน `--logic`, วน 27 combination export
`rule_v{N}.json` — N parse จากชื่อ module ตรงๆ ด้วย regex `rule_v(\d+)_logic`) **regenerate
`rule_v1.json` ทับของเดิม** (ตั้งใจ — เพราะ v1_logic.py คือต้นทางที่แท้จริงของ v1 เป็นครั้งแรก,
เนื้อหาเดิมมาจาก formula ที่ยืนยันแล้วว่าผิด ไม่มี experiment จริงอ้างอิงเนื้อหาเดิม) ลบ
`generate_rule_v1.py` เดิมทิ้ง (superseded) — `combine()`/หน้า Rules **ไม่แก้ interface เลย**
อ่าน JSON แบบเดิมทุกอย่างตามที่กำหนด "ห้ามทับไฟล์เดิม" ยังคงใช้ได้เต็มที่กับ path การ save
ผ่าน UI (auto-increment ผ่าน `versions.py`) — generator path นี้แยกกันชัดเจน ปลอดภัยเพราะ
ผูกกับชื่อไฟล์ source ที่ commit ไว้ใน git โดยตรง (regenerate จาก source ที่ deterministic
ไม่ใช่การทับ manual edit)

**ข้อมูลที่ใช้:** ไม่มีข้อมูลจริงเกี่ยวข้อง (business logic ที่ผู้ใช้ระบุเอง ไม่ใช่ผลลัพธ์
ที่ validate จากข้อมูล)

**ผลลัพธ์:**
- `generate_rule_table.py --logic rule_v1_logic` → 27 rows, กระจาย buy=4, hold=19, sell=4
  (ตรงกับที่คำนวณด้วยมือไว้ล่วงหน้าเป๊ะทุกตัว)
- Unit test เพิ่มเป็น 13 case (เดิม 8): เทส `decide()` ตรงๆ 8 case (no-veto ทั้ง buy/sell,
  veto จาก B และ C แยกกันทั้ง 2 ทิศทาง, hold ไม่ขึ้นกับ B/C เลย, ครบ 27 combo) + เทส
  `combine()` ผ่านไฟล์จริงอีก 5 case **รวมเทสสำคัญที่สุด: `rule_v1.json` ทุกแถวต้องตรงกับผล
  `decide()` เป๊ะ** (กัน JSON กับ source โค้ดเพี้ยนกัน) — ผ่านครบ 13/13
- error handling: `--logic` ชื่อผิด pattern → error ชัดเจนไม่ crash, module ไม่มี `decide()`
  → error ชัดเจน (ทดสอบสร้าง `rule_v99_logic.py` เปล่าๆ จริง แล้วลบทิ้งหลังทดสอบ)
- `/rules` page แสดง v1 พร้อม description ใหม่ "generated from
  sandbox/rules/rule_v1_logic.py:decide()" ถูกต้อง, 27 แถวครบ, `smoke_test` ไม่กระทบ

**มุมมอง/การตีความ:** นี่คือตัวอย่างที่ดีของทำไมต้องถามแทนเดา — logic ใหม่ (A เป็น veto
gate) ให้ผลต่างจาก logic เดิม (A+B weighted) มาก: distribution เปลี่ยนจาก buy=12/hold=3/
sell=12 เป็น buy=4/hold=19/sell=4 — ระบบเดิมแทบไม่เคย hold เลย (hold แค่ 3/27) ระบบใหม่
hold เป็นค่า default เกือบทุกกรณี (19/27) สะท้อน philosophy ที่ต่างกันโดยสิ้นเชิง (weighted
consensus vs. conservative-veto) ถ้าเดาแล้วใช้ logic ผิดต่อไปจะทำให้ทุก experiment/strategy
ที่พึ่งพา rule engine ผิดตามไปด้วย

**ขั้นต่อไปที่ควรลอง:** Strategy engine (base.py, strategy_v1.py, engine/simulate.py, UI
ใหม่) — ใช้ C signal ตรงๆ ไม่ผ่าน rule engine (ตามตัวอย่างที่ผู้ใช้ให้มา)
---

## sandbox_strategy_engine — 2026-09-11 11:45 (+07:00)

**วิธีที่ใช้:** เพิ่ม Strategy engine เต็มระบบ แยกจาก rule engine (Phase 4) โดยสิ้นเชิง:
- `sandbox/strategy/base.py` — `Strategy` (interface, `on_day(date, signals_per_ticker,
  portfolio_state) -> actions`) + `PortfolioState` (dataclass: cash, holdings,
  last_sell_price — ตามที่กำหนดเป๊ะ)
- `sandbox/strategy/strategy_v1.py` — implement ตามตัวอย่าง: C=negative → sell ทั้งหมด +
  จำราคาขาย, ราคาตก -20% จากจุดขายเดิม → ซื้อคืน (หารเงินเท่ากันถ้าหลาย ticker เข้าเงื่อนไข
  พร้อมกัน, เคลียร์ last_sell_price กันซื้อคืนซ้ำจุดเดิม), cash ที่เหลือ → DCA เข้า
  ticker ที่ C=positive วันนั้น (หารเท่ากัน) — รายละเอียดที่ตัวอย่างไม่ระบุ (ลำดับ
  sell→buyback→DCA, วิธีหารเงินเมื่อมีหลาย ticker) documented ไว้ในไฟล์ตรงๆ
- `sandbox/engine/simulate.py` — `run_simulation()` วน day-by-day (ใช้ trading date จริง
  จากไฟล์ราคา) ต่อวัน: a จาก `model_a.predict()` เสมอ, b จาก manual event ตรงวันนั้นเป๊ะ, c
  จาก manual + real historical (477 ข่าว, เหมือนที่ Dashboard ใช้ — manual ชนะถ้าชนวันเดียวกัน)
  **ไม่ forward-fill สัญญาณข้ามวัน** (ห้ามเดา) trade log เต็ม + portfolio value รายวัน
- หน้า Strategies ใหม่ (nav bar เพิ่ม tab ที่ 5) — banner บังคับ (ข้อความตรงตามที่กำหนดเป๊ะ):
  "ผลจำลองนี้ใช้ signal จาก STUB — ทดสอบว่า logic ทำงานถูก ไม่ใช่ทดสอบว่ากลยุทธ์กำไรจริง"
  ฟอร์ม (strategy select, ticker checkbox, date range, initial cash, notes) → trade log
  table + Plotly line chart มูลค่าพอร์ต
- `sandbox/experiments_db.py` เพิ่ม `run_strategy_experiment()` — เก็บลงตาราง `experiments`
  เดียวกับ Phase 5 เป๊ะ (schema ไม่เปลี่ยน) ผูก `rule_version = "strategy:<name>"` เป็นตัวแยก
  ประเภทตอนอ่านกลับ (`is_strategy` flag) `diff_experiments()` reject การ diff strategy run
  (raise ValueError ชัดเจน — trade log เทียบแบบ (ticker,date)→decision ไม่ได้) UI (หน้า
  Experiments) disable diff checkbox ของ strategy row ไปเลยไม่ให้เลือกผิดตั้งแต่แรก

**บั๊กที่เจอแล้วแก้ระหว่างทดสอบ:** `load_strategy()` เดิมปล่อยให้
`ModuleNotFoundError` หลุดออกไปดิบๆ เป็น Flask debug 500 traceback เต็มหน้า (ไม่ใช่ JSON
error สะอาดๆ) เวลาระบุ strategy ที่ไม่มีจริง — เจอจาก curl ทดสอบจริง (`strategy_v99`) ไม่ใช่
แค่ตรวจโค้ด แก้เป็น catch `ModuleNotFoundError` เทียบ `e.name` ให้ชัดว่าเป็น module ที่เรา
import เอง (ไม่ใช่ import ที่พังข้างในไฟล์ strategy อื่น) แล้วแปลงเป็น `FileNotFoundError`
พร้อม list strategy ที่มีจริงให้

**ข้อมูลที่ใช้:** ราคาจาก `sandbox/data/prices/*.csv` (Phase 0), real historical macro
data 477 ข่าว (เชื่อมไว้แล้วจาก fix ก่อนหน้า) ทดสอบรันจริง: 1 ปี (2024, 5 ticker,
$100k) และเต็ม 5 ปี (2021-09-10..2026-09-10)

**ผลลัพธ์ (ทดสอบจริงทุกข้อ):**
- รัน 1 ปี (2024, ticker ครบ 5 ตัว, $100,000) → final_value=$176,508.91, 21 trades
  (mix sell/dca ตามที่คาด, first day value = initial cash เป๊ะ, ticker_set แคบลง (2 ตัว) ให้
  ผลต่างกันจริง — final_value=$100,764 สมเหตุสมผลกับ universe เล็กลง/สั้นลง)
- รันเต็ม 5 ปี → 91 trades, **8 buyback event เกิดขึ้นจริง** ทุกอันราคาตก ≥20% จากจุดขายจริง
  (เช่น META -38.9%, NVDA -45.5%) ยืนยันว่า threshold -20% ทำงานถูกต้องด้วยข้อมูลราคาจริง
- `POST /api/strategies/run` → persist ลง `experiments.db` สำเร็จ, `GET
  /api/strategies/runs` เห็น run ที่เพิ่ง save, หน้า `/strategies` render ตาราง saved run
  ถูกต้อง
- diff guard: สร้าง 1 rule-lookup + 1 strategy experiment แล้วลอง diff คู่กัน →
  `ValueError` ชัดเจน ไม่ crash, ตรวจ UI แล้วว่า checkbox ของ strategy row มี `disabled`
  attribute จริงในหน้า `/experiments`
- error path ครบ: unknown strategy (แก้บั๊กแล้ว → 400 JSON สะอาด), ชื่อ pattern ผิด, cash
  ติดลบ, start>end → ทุกกรณี 400 พร้อมข้อความชัดเจน ไม่ใช่ 500
- `smoke_test`, `test_combine` (13 case), `node --check` ผ่านหมด ไม่กระทบ

**มุมมอง/การตีความ:** Strategy engine ทำงานจบ end-to-end จริงด้วยข้อมูลราคา+ข่าวจริง (ไม่ใช่
mock) — buyback -20% ที่ trigger ได้จริง 8 ครั้งใน 5 ปี พิสูจน์ว่า logic ตอบสนองข้อมูลจริง
ถูกต้อง ไม่ใช่แค่ผ่าน unit test สังเคราะห์ จุดที่ยังไม่ครบ: ยังไม่ได้เห็น UI จริง (form,
trade log table, portfolio chart) ในเบราว์เซอร์

**ขั้นต่อไปที่ควรลอง:** ผู้ใช้เปิด browser ทดสอบทั้ง 4 เรื่องที่ทำวันนี้ (indicators,
bulk upload, rule engine ใหม่, strategy engine) ด้วยตาจริง
---

## sandbox_rule_logic_code_editor — 2026-09-11 12:15 (+07:00)

**วิธีที่ใช้:** เพิ่ม `sandbox/rules/codegen.py` — backend สำหรับ code editor ในหน้า Rules:
- `validate_source(source)` — compile + exec ใน namespace แยก เช็คว่ามี `decide()` จริง เรียก
  ได้จริง (ทดสอบด้วย `decide("buy","positive","positive")`) และ return ค่าที่ใช้ได้ ไม่เขียน
  ไฟล์ใดๆ คืน error message ระบุเลขบรรทัดถ้าเป็น `SyntaxError`
- `save_new_version_from_source(source, description)` — validate ซ้ำ (ไม่เชื่อ client) แล้ว
  เขียน `rule_v{next}_logic.py` **ไฟล์ใหม่เสมอ** (next = max version ที่มีอยู่ + 1, auto-
  increment เหมือน `versions.py` — คนละกลไกกับ CLI `generate_rule_table.py` ที่ regenerate
  ทับไฟล์ paired ได้) รัน `build_table()` (import จาก `generate_rule_table.py` เดิม ไม่เขียน
  logic ซ้ำ) generate `rule_v{next}.json` คู่กัน คืน distribution diff เทียบ version ก่อนหน้า
  (before/after count ของ buy/hold/sell + changed_rows/27 + %)
- หน้า Rules เพิ่ม panel "Edit rule logic" — dropdown เลือก version logic ที่มีจริงมาเป็นจุด
  เริ่มต้น, textarea (monospace), ปุ่ม Validate (ไม่ save) + ปุ่ม Save as new version &
  regenerate (แสดง distribution diff ทันทีหลัง save)
- `POST /api/rules/logic/validate`, `POST /api/rules/logic/save`, `GET /api/rules/logic`

**⚠️ Security note (ต้องรู้):** ฟีเจอร์นี้ `exec()` python source code ที่ส่งมาจาก browser
ตรงๆ — เป็น arbitrary code execution โดยเจตนา (ไม่มีทางเลี่ยงได้ถ้าจะให้ "แก้โค้ดในเบราว์เซอร์
แล้วรันได้เลย" ตามที่ขอ) ยอมรับได้เพราะรันบน localhost คนเดียวใช้ ไม่มี auth — ห้ามเปิดเครื่อง
ให้เข้าถึงจากเครือข่ายอื่น (0.0.0.0, ngrok, ฯลฯ) ตอนใช้ฟีเจอร์นี้ ระบุคำเตือนนี้ไว้ทั้งใน
docstring ของ `codegen.py` และข้อความในหน้า UI เอง

**ข้อมูลที่ใช้:** ไม่มีข้อมูลจริงเกี่ยวข้อง (เป็น dev tool)

**ผลลัพธ์ (ทดสอบผ่าน HTTP API จริง ไม่ใช่แค่เรียก function ตรงๆ):**
- `python3 -c` ทดสอบ `validate_source()` 5 case: syntax ถูก (valid=True), syntax ผิด (ชี้
  บรรทัดถูก), ไม่มี `decide()`, `decide()` raise exception, `decide()` return ค่านอก
  buy/hold/sell — ทุกกรณีจับ error ได้ถูกต้องตามที่ตั้งใจ
- `POST /api/rules/logic/save` ผ่าน HTTP จริง ด้วย logic ใหม่ (majority-vote formula ต่างจาก
  v1's veto logic โดยสิ้นเชิง) → สร้าง `rule_v2.json` + `rule_v2_logic.py` จริง, MD5 ของ
  `rule_v1.json` **เหมือนเดิมทุกตัวอักษร** ก่อน/หลัง (`e84e5a8ac5006f94af7e9327feff28d6`)
  distribution diff ถูกต้อง: before(v1)={buy:4,hold:19,sell:4} → after(v2)=
  {buy:10,hold:7,sell:10}, changed_rows=12/27 (44.4%) — ตรงกับที่คำนวณตรงๆ ด้วยมือ
- หน้า `/rules` แสดง version picker อัปเดตมี v2 เพิ่มมาจริงหลัง save (grep เจอ `version=2`)
- ลบ `rule_v2.json`/`rule_v2_logic.py` (test artifact) ทิ้งหลังทดสอบ เหลือแค่ v1 ใน repo

**บั๊ก/ของค้างที่เจอระหว่างทำ (ไม่เกี่ยวกับ feature นี้):** พบไฟล์ `rule_v2.json` ค้างอยู่แบบ
untracked จากการทดสอบ turn ก่อนหน้าที่ไม่ได้ลบให้สะอาด (`git status` ยืนยันว่าไม่เคย commit)
ทำให้การทดสอบ distribution diff รอบแรกเทียบกับ baseline ผิด (เทียบกับ v2 เก่าที่ไม่รู้ที่มา
แทนที่จะเป็น v1) แก้โดยลบทิ้งแล้วทดสอบใหม่จาก baseline ที่ถูกต้อง — เป็นบทเรียนเรื่อง cleanup
discipline ระหว่าง test iteration ในหลาย turn ต่อเนื่องกัน

**มุมมอง/การตีความ:** ฟีเจอร์นี้ทำให้ "ลอง logic ใหม่" เร็วขึ้นมากจริง (พิมพ์โค้ดในเบราว์เซอร์
→ validate → save → เห็น distribution เปลี่ยนทันที ไม่ต้อง SSH เข้าเครื่อง ไม่ต้องรัน CLI
เอง) แต่ต้องแลกกับ security surface ที่กว้างขึ้น (arbitrary code exec) ซึ่งยอมรับได้เฉพาะ
บริบท local dev sandbox เท่านั้น — ต้องเตือนผู้ใช้ให้ชัดถ้าจะ deploy ที่ไหนที่ไม่ใช่ localhost

**ขั้นต่อไปที่ควรลอง:** เรื่องที่ 2/3 (ต่อจากนี้ในบันทึกถัดไป)
---

## sandbox_dashboard_marker_toggle — 2026-09-11 12:20 (+07:00)

**วิธีที่ใช้:** เพิ่ม checkbox 2 อันใน Dashboard sidebar: "Show macro (C) events" / "Show
company (B) events" (default เปิดทั้งคู่) แก้ `render()` ใน `main.js` ให้เช็ค checkbox ก่อน
push trace/shape ของ C (triangle marker + dashed line) และ B (circle marker) เข้า Plotly
figure — ผูก `change` event เข้ากับ `render()` เดียวกับที่ indicator checkbox ใช้อยู่แล้ว
(pattern เดิมจากงานก่อนหน้า ไม่ต้องเขียนกลไกใหม่)

**ข้อมูลที่ใช้:** ไม่มีข้อมูลจริงเกี่ยวข้อง (UI toggle เฉยๆ)

**ผลลัพธ์:** `curl` ยืนยัน checkbox `id="show-c-events"`/`id="show-b-events"` render บนหน้า
Dashboard จริง, `node --check` ผ่าน — ตรรกะ conditional (skip push trace ถ้า unchecked) ตรวจ
ด้วยการอ่านโค้ดเอง **ยังไม่เคยเห็นด้วยตาว่า marker หายจากกราฟจริงตอนคลิก** เพราะไม่มี browser
ในสภาพแวดล้อมนี้

**มุมมอง/การตีความ:** ฟีเจอร์เล็ก ทำตาม pattern ที่มีอยู่แล้ว (indicator toggle) เสี่ยงต่ำ

**ขั้นต่อไปที่ควรลอง:** เรื่องที่ 3 — metrics
---

## sandbox_strategy_metrics — 2026-09-11 12:30 (+07:00)

**วิธีที่ใช้:** เพิ่ม `sandbox/analytics/metrics.py`:
- `compute_max_drawdown_pct()` — running peak เทียบกับมูลค่าปัจจุบันทุกวัน (ไม่ใช่เทียบกับ
  initial cash เฉยๆ ซึ่งจะผิด ถ้าพอร์ตเคยขึ้นไปสูงกว่าแล้วค่อยร่วง)
- `compute_win_rate()` — running weighted-average cost basis ต่อ ticker (ไม่ใช่ FIFO lot)
  ใช้ได้ตรงกับ strategy_v1 เพราะ sell ขายทั้งหมดทุกครั้ง (ไม่มี partial sell) — sell ที่ราคา
  > average cost = win, reset cost basis เป็น 0 หลัง sell หมด
- `compute_buy_and_hold()` — benchmark: ซื้อ ticker_set เท่าๆ กันที่วันแรกของช่วง ถือเฉยๆ
  ตลอด คำนวณ metric ชุดเดียวกันเพื่อเทียบตรงๆ
- ต่อเข้า `sandbox/engine/simulate.py` — `run_simulation()` return เพิ่ม `metrics` +
  `benchmark` (มี `portfolio_value_series` ของ benchmark ด้วย สำหรับวาดกราฟเทียบ) เก็บลง
  `experiments_db` อัตโนมัติ (อยู่ใน `decisions_json` เดิมอยู่แล้ว ไม่ต้อง migrate schema)
- หน้า Strategies: banner เพิ่มบรรทัดชัดเจนว่า metric ทดสอบโค้ดถูก ไม่ใช่กำไรจริง, เพิ่มตาราง
  metrics (strategy vs benchmark), กราฟ portfolio value ใส่เส้น benchmark เพิ่ม (เส้นประ
  เหลือง), ตาราง saved runs เพิ่มคอลัมน์ return%/drawdown%/win rate
- หน้า Experiments: ตาราง runs เพิ่มคอลัมน์ metric เดียวกัน (ว่างสำหรับ rule-lookup row) ให้
  เทียบข้าม run ได้ตรงๆ ตามที่ขอ

**ข้อมูลที่ใช้:** ราคาจริง 5 ปี (`sandbox/data/prices/*.csv`) + real historical macro data
(477 ข่าว, เชื่อมไว้จาก fix ก่อนหน้า)

**ผลลัพธ์ (ทดสอบจริงทุกจุด):**
- รันเต็ม 5 ปี (5 ticker, $100k): strategy total_return=302.69%, max_drawdown=51.38%,
  win_rate=53.66% (41 closed trades จาก 91 trade รวม) — **max drawdown ตรวจสอบด้วยมือแยก
  ต่างหาก** (recompute จาก portfolio_value_series ตรงๆ) ได้ 51.38% เป๊ะ ตรงกับที่ engine
  คำนวณ, เกิดวันที่ 2023-01-03 ตรงกัน
- benchmark (buy-and-hold ticker เดียวกัน ช่วงเดียวกัน): return=218.29%, drawdown=47.04% —
  strategy ทำได้ดีกว่า benchmark ทั้ง return (สูงกว่า) แต่ drawdown ก็สูงกว่าด้วย (trade-off
  ที่สมเหตุสมผล ไม่ใช่ตัวเลขที่ดูผิดปกติ)
- `POST /api/strategies/run` ผ่าน HTTP จริง → metrics/benchmark ตรงกับที่ทดสอบตรงๆ ทุกตัว
- หน้า `/strategies` และ `/experiments` แสดงตัวเลข 302.69% ตรงกันทั้งคู่ (grep ยืนยัน) banner
  มีข้อความ "โค้ดคำนวณถูก" ตามที่กำหนด

**มุมมอง/การตีความ:** ตัวเลขที่ได้ดูสมเหตุสมผลภายในตัวเอง (strategy ให้ return สูงกว่าแต่
drawdown สูงกว่าด้วย ซึ่งเป็น trade-off ปกติของการเทรดบ่อยกว่า) แต่ต้องย้ำอีกครั้งว่านี่คือ
ผลจาก **สัญญาณ stub deterministic** ไม่ใช่สัญญาณจากโมเดลจริง — ตัวเลข 302% ไม่ได้แปลว่า
strategy_v1 จะทำกำไรขนาดนี้จริงเมื่อ Model A/B/C เป็นของจริง (ตามที่ banner ระบุไว้)

**ขั้นต่อไปที่ควรลอง:** ผู้ใช้เปิด browser ทดสอบทั้ง 3 เรื่องด้วยตาจริง โดยเฉพาะ code editor
(เรื่องที่ 1) ที่มี UX ซับซ้อนกว่าฟีเจอร์อื่น (dropdown โหลด source, validate, save)
---

## sector_news_collection_day1 — 2026-09-12 (+07:00)

**วิธีที่ใช้:** เริ่มงานเก็บข่าว sector-tagged สำหรับปรับปรุง Model C (เสริม ไม่แทน
FOMC/Beige Book เดิม) ตามคำสั่ง unattended หลายวัน — ก่อนเขียน scraper ตัวไหนเลย เปิดหน้า
Terms of Service จริงของ Group B/C ทั้ง 5 เว็บ (ไม่ใช่แค่ robots.txt ตามที่ผู้ใช้ย้ำกลางทาง)
ผลคือตัดทั้ง Group B/C ออกจาก automated collection (รายละเอียดเต็ม + หลักฐานทุกเว็บอยู่ใน
`sandbox/data/DECISIONS_NEEDED.md`) แล้วพบว่า Finnhub `company-news` query ด้วย sector ETF
ticker ตรงๆ ครอบคลุมเป้าหมายของ Group B ได้อยู่แล้วโดยไม่ต้อง scrape

โครงสร้าง: `sandbox/scripts/_sector_news_common.py` (shared: resumable log, index writer, ticker
→ GICS sector → ETF map จาก S&P500 ปัจจุบัน ผ่าน Wikipedia, reuse `fetch_sp500_table()` จาก
Phase 0), `collect_finnhub.py`, `collect_alpha_vantage.py` — raw content ไปที่
`sandbox/data/sector_news_raw/` (`.gitignore` ทั้งโฟลเดอร์) metadata (source, item_id, date,
sector_etf, url, sentiment_score, word_count, raw_path) ไปที่
`sandbox/data/sector_news_processed/index.csv` (commit ได้)

**ข้อมูลที่ใช้:** เรียก API จริงทั้ง Finnhub และ Alpha Vantage (มี key อยู่แล้วใน `.env`)
ไม่ใช่ mock — verify field name/behavior ด้วยการเรียกจริงก่อนเขียน script เสมอ (พบว่า spec
เดิมผิดไป 1 จุด: Finnhub `news-sentiment` endpoint คืน 403 บน free tier ทั้งที่ spec บอกว่าใช้
ได้)

**ผลลัพธ์ (ตัวเลขจริงทั้งหมด):**
- **Finnhub**: 4,512 รายการ ครบทั้ง 11 sector ETF ย้อนหลัง 2025-10-01 ถึง 2026-09-11 (~11.5
  เดือน) — resumability ทดสอบแล้วจริง (รันซ้ำ skip ของเดิมหมด 0 API call เพิ่ม)
- **Alpha Vantage**: 2,664 รายการ — sector derive จาก ticker ที่บทความพูดถึงจริง (join กับ
  S&P500 ticker→GICS sector, 503 ticker) ไม่ใช่ topic label ตรงๆ (แม่นกว่า, ครอบคลุมครบ 11
  sector แม้ query แค่ 7 topic — เห็นได้จาก XLC/XLU/XLB/XLRE ที่ไม่มี topic ตรงตัวแต่ยังได้
  รายการจริงจาก ticker mention) 256/1108 บทความ (23%) แตะมากกว่า 1 sector, sentiment_score
  อยู่ในช่วง -0.84 ถึง 0.89 (สมเหตุสมผล)
- **รวม index.csv**: 7,176 แถว metadata — ตรวจแล้วด้วย `git status` ว่า `sector_news_raw/`
  ไม่หลุดเข้า git เลย (มี raw file จริง 1,965 ไฟล์บน disk แต่ git มองไม่เห็น)

**บั๊กจริงที่เจอระหว่างทำ (รายละเอียดเต็มใน DECISIONS_NEEDED.md):**
1. Finnhub: query ช่วงวันที่กว้าง (8.5 เดือนทีเดียว) cap ผลลัพธ์แล้ว bias ไปทางข่าวล่าสุด
   (ข่าวเก่ากว่าในช่วงเดียวกันหายไปเงียบๆ) — แก้โดย query เป็น chunk รายเดือนเสมอ
2. Alpha Vantage: (a) `time_to` ต้องมี `time_from` คู่กันเสมอ ไม่งั้น API ตอบ
   "Invalid inputs" (b) cursor ไม่ขยับเพราะ `time_published` (มีวินาที) parse ผิด format
   (ไม่มีวินาที) — `except ValueError` เดิมจับเงียบๆ ทำให้เกือบวน loop ไม่รู้จบด้วย cursor
   เดิม (c) สงสัยว่า free tier คืน feed ว่างเฉยๆ ตอนติด rate limit (ไม่ error ชัดเจน) — แก้
   โดยเลิก mark-exhausted-ถาวรจาก response เดียว เปลี่ยนเป็น retry ทุกวันแทน

**มุมมอง/การตีความ:** วันแรกได้ผลดีกว่าที่ spec เดิมคาดไว้มาก (spec คิดว่า Finnhub ต้อง query
ทีละบริษัทแล้ว group เอง, ประเมิน sector ไม่ตรง GICS 100% จาก topic — สุดท้ายได้ทั้งสอง
ปัญหาแก้ไปพร้อมกัน: Finnhub ใช้ ETF ticker ตรงๆ ได้เลย, Alpha Vantage ใช้ ticker mention
derive sector แม่นกว่า topic) จุดที่ต้อง revisit: sentiment_score ของฝั่ง Finnhub ว่างทั้งหมด
(ไม่มี scoring endpoint ให้ใช้บน free tier) ต้องตัดสินใจว่าจะรัน FinBERT ให้ทีหลังไหม —
บันทึกไว้ใน DECISIONS_NEEDED.md แล้ว

**ขั้นต่อไปที่ควรลอง:** (1) พรุ่งนี้ (quota ใหม่) รัน `collect_alpha_vantage.py` ต่อ — cursor
เดินต่อจากเดิมอัตโนมัติ (2) ตัดสินใจเรื่อง Benzinga key + Group C manual collection + FinBERT
scoring ของ Finnhub items (ทั้งหมดอยู่ใน DECISIONS_NEEDED.md รอ input)
---

## sector_news_rule_based_filter — 2026-09-12 (+07:00)

**วิธีที่ใช้:** เขียน `sandbox/scripts/filter_relevant_news.py` — rule-based เท่านั้น (ไม่ใช้
LLM) tag 3 อย่างลงคอลัมน์ใหม่ใน `index.csv` เดิม (ไม่ลบ/ไม่ทับข้อมูลเดิม, รันซ้ำได้ปลอดภัย):
`is_company_level` (นับ distinct company mention — AV ใช้ `ticker_sentiment` ตรงๆ, Finnhub
ใช้ regex ticker pattern + จับคู่ชื่อบริษัท S&P500 กับข้อความ เพราะไม่มี structured field),
`is_weak_signal` (ไม่มี sector keyword ที่กำหนดเองเลยสักคำ, keyword list ต่อ 11 sector เขียน
ไว้ในไฟล์สคริปต์ตรงๆ), `is_mistagged` (บริษัทที่ระบุได้จริงในเนื้อหา sector ไม่ตรงกับที่
index.csv tag ไว้เลยสักตัว) รวมเป็นคอลัมน์ `scope` (join tag ที่ตรงทั้งหมด หรือ "clean")

**ข้อมูลที่ใช้:** `sandbox/data/sector_news_processed/index.csv` ทั้งหมด (7,176 แถวจริงจาก
Finnhub+Alpha Vantage วันก่อน) join กับ raw content จาก `sector_news_raw/` (เปิดแต่ละไฟล์
ครั้งเดียว ไม่เปิดซ้ำต่อแถว — 1,965 raw file)

**ผลลัพธ์ (ตัวเลขจริงจากการรัน ไม่ใช่ประมาณ):**
- scope breakdown: weak_signal 40.3%, clean 26.0%, company_level+weak_signal 15.9%,
  company_level เดี่ยว 10.1%, company_level+weak_signal+mistagged 4.5%,
  company_level+mistagged 2.6%, weak_signal+mistagged 0.3%, mistagged เดี่ยว 0.2%
- per-flag (นับซ้ำได้): is_company_level 33.2% (2,381), is_weak_signal 61.0% (4,379),
  is_mistagged 7.7% (552)
- **แยกตาม source — พบสิ่งที่ยืนยัน internal consistency ของงานเมื่อวาน**:
  Alpha Vantage `is_mistagged = 0.0%` (0/2,664) พอดี — สมเหตุสมผล เพราะ sector tag ของ AV
  ทุกแถว derive มาจาก ticker mention ในบทความนั้นเองตั้งแต่ตอน collect (คำนวณจาก source
  เดียวกัน เปรียบเทียบกับตัวเอง ต้องตรงเสมอ ถ้าไม่ตรงคือ Bug) — เป็น sanity check ที่ผ่านจริง
  ไม่ใช่การเดาว่าควรจะเป็น 0%
  Finnhub `is_mistagged = 12.2%` (552/4,512) — ตัวเลขจริงที่แสดงว่า query
  `company-news?symbol={ETF}` มีข่าวที่จริงๆ พูดถึงบริษัทนอก sector นั้นปนอยู่จริงประมาณ 1
  ใน 8 (ตรงกับที่ผู้ใช้กังวลไว้ตั้งแต่ต้น)

**Limitation ที่เจอจริงจากการ spot-check (ไม่ใช่แค่คาดเดา):** สุ่มดู mistagged row 2 อัน
พบว่าเป็นข่าว "Sector Update: Tech Stocks Gain..." (market wrap ทั่วไป พูดถึง XLK ETF เอง)
ที่ mention คำว่า "State Street" (ชื่อบริษัทผู้ออก SPDR ETF ในชื่อเต็ม "State Street
Technology Select Sector SPDR ETF") — ระบบจับ "State Street" เป็นบริษัท S&P500 จริง (STT,
sector จริง = XLF) เลย flag mistagged ทั้งที่บทความไม่ได้พูดถึง State Street Corp ในฐานะ
ประเด็นข่าวจริง เป็นข้อจำกัดจริงของ name-matching แบบง่าย (จับชื่อบริษัทที่โผล่มาในบริบท
โครงสร้าง เช่น ชื่อผู้ออก ETF ไม่ใช่แค่ noise เดา — เป็น mechanism ที่ระบุได้ชัดเจน)

**มุมมอง/การตีความ:** ตัวเลขทั้งหมดเป็นค่าที่คำนวณได้จริง ไม่ได้เดา — แต่ยังไม่ตัดสินใจ
threshold คัดออกตามที่สั่งไว้ (รอ user ตัดสินใจจากตัวเลขจริงชุดนี้) weak_signal สูงถึง 61%
น่าจะสะท้อนสองสาเหตุผสมกัน: (1) keyword list ที่กำหนดเองอาจแคบไป (2) ข่าวเฉพาะบริษัทจำนวนมาก
ไม่ได้ใช้คำ sector-level ตรงๆ (เช่นข่าว "Linde stock" ไม่มีคำว่า "chemical"/"materials" เลย
แม้จะเป็นข่าว sector XLB จริง) — สังเกตว่า company_level กับ weak_signal เกิดร่วมกันบ่อย
(15.9%+4.5%=20.4%) สนับสนุนสมมติฐานข้อ 2

**ขั้นต่อไปที่ควรลอง:** รอผู้ใช้ตัดสินใจ threshold (เช่น ตัด mistagged ทิ้ง, หรือปรับ keyword
list ให้กว้างขึ้นก่อนตัดสินใจเรื่อง weak_signal)
---

---
## fix_sector_tags — แก้ sector_etf ของข่าว mistagged ด้วย Finnhub company-profile2 — 2026-09-12 17:46

**วิธีที่ใช้:** เขียน `sandbox/scripts/fix_sector_tags.py` — สำหรับแถวที่
`filter_relevant_news.py` ติด `is_mistagged=True` และ detect ได้บริษัทเดียวไม่กำกวม ยิง
Finnhub `company-profile2?symbol={ticker}` เอา field `finnhubIndustry` มา map เข้า 1 ใน 11
sector ETF ด้วย keyword list ที่กำหนดเอง (rule-based ไม่ใช่ LLM) แล้วเขียนทับ `sector_etf`
พร้อมเก็บค่าเดิมไว้ในคอลัมน์ใหม่ `original_sector_etf` (ไม่ลบทิ้ง) ตาม "ห้ามเดา" — ข้ามไม่แก้
แถวที่ (1) detect ได้มากกว่า 1 บริษัท (2) หา profile ไม่เจอ (3) industry map เข้า sector
ไม่ได้ script ออกแบบให้รันซ้ำได้ปลอดภัย (idempotent — แถวที่แก้แล้วจะไม่ใช่ mistagged อีก)

ระหว่างพัฒนาเจอบั๊กจริง 2 ตัวจากการ spot-check ผลลัพธ์ (ไม่ใช่เดา) ต้องแก้ก่อนตัวเลขจะเชื่อถือได้:

1. **False-positive จากชื่อทั่วไป/โครงสร้าง**: รันรอบแรกดิบบน 552 แถว mistagged ได้ "503
   fixed" (91.1%) แต่ตรวจ raw text จริงพบว่าส่วนใหญ่ผิด — "Nasdaq" (ใช้เป็นชื่อดัชนี/ตลาดหุ้น
   ทั่วไปในข่าว "Stock Market Today") ไป match ticker NDAQ, "State Street" (ชื่อผู้ออก SPDR
   ETF ในชื่อเต็ม เช่น "State Street Technology Select Sector SPDR Fund") ไป match STT — นับ
   ตัวอย่าง 173/503 เป็น sponsor-name pattern ยืนยันชัด ตรวจเพิ่มพบ TGT (6/6 ตัวอย่างเป็นคำว่า
   "price target" ไม่ใช่ Target Corp), SPGI (อ้างเป็นแหล่งข้อมูล PMI), MSCI (อ้างเป็น index
   provider), BLK (อ้างเป็น fund manager ของ closed-end fund) เป็น false positive เหมือนกัน —
   revert ข้อมูลกลับ เพิ่ม `GENERIC_NAME_COLLISION_TICKERS = {NDAQ, STT, TGT, SPGI, MSCI, BLK}`
   ใน `filter_relevant_news.py` (พร้อม comment อ้างอิงหลักฐานที่ตรวจจริง) แล้วรัน
   `filter_relevant_news.py` ใหม่ — mistagged ลดจาก 552 (7.7%) เหลือ 167 (2.3%)

2. **Substring match bug ใน industry→ETF mapping**: รันรอบสองบน 167 แถว พบ MRNA (Moderna,
   `finnhubIndustry="Biotechnology"`) ไม่ถูกแก้ทั้งที่ควรแก้ (XLK -> XLK เฉยๆ) — root cause คือ
   `map_industry_to_etf()` ใช้ `kw in industry_lower` (substring) และคำ "technology" (keyword
   กลุ่ม XLK ซึ่งมาก่อนในลิสต์) เป็น substring ของ "biotechnology" (ควรไป XLV) — revert ข้อมูล
   แล้วเปลี่ยนเป็น `re.search(r"\bkw\b", ...)` (word-boundary) ทั้งหมด ยืนยันด้วย
   `re.search(r'\btechnology\b','biotechnology')` -> False,
   `re.search(r'\bbiotechnology\b','biotechnology')` -> True ก่อนรันจริง

**ข้อมูลที่ใช้:** `sandbox/data/sector_news_processed/index.csv` (7,176 แถว, คอลัมน์ tag จาก
`filter_relevant_news.py`) เฉพาะแถว `is_mistagged=True` (167 แถวหลังแก้บั๊ก 1 — ทั้งหมดเป็น
source=finnhub เพราะ alpha_vantage mistagged=0% อยู่แล้ว), เรียก Finnhub `company-profile2`
จริง (unique ticker ที่ยิง = 23 ตัว, rate-limit 1.1s/call)

**ผลลัพธ์:** จาก 167 แถว mistagged (ตัวเลขสุดท้ายหลังแก้บั๊กทั้ง 2 ตัว, รันสะสม 2 รอบย่อยแบบ
resumable):
- แก้ sector สำเร็จ: **144 แถว (86.2%)**
- ข้าม — ambiguous (>1 บริษัท): 20 แถว (12.0%)
- ข้าม — industry map เข้า sector ไม่ได้: 3 แถว (1.8%) — ทั้งหมดคือ `finnhubIndustry="Consumer
  products"` (GRMN, LEN → ควรเป็น XLY; PG → ควรเป็น XLP) ตรวจแล้วเป็น ambiguous จริง ไม่ใช่
  keyword gap ที่ควรเติม — ตั้งใจไม่ map
- ข้าม — หา Finnhub profile ไม่เจอ: **0 แถว (0.0%)**
- ไฟล์สุดท้าย: 7,176 แถวครบ (ไม่หาย/ไม่เกิน), เพิ่มคอลัมน์ `original_sector_etf` เก็บค่า sector
  เดิมไว้ครบทุกแถวที่แก้ (ยืนยันด้วยการอ่านไฟล์จริงหลังรัน ไม่ใช่เดา)

**มุมมอง/การตีความ:** ตัวเลข 144/167 (86.2%) แก้ได้สูง และ 0 แถวหา profile ไม่เจอ แปลว่า
Finnhub ให้ profile ครบสำหรับทุก ticker ที่ detect ได้จริงใน sample นี้ — ปัญหาคอขวดจริงคือ
ambiguous (20 แถว, มักเป็นข่าวเปรียบเทียบหลายบริษัทพร้อมกัน) กับ industry ที่กำกวมจริง (3
แถว, "Consumer products" คร่อม 2 sector) ไม่ใช่ data availability บั๊กทั้ง 2 ตัวที่เจอ
(generic-name collision, substring match) ชี้ว่า rule-based matching แบบง่ายมีความเสี่ยง false
positive/false negative สูงถ้าไม่ตรวจ raw text จริงประกอบ — การ spot-check ก่อนเชื่อตัวเลขจึง
จำเป็นเสมอ (ตรงตามหลัก "ห้ามเดา" ของโปรเจค)

**ขั้นต่อไปที่ควรลอง:** (1) พิจารณาว่า SECTOR_KEYWORDS ใน `filter_relevant_news.py` (ใช้ตัดสิน
`is_weak_signal`) มีความเสี่ยง substring-collision แบบเดียวกับที่เจอใน
`INDUSTRY_KEYWORD_TO_ETF` หรือไม่ ยังไม่ได้ตรวจ (2) 23 แถวที่เหลือ (ambiguous 20 + unmapped 3)
ตัดสินใจว่าจะปล่อยเป็น mistagged ต่อไป หรือ manual review เพราะจำนวนน้อยพอจะดูเองได้ (3)
พิจารณา re-run `filter_relevant_news.py` เต็มไฟล์อีกครั้งหลังแก้ sector แล้ว เผื่อมี
weak_signal/company_level tag ที่เปลี่ยนไปตาม sector ใหม่ (ยังไม่ได้ตรวจว่าจำเป็นหรือไม่)

---
## sandbox_fundamentals_upgrade_and_smoke_test — 2026-09-15 14:37 (+07:00)

**วิธีที่ใช้:** สอง task รวมกัน (1) auto-test sandbox web simulator ที่มีอยู่แล้ว (Dashboard/
Events/Rules/Experiments/Strategies) ด้วย automated check ทุกแบบที่ทำได้ในสภาพแวดล้อมนี้ (ไม่มี
browser automation tool ใช้งานได้ในรอบนี้ — เจ้าของเครื่องเลือก "continue without browser
tools" ตอนติดตั้ง Claude in Chrome extension) (2) เพิ่ม fundamental data ต่อ ticker (P/E ratio,
market cap, EPS, dividend yield, beta, PEG, profit margin, ROE TTM, 52-week high/low, analyst
target price) เข้า Dashboard — โมดูลใหม่ `sandbox/fundamentals.py` เรียก Alpha Vantage
`OVERVIEW` endpoint (คนละ endpoint จาก `collect_alpha_vantage.py` ที่ใช้ดึงข่าว) cache เป็นไฟล์
JSON ต่อ ticker (`sandbox/data/fundamentals/{TICKER}.json`, TTL 24 ชม., gitignored เหมือน
experiments.db) fallback ไป cache เก่า (mark `stale: true`) ถ้าเรียก API ไม่สำเร็จ ไม่มีการ
fabricate ตัวเลขใดๆ — เพิ่ม endpoint `/api/fundamentals/<ticker>`, panel ใหม่ในหน้า Dashboard
sidebar (`fundamentals-panel`), และ script prefetch `sandbox/scripts/fetch_fundamentals.py`
(rate-limit 15s/ticker ตาม free tier 5 req/min)

**ข้อมูลที่ใช้:** โค้ดที่มีอยู่แล้วทั้งหมดใน `sandbox/` (ไม่แก้ inference/rules/engine) +
เรียก Alpha Vantage OVERVIEW จริงสำหรับ universe 5 ตัว (NVDA, META, TSLA, SCHW, FDX) ผ่าน
`ALPHA_VANTAGE_API_KEY` ที่มีอยู่แล้วใน `.env` (ใช้ร่วมกับ `collect_alpha_vantage.py`)

**ผลลัพธ์:** (ตัวเลขจริงจากการรันจริงทั้งหมด ไม่มีเดา)
- `python3 -m sandbox.scripts.smoke_test` → 20/20 PASS, exit code 0
- `python3 -m unittest sandbox.scripts.test_combine -v` → 13/13 ok
- `python3 -m py_compile` บนไฟล์ python ใหม่/แก้ทั้งหมด → ผ่าน, `node --check` บน
  `static/js/main.js` → ผ่าน (ไม่มี syntax error)
- เรียก Alpha Vantage OVERVIEW จริงผ่าน `fetch_fundamentals.py` ครบ 5/5 ticker สำเร็จ ตัวอย่าง
  ตัวเลขจริงที่ได้: NVDA PE=27.63 MarketCap=5.271T EPS=7.9, META PE=24.39
  MarketCap=1.651T EPS=26.57, TSLA PE=332.22 MarketCap=1.443T EPS=1.1, SCHW PE=19.54
  MarketCap=185.5B EPS=5.49, FDX PE=16.81 MarketCap=73.8B EPS=18.56 — cache file 5 ไฟล์เขียน
  สำเร็จใน `sandbox/data/fundamentals/`
- ทดสอบ cache path (`force_refresh=False`) ยิงซ้ำ NVDA → คืนค่าเดิมจาก cache, `stale: false`
  ไม่เรียก API ซ้ำ (ยืนยันด้วย `fetched_at` timestamp ไม่เปลี่ยน)
- เปิด Flask server จริง (`python3 -m sandbox.app.server`, port 5050) แล้ว curl ทุกหน้า: `/dashboard`,
  `/events`, `/rules`, `/experiments`, `/strategies` → HTTP 200 ทั้งหมด
- curl API เดิมทุกตัวยังทำงานปกติหลังแก้ (`/api/prices/NVDA`, `/api/indicators/NVDA`,
  `/api/events?ticker=NVDA`) → HTTP 200 ทั้งหมด (ไม่มี regression)
- curl API ใหม่ `/api/fundamentals/NVDA` → HTTP 200, JSON ตรง schema ที่ออกแบบไว้
- curl `/api/fundamentals/BADTICKER` (ticker นอก universe) → HTTP 400 ตามที่ตั้งใจ (validation
  เดียวกับ endpoint เดิม)
- ตรวจ HTML ของ `/dashboard` มี `<div id="fundamentals-panel">` จริง

**มุมมอง/การตีความ:** ระบบเดิม (Phase 0-5) ยังทำงานถูกต้องครบทุกหน้า/endpoint ไม่มี regression
จากการเพิ่มโมดูลใหม่ Alpha Vantage OVERVIEW ให้ข้อมูล fundamental ครบตามที่ต้องการ (P/E ฯลฯ)
สำหรับทั้ง 5 ticker ใน universe ไม่มีตัวไหน rate-limit/error เพราะ prefetch เว้นจังหวะ 15s/ครั้ง
ตามที่ออกแบบไว้ **ข้อจำกัดที่ยังเหลืออยู่**: ไม่มี browser automation tool ในรอบนี้ (เจ้าของ
เครื่องเลือก "continue without browser tools" หลัง skill `claude-in-chrome` ถูกเรียก) จึงยังไม่
ได้เห็น fundamentals panel render จริงบนหน้าจอ/เช็ค JS console error ด้วยตา — ทุกอย่างที่ automate
ได้ (HTTP status, JSON schema, JS syntax, ค่าตัวเลขจริงจาก API) ตรวจผ่านหมดแล้ว เหมือนกรณีเดียวกับ
ที่ log ไว้ใน `sandbox/OVERNIGHT_LOG.md` (Phase 3-5)

**ขั้นต่อไปที่ควรลอง:** (1) ให้ผู้ใช้เปิด browser เองยืนยันว่า fundamentals panel แสดงผลถูกต้อง
ไม่มี JS error (หรือเชื่อม claude-in-chrome ในรอบถัดไป) (2) พิจารณาว่า OVERVIEW field อื่นที่ยังไม่
ได้ดึง (เช่น QuarterlyEarningsGrowthYOY, RevenueTTM, ExDividendDate) มีประโยชน์กับ Model A
(Piotroski) หรือไม่ เมื่อเริ่มเขียน inference จริงของ Model A (3) เก็บ Alpha Vantage free-tier
quota ไว้ (25 req/day รวมทุก endpoint ของ key เดียวกับที่ `collect_alpha_vantage.py` ใช้) —
ถ้าจะรัน `fetch_fundamentals.py` บ่อยๆ ควรเพิ่ม TTL หรือแยก API key

---
## model_A_v0_data_audit — 2026-09-27 02:56 (+0700)

**วิธีที่ใช้:** เริ่ม Model A ใหม่ทั้งหมด (branch `feature/model-a-rebuild`, ตาม `model_A/SPEC.md` Phase 1) — ยังไม่มีสัญญาณ/backtest
เป็นการตรวจความครอบคลุมของข้อมูลเท่านั้น: สร้าง pipeline ใน `model_A/lib/` (constituents point-in-time จาก fja05680/sp500,
SEC XBRL RSS รายเดือน → จับคู่ ticker→CIK แบบรู้เวลา + override ที่มีหลักฐาน, SEC companyfacts ใช้ค่าที่ filed ครั้งแรก,
PIT accessor เลือก tag ทีละ field เฉพาะที่ filed แล้ว, ราคา yfinance + ตรวจ ticker reuse ด้วยราคาจริงย้อน split/market cap)
แล้ววัด % สมาชิกที่ข้อมูลครบต่อรอบ rebalance สิ้น มิ.ย. 2009–2026 — notebook: `model_A/notebooks/v0_data_audit.ipynb`,
report: `model_A/reports/v0_data_audit.html`

**ข้อมูลที่ใช้:** fja05680/sp500 `S&P 500 Historical Components & Changes (Updated).csv` @ commit a2430f2af0 (2,720 แถว,
1996-01-02→2026-08-18); SEC XBRL RSS 210 เดือน (2009-04→2026-09); SEC companyfacts 937 CIK → annual facts 166,622 แถว
(13,466 บริษัท-ปี, 812 บริษัท); yfinance ราคารายวัน 2008-01→2026-09 (1,150 ticker ที่ลองดึง, 916 มีข้อมูล) + split history
(ข้อมูลดิบทั้งหมดอยู่ใน `model_A/data/` ซึ่ง gitignore ไว้ regenerate ได้ด้วย `python3 -m lib.build_data`)

**ผลลัพธ์:**
- สมาชิกตั้งแต่ 2009: 869 ticker / 894 spell; จับคู่ CIK ได้ 833/894 spell (93.2%); override 30 segment (28 high, 2 medium)
- XBRL 10-K ฉบับแรก filed 2009-05-29; บริษัทเริ่มยื่น XBRL รายปีครั้งแรกปี 2010 = 377, 2011 = 227
- ราคา (ticker ตาม fja): 74.9% ของ spell มีราคา; หุ้นที่ยังเป็นสมาชิก 100%, หุ้นที่ออกจากดัชนีแล้ว 42.7%
- % สมาชิกที่ `usable` (มี CIK + ราคา ณ R + F-score ครบแบบถือว่าไม่มี tag หนี้ = 0 + BM ครบ): 2009 0.0, 2010 0.8,
  2011 27.2, 2012 39.4, 2015 44.9, 2018 51.0, 2020 52.5, 2023 59.8, 2026 60.4
- non-financial usable: 2011 32.1%, 2012 46.1%, 2015 52.7%, 2020 61.5%, 2026 72.1%; financial (SIC 6000–6799) F-score ครบ 3.5–14.7%
- สาเหตุหลัก (non-financial): ไม่มีราคา 127 ตัว (2011) → 1 ตัว (2026); gross margin ขาด 24.9–30.8% ของหุ้นที่มีงบ; long-term debt ขาด 8.6–19.0%
- ค่าที่ถูกแก้ย้อนหลัง (ค่าล่าสุด ≠ ค่า filed ครั้งแรก): 6.2% (shares_out) – 18.3% (gross_profit)
- Benchmark: SPY/RSP/^GSPC/^DJI ครบ 2008-01-02→2026-09-25 (USD); ^SET.BK มีแค่ 1 วัน → proxy TDEX.BK (THB, 4,565 วัน), THD (USD, 4,652 วัน)

**มุมมอง/การตีความ:** ข้อมูลพอสำหรับ v1 ตั้งแต่รอบ มิ.ย. 2011/2012 เป็นต้นไป แต่ช่วงต้น (2011–2016) ขาดราคาของหุ้น
20–31% ของสมาชิก non-financial ซึ่งเกือบทั้งหมดเป็นหุ้นที่ภายหลังถูกซื้อกิจการ/ล้มละลาย → survivorship bias สูงสุดในช่วงนี้
และทำให้ผลตอบแทนย้อนหลังน่าจะสูงเกินจริง; ตัวจำกัดอันดับสองคือ gross margin ที่บริษัท ~1 ใน 4 ไม่รายงาน ทำให้ F-score 9 ข้อ
คำนวณครบได้แค่ ~55–62% — ระหว่างทางพบและแก้บั๊ก 3 จุด (tag priority ทำให้งบปี 2017 หายในรอบ 2018, namespace ของ SEC RSS
เปลี่ยนปลายปี 2019 ทำให้ parse ได้ 0 แถว, การจับคู่ CIK แบบ majority ผิดกับบริษัทที่ปรับโครงสร้าง/บริษัทลูก utility)

**ขั้นต่อไปที่ควรลอง:** รอผู้ใช้ตัดสินใจ (1) รับ survivorship gap ช่วง 2011–2016 หรือหาแหล่งราคาหุ้น delist
(2) วิธีจัดการ gross margin/หนี้ที่ขาด (3) ช่วง held-out เทียบกับ rebalance มิ.ย. 2023 (4) proxy ของ SET — แล้วเขียน PREREG v1
---

---
## model_A_v0_addendum_missing_data — 2026-09-27 03:17 (+0700)

**วิธีที่ใช้:** ต่อจาก v0 data audit ตามคำขอของผู้ใช้ (ยังไม่มีสัญญาณ/ผลตอบแทนใด ๆ): เพิ่ม `lib/fscore.py` (สัญญาณ F-score 9 ข้อ
พร้อมสถานะ "คำนวณได้ไหม" และนโยบายข้อมูลขาด), field interest expense เป็นหลักฐานของหนี้ = 0, `lib/checks.py` (assertion กันบั๊กเงียบ:
จำนวนแถวไม่เป็นศูนย์, สมาชิกต่อรอบ 480–520, จำนวนหุ้นต่อรอบต้องไม่ตกเป็นหลุม < 0.8 × เฉลี่ยรอบข้างเคียง) แล้วรายงาน gross margin ที่ขาด
แยกกลุ่ม SIC, firm-year ที่กระทบจากหนี้ที่ไม่มี tag, firm-year ของ IR/JEF, ปีเริ่มต้นของ benchmark — notebook หัวข้อ 10 ของ
`model_A/notebooks/v0_data_audit.ipynb` และร่าง `model_A/PREREG.md` (v1, รอผู้ใช้ตรวจ)

**ข้อมูลที่ใช้:** ชุดเดียวกับ v0 + annual facts ที่ rebuild แล้ว 178,703 แถว (13,467 บริษัท-ปี) หลังเพิ่ม interest expense;
panel non-financial ที่มีงบปี t รอบ 2011–2026 = 6,420 firm-year

**ผลลัพธ์:**
- gross margin ขาด 1,736/6,420 firm-year (27.0%); ช่วง 2017+ 1,073/4,033 (26.6%); กระจุกที่ Utilities 22.3% ของที่ขาด (ขาด 68.6% ในกลุ่ม),
  Oil & gas extraction 13.4% (86.3%), Transportation 11.9% (77.8%), Business services & software 9.2% (20.8%) — กลุ่มจาก SIC
- หนี้ระยะยาว: firm-year ที่ปี t หรือ t-1 ไม่มี tag = 757/6,420 (11.8%); มีหลักฐานว่าไม่มีหนี้ (interest expense = 0) แค่ 5;
  สถานะปี t: reported 5,718, unknown (มี interest > 0) 388, unknown (ไม่มี tag interest) 309
- หุ้นที่เข้าเกณฑ์ v1 (ราคา + BM + สัญญาณ ≥ 8/9): 168 (2011), 299 (2017), 368 (2023), 375 (2026); หนี้ขาด = 0 เพิ่ม 5–12 ตัว/รอบ
- IR/JEF: 16 firm-year (0.33% ของ 4,897) ทั้งหมดเป็น IR; JEF 0 เพราะ SIC อยู่กลุ่มการเงิน
- benchmark SPY/RSP/^GSPC/^DJI เริ่ม 2008-01-02, TDEX.BK 2008-01-02, THD 2008-04-01 (ครอบคลุม มิ.ย. 2011 ทุกตัว)
- assertion ผ่านทั้งหมดบนข้อมูลจริง และจับหลุมจำลองแบบบั๊ก 2018 ได้ (2018: 197 < 0.8 × เฉลี่ยรอบข้างเคียง)
- assertion รุ่นแรก (เทียบ median ทั้งช่วง) fire ผิดที่ 2012 (190 < 198) เพราะความครอบคลุมโตตามเวลาจริง → เปลี่ยนเป็นเทียบรอบข้างเคียง

**มุมมอง/การตีความ:** gross margin ที่ขาดเป็นเรื่องโครงสร้างงบของบาง sector (utility/พลังงาน/ขนส่งไม่มีแนวคิด gross profit) ไม่ใช่ปัญหา
การดึงข้อมูล จึงควรรายงานผลแยก sector และ sensitivity S1; หนี้ที่ไม่มี tag เกือบทั้งหมดมี interest expense > 0 แปลว่ามีหนี้จริงแต่ใช้ tag อื่น
การถือเป็น 0 จะผิด จึงใช้ "ไม่ทราบ" เป็นหลักตามที่ผู้ใช้กำหนด; IR/JEF มีผลน้อยมาก (0.33%)

**ขั้นต่อไปที่ควรลอง:** ผู้ใช้ตรวจ `model_A/PREREG.md` (โดยเฉพาะหัวข้อ 10: High F ≥ 7, นิยาม C2, rf = ^IRX, EW ไม่รวมการเงิน, delist = เงินสด)
แล้ว commit เวอร์ชันล็อกก่อนรัน v1
---

---
## model_A_v1_baseline_piotroski — 2026-09-27 03:47 (+0700)

**วิธีที่ใช้:** v1 ตาม `model_A/PREREG.md` (ล็อกที่ commit 3daf3a7 ก่อนรัน) — Piotroski baseline บน S&P 500 non-financial แบบ point-in-time:
P1 = BM quintile บน (หุ้น BM > 0), P2 = F-score ≥ 7 (ต้องมี ≥ 8/9 ข้อ แล้ว rescale; หนี้ = 0 เฉพาะเมื่อมีหลักฐาน), P3 = P1 ∩ P2;
equal-weight, rebalance วันทำการสุดท้ายของ มิ.ย., ต้นทุน 10 bps/ข้าง, หุ้น delist = เงินสด; benchmark ตัดสิน = EW universe เดียวกัน;
rf = ^IRX; sensitivity S1 (ข้อที่ขาด = 0), S2 (หนี้ที่ขาด = 0), S3 (ตัด IR/JEF) × P1–P3 = 12 variant; ราคาโหลดถึง 2023-06-30 เท่านั้น
(held-out guard) — ต่างจาก v0 ตรงที่คำนวณสัญญาณและผลตอบแทนจริงครั้งแรก — notebook `model_A/notebooks/v1_baseline_piotroski.ipynb`

**ข้อมูลที่ใช้:** pipeline v0 (fja05680 @ a2430f2af0, SEC companyfacts first-filed, yfinance Adj Close/Close + split) หลังแก้บั๊ก;
universe ที่เข้าเกณฑ์ (main) 168 หุ้น (2011) → 352 หุ้น (2022), 12 รอบ rebalance 2011–2022; ตรวจ market cap กับ SEC EntityPublicFloat 2,279 หุ้น-รอบ

**ผลลัพธ์:**
- **C1 ไม่ผ่าน**: ช่วงตัดสิน (rebalance 2017–2022, 72 เดือน) Sharpe P3 = 0.4115 vs EW = 0.6308
- ช่วงตัดสิน: EW CAGR 12.34% Sharpe 0.631 MDD −37.7%; P1 10.09% / 0.452 / −49.6%; P2 12.72% / 0.636 / −38.3%; P3 9.92% / 0.412 / −53.1%;
  ส่วนเกินเฉลี่ยต่อปี vs EW (NW t, lag 3): P1 −0.67% (−0.14), P2 +0.46% (0.38), P3 +0.61% (0.09)
- ช่วงประกอบ (2011–2016): EW 14.15% / 1.186; P1 13.31% / 1.098; P2 13.85% / 1.113; P3 18.35% / 1.172 (ส่วนเกิน +4.12%, t 1.15)
- P3 มีหุ้น < 20 ตัวใน 11/12 รอบ (3–18 ตัว; รอบ 2022 = 28)
- 12 variant ช่วงตัดสิน: P3 Sharpe 0.40–0.43 < EW 0.63–0.64 ทุก variant; P1 < EW ทุก variant; P2 > EW ใน 3/4 (ห่าง ≤ 0.0055)
- rank IC เฉลี่ย ช่วงตัดสิน: BM −0.080, F +0.007; ช่วงประกอบ: BM −0.025, F +0.013
- SPY ช่วงตัดสิน (ประกอบ, มี survivorship เอียงเข้าข้างเรา): CAGR 12.54%, Sharpe 0.681
- DCA ช่วงตัดสิน: IRR P3 14.12%, EW 12.14%, SPY 11.92%; lumpsum multiple P3 1.764, EW 2.010
- ตรวจ market cap / public float: median 1.014, < 0.7 = 0.49% (หลังตัดค่า float ที่ผิดหลัก 13 ตัว)
- บั๊กที่พบและแก้ระหว่างรัน (Sharpe P3/EW ของแต่ละรอบ): ตัด split ที่ END 0.6125/0.6294 → ไม่ปรับหุ้นด้วย split ระหว่างวันนับหุ้นกับ R
  0.4614/0.6301 → ticker reuse IR 0.4493/0.6305 → สุดท้าย 0.4115/0.6308 (C1 ไม่ผ่านทุกรอบ)

**มุมมอง/การตีความ:** ใน S&P 500 ช่วง 2017–2022 "ความถูก" (BM) ไม่ได้ช่วย (P1 แพ้ EW, IC ของ BM ติดลบ) และ "คุณภาพ" (F) ได้ผลใกล้ EW
การรวมสองเงื่อนไขทำให้พอร์ตเหลือ ~13 ตัว กระจุกในหุ้น value วัฏจักร (เรือสำราญ/สายการบินรอบ 2019–2020) จึงผันผวนสูงและ drawdown ลึก
สอดคล้องกับงานที่พบว่า F-score อ่อนลงในช่วงหลังและในหุ้นใหญ่ — ผลช่วง 2011–2016 ดูดีกว่าแต่มี survivorship สูงและหุ้นน้อยมาก
ส่วนเกินเชิงเลขคณิตที่เป็นบวกของ P3 มาจากความผันผวนสูง (CAGR ยังต่ำกว่า EW) ไม่ใช่หลักฐานว่าสัญญาณได้ผล

**ขั้นต่อไปที่ควรลอง:** v2 (quality/value สัญญาณใหม่ทีละตัว + sector-neutral) ตาม SPEC หลังผู้ใช้ตรวจ v1 และเขียน PREREG v2;
พิจารณาใช้จำนวนหุ้นจาก 10-Q เพื่อลดความคลาดเคลื่อนของ market cap หลังการควบรวม
---

---
## model_A_v1_bugfix_record — 2026-09-27 04:19 (+0700)

**วิธีที่ใช้:** บันทึกย้อนหลังให้ครบตามที่ผู้ใช้ขอ — บั๊ก 3 จุดที่พบระหว่างรัน v1 (ทุกจุดทำให้ market cap ผิด → BM และการเลือกหุ้นผิด)
สเปก v1 (PREREG) ไม่เปลี่ยน รันซ้ำด้วยสเปกเดิมหลังแก้แต่ละจุด ตัวเลขทุกตัวมาจาก output ของแต่ละรอบที่รันจริง

**ข้อมูลที่ใช้:** ชุดเดียวกับ v1 (rebalance 2011–2022, ราคาถึง 2023-06-30); ตัวตรวจอิสระ = SEC dei:EntityPublicFloat (float ณ วันทำการสุดท้ายของไตรมาส 2)
จับคู่กับ R ได้ 2,277–2,279 หุ้น-รอบ

**ผลลัพธ์:**
- **บั๊ก 1 — ตัดประวัติ split ที่ END (2023-06-30)**
  อาการ: NVDA/AVGO/LRCX/KLAC ติด P1/P3 (กลุ่ม "หุ้นถูก"); NVDA มิ.ย. 2017 market cap 8.509e9 vs public float 9.431e10 (2017-07-28) — เล็กไป ~10 เท่า
  สาเหตุ: Close ของ Yahoo ถูกปรับย้อนหลังด้วย split หลัง END แล้ว (NVDA 10:1 2024-06-10, AVGO 10:1 2024-07-15, LRCX 10:1 2024-10-03,
  CTAS 4:1 2024-09-12, WMT 3:1 2024-02-26) การตัด split ทิ้งทำให้แปลงกลับเป็นราคาจริงไม่ได้
  แก้: ใช้ประวัติ split ทั้งหมด (เป็นการถอดการปรับราคา ไม่ใช่มองอนาคต) + เพิ่มหัวข้อตรวจ market cap กับ public float
  ผล: Sharpe P3/EW ช่วงตัดสิน 0.6125/0.6294 → 0.4614/0.6301; CAGR P3 ช่วงตัดสิน 15.99% → 11.63%
- **บั๊ก 2 — ไม่ปรับจำนวนหุ้นด้วย split ที่เกิดระหว่างวันนับหุ้น (หน้าปกงบ) กับวัน R**
  อาการ: market cap / float: AMZN มิ.ย. 2022 = 0.057, CF 2015 = 0.206, DXCM 2022 = 0.249, CSX 2021 = 0.340, SHW 2021 = 0.341,
  EW 2020 = 0.339, FTNT 2022 = 0.355, PPG 2015 = 0.505 (assertion เดิม "ratio < 0.5 ต้อง < 2%" ผ่านทั้งที่มีบั๊กนี้)
  สาเหตุ: เช่น AMZN หุ้น 508.8 ล้าน ณ 2022-01-26 (ก่อน split 20:1 วันที่ 2022-06-06) × ราคาหลัง split
  แก้: PIT เก็บ shares_date; ปรับจำนวนหุ้นด้วย split ระหว่าง shares_date กับวันราคา; F_EQ ใช้ shares_date ของสองปีเช่นกัน
  ผล: Sharpe P3/EW 0.4614/0.6301 → 0.4493/0.6305; percentile 1 ของ market cap/float 0.504 → 0.717; AMZN 2022 market cap 1.081e12
- **บั๊ก 3 — ticker reuse ที่ market cap เกิน $1B (หลุดการตรวจ mcap)**
  อาการ: IR มิ.ย. 2017–2019 market cap/float 0.24–0.33 ทั้งที่จำนวนหุ้นถูก (259.5 ล้าน ณ 2017-02-01)
  สาเหตุ: ราคา Yahoo "IR" ปัจจุบันเป็นของ Ingersoll Rand Inc. (อดีต Gardner Denver ราคา ~$21 ช่วงนั้น) แต่สมาชิกจริงคือ Ingersoll-Rand plc (ปัจจุบัน TT)
  แก้: เลือกราคาจาก ticker ปัจจุบันของ CIK ก่อน แล้วค่อย ticker ตาม fja — IR 2017 ได้ market cap 2.372e10 vs float 2.312e10
  ผล: Sharpe P3/EW 0.4493/0.6305 → **0.4115/0.6308 (ผลสุดท้าย)**; percentile 1 ของ ratio 0.717 → 0.776;
  หลังตัดค่า float ผิดหลักใน XBRL 13 ตัว ratio < 0.7 เหลือ 0.49%; v0 รันใหม่ — หุ้นเข้าเกณฑ์รอบ 2017 299 → 300, firm-year รวม 4,897 → 4,900
- assertion ใหม่: median ratio ใน [0.9, 1.5] และ ratio < 0.7 ต้อง < 1% (หลังตัด float ผิดหลัก ratio < 0.01 หรือ > 100)
- **C1 ไม่ผ่านในทุกรอบ** (0.6125 < 0.6294, 0.4614 < 0.6301, 0.4493 < 0.6305, 0.4115 < 0.6308)

**มุมมอง/การตีความ:** บั๊กทั้งสามเป็นเรื่อง "ราคาจริง ณ วันนั้น × จำนวนหุ้น ณ วันนั้น" ที่ต้องสอดคล้องกันทั้งเรื่อง split และตัวตนของบริษัท
ตัวตรวจอิสระ (public float) คือสิ่งที่จับได้ — assertion รุ่นแรกหลวมเกินจนปล่อยบั๊ก 2 และ 3 ผ่าน; การแก้บั๊กทำให้ผลของ P3 แย่ลง
(ไม่ได้แก้เพื่อให้ผลดีขึ้น) และไม่เปลี่ยนผลตัดสิน C1

**ขั้นต่อไปที่ควรลอง:** ใช้ public float check เป็น assertion มาตรฐานของทุกเวอร์ชัน; ข้อจำกัดที่เหลือ = บริษัทที่ออกหุ้นควบรวมหลังวันนับหุ้น
(NWL 2016 0.562, XRAY 2016 0.601, NEM 2019 0.652, AMD 2022 0.656, OKE 2017 0.564, WAB 2019 0.546) และ DD 2012–2013 (0.621–0.625)
→ พิจารณาใช้จำนวนหุ้นจาก 10-Q ในเวอร์ชันถัดไป
---

---
## model_A_v1_review_addendum_and_v2_coverage — 2026-09-27 04:19 (+0700)

**วิธีที่ใช้:** (1) เพิ่มหัวข้อ 13 ใน v1 notebook ตามคำขอผู้ใช้ — รายชื่อหุ้น P3 รอบ 2019/2020 พร้อมผลตอบแทนรายตัว และ rank IC รายปีของ BM/F
(ข้อมูล in-sample เดิม ไม่เปลี่ยนสเปก) และแก้ถ้อยคำในสรุป v1 (2) เพิ่ม field EBIT, เงินสด, หนี้ระยะสั้น, capex และ `lib/signals_v2.py`
แล้ววัดความครอบคลุมของสัญญาณ v2 (ไม่มีการคำนวณผลตอบแทน) เพื่อร่าง PREREG v2

**ข้อมูลที่ใช้:** ผล v1 (scores/backtest เดิม); annual facts rebuild 232,431 แถว (13,705 บริษัท-ปี); U2 (non-financial + ราคา/market cap ผ่าน) 255–374 หุ้นต่อรอบ 2011–2022

**ผลลัพธ์:**
- P3 รอบ 2019 (18 ตัว): −16.62% vs EW −1.77% (ก่อนต้นทุน) — NCLH −69.36%, CCL −63.50%, XRX −54.85%, KSS −53.47%, PVH −49.12%, XOM −38.17%
- P3 รอบ 2020 (7 ตัว): +101.28% vs EW +49.99% — UAL +51.08%, DAL +54.22%, ALK +66.33%, COP +50.73%, JCI +105.19%, MGM +153.96%, TPR +227.41%
- **แก้ถ้อยคำสรุป v1**: ร่างแรกเขียน "โดนหนักช่วงโควิด (รอบ 2019–2020 มีเรือสำราญ/สายการบิน)" ซึ่งถูกครึ่งเดียว —
  เรือสำราญอยู่รอบ 2019 และขาดทุน, สายการบินอยู่รอบ 2020 และกำไร → P3 เป็นพอร์ตหุ้นวัฏจักรที่แกว่งแรงทั้งสองทาง
- rank IC ช่วงตัดสิน: BM เฉลี่ย −0.0801, ติดลบ 4/6 ปี, แย่สุด 2019 (−0.4294), ตัดปีนั้นแล้วเฉลี่ย −0.0103, median −0.1493;
  F เฉลี่ย +0.0068, ติดลบ 3/6, แย่สุด 2017 (−0.0564), ตัดแล้ว +0.0195, median −0.0012
- rank IC ช่วงประกอบ: BM −0.0254 (ติดลบ 4/6, แย่สุด 2014 −0.2629, ตัดแล้ว +0.0222); F +0.0131 (ติดลบ 2/6, ตัดแล้ว +0.0233)
- ความครอบคลุม v2 ช่วงตัดสิน: Q_GPA 73–77%, Q_ROIC 81–86%, Q_LOWACC 98–100%, V_BM 100%, V_EP 99–100%, V_EBITEV 74–79%, V_FCFP 94–95%,
  I_LOWISS 98–100%, I_LOWAG 98–100%; มีทั้งเสา quality และ value 98.6–100% ทุกรอบ; top 20% ของ U2 = 51–75 ตัว

**มุมมอง/การตีความ:** IC ติดลบของ BM ไม่ได้มาจากปี 2019 ปีเดียว (median ติดลบกว่าค่าเฉลี่ย) แต่ปี 2019 มีน้ำหนักมากที่สุด;
ข้อมูลสำหรับ v2 พอให้พอร์ตแบบจัดอันดับมีหุ้น ≥ 50 ตัวทุกรอบตามที่ผู้ใช้ต้องการ

**ขั้นต่อไปที่ควรลอง:** ผู้ใช้ตรวจ PREREG v2 (ส่วน "v2" ใน `model_A/PREREG.md`, สถานะ DRAFT) ก่อนรัน
---

---
## model_A_autorun_round_001_single_signals — 2026-09-27 (+0700)

**วิธีที่ใช้:** เริ่มโหมด AUTORUN (`model_A/AUTORUN.md`): ล็อกเกณฑ์ S1–S7 ใน `model_A/PREREG_AUTORUN.md` (commit d7acc72 ก่อนประเมินใด ๆ),
ล็อก held-out ทางเทคนิค (`lib/guard.py`), นับ trial ใน `model_A/trials.csv` (เริ่ม 12 จาก v1) แล้วรัน round 001 = ตระกูล A สัญญาณเดี่ยว
15 ตัว (quality/value/investment/F/G/Altman Z/shareholder yield/stability/leverage) × {overall, sector-neutral} + ตัวกรอง Altman/Beneish 3 แบบ;
top 20% ขั้นต่ำ 50 ตัว, EW, rebalance มิ.ย. 2011–2022, ต้นทุน 10/25 bps — สเปกใน `model_A/rounds/round_001/HYPOTHESIS.md` (commit 5763358 ก่อนรัน)
ก่อนรันพบและแก้บั๊กงบปีก่อน (t−1) ใน PIT (แถวว่าง ณ วันเริ่มใช้ ASC 606) → v1 รันใหม่: Sharpe P3/EW 0.4115/0.6308 → 0.4097/0.6298 (C1 ยังไม่ผ่าน)

**ข้อมูลที่ใช้:** panel รายปี `data/interim/panel_annual.parquet` 6,023 แถว (universe U 255–376 หุ้นต่อรอบ); annual facts 325,690 แถว
(เพิ่ม field liabilities, retained earnings, receivables, PP&E, depreciation, SG&A, R&D, advertising, dividends, buybacks, stock issued)

**ผลลัพธ์:**
- trial รอบนี้ 33 → สะสม 45; **ผู้เข้ารอบ (S1+S2+S3+S6) = 0**
- benchmark ช่วงตัดสิน: EW(U) Sharpe 0.640, SPY 0.681 → S1 ต้อง ≥ 0.831
- ผ่าน S1 ตัวเดียว: Q_LOWACC_overall Sharpe 0.863 (25 bps ผ่านด้วย), CAGR 18.6% vs EW 12.5%, S2 100%, S6 63/51 แต่ **DSR 0.860 < 0.95**;
  ช่วงประกอบ 2011–2016 Sharpe 0.787 แพ้ EW 1.137
- quality อื่น: ROIC 0.817, G-score 0.793, Altman Z 0.783, GP/A 0.775 (overall) — ชนะ EW แต่ไม่ถึง S1
- value: BM 0.484, E/P 0.475, EBIT/EV 0.553, FCF/P 0.629 (overall) — แพ้ EW
- walk-forward: corr(Sharpe ส่วนเกินช่วงประกอบ, ช่วงตัดสิน) = −0.247; ตัวที่ดีที่สุดช่วงประกอบ (A_STAB_sector +0.285) ได้ −0.030 ในช่วงตัดสิน

**มุมมอง/การตีความ:** quality ดีกว่า value ในช่วง 2017–2022 แต่ความได้เปรียบไม่เสถียรข้ามช่วงเวลาและไม่ผ่านการปรับ multiple testing
→ ไม่มีสัญญาณเดี่ยวที่ "ชนะขาดรอย"; ไม่ลดเกณฑ์

**ขั้นต่อไปที่ควรลอง:** round 002 ตระกูล B (คะแนนรวม quality+value/QARP/quality composite) ตาม `model_A/autorun/STATE.md`
---

---
## model_A_autorun_round_002_composites — 2026-09-27 (+0700)

**วิธีที่ใช้:** AUTORUN round 002 ตระกูล B: คะแนนรวมน้ำหนักเท่ากัน 6 สูตร (QV, QUAL=profitability+safety, QARP, F+value, shareholder yield+quality,
QVI) × {overall, sector-neutral}; top 20% ขั้นต่ำ 50, EW, rebalance มิ.ย. 2011–2022, 10/25 bps — สเปก `model_A/rounds/round_002/HYPOTHESIS.md` (commit 9f26090 ก่อนรัน)

**ข้อมูลที่ใช้:** panel รายปีเดียวกับ round 001 (6,023 แถว)

**ผลลัพธ์:**
- 12 trial → สะสม 57; ผู้เข้ารอบ 0; ไม่มีตัวไหนผ่าน S1 (ต้อง Sharpe ≥ 0.831)
- ใกล้สุด B_SHYQ_overall: Sharpe 0.821, CAGR 17.6% (EW 12.5%), S2 100%, DSR 0.703, ช่วงประกอบ 1.211 (EW 1.137)
- B_QUAL_overall 0.755 (MDD −32.3% vs EW −37.6%); สูตรที่มี value: 0.489–0.628 (แพ้ EW ทั้งหมด)
- walk-forward: corr(ส่วนเกินช่วงประกอบ, ช่วงตัดสิน) = −0.037

**มุมมอง/การตีความ:** value ถ่วงผลทุกสูตรในช่วงตัดสิน; shareholder yield + quality สม่ำเสมอที่สุดแต่ไม่ถึงเกณฑ์

**ขั้นต่อไปที่ควรลอง:** round 003 ตระกูล C (momentum/low vol/trend และพื้นฐาน×ราคา) บน panel รายเดือน
---

---
## model_A_autorun_round_003_price_signals — 2026-09-27 (+0700)

**วิธีที่ใช้:** AUTORUN round 003 ตระกูล C: สัญญาณราคา (momentum 12-1, low vol 252 วัน, trend 200 วัน, ใกล้ high 52 สัปดาห์) และผสมพื้นฐาน×ราคา
(quality+mom, shareholder yield+quality+mom, quality+low vol, value+mom) × {overall, sector}; rebalance รายเดือน 144 รอบ, top 20% ขั้นต่ำ 50, EW,
10/25 bps, benchmark EW(U) รายเดือน — สเปก `model_A/rounds/round_003/HYPOTHESIS.md` (commit 1dacf71 ก่อนรัน)
รันครั้งแรกพบบั๊กปฏิทิน (ตารางราคามีวันหยุดสหรัฐจาก TDEX.BK/THB=X → momentum หาย 6 เดือน, พอร์ต 0 ตัว) → แก้ให้ใช้ปฏิทิน SPY และรันใหม่สเปกเดิม

**ข้อมูลที่ใช้:** panel รายเดือน 72,334 แถว (U 255–385 หุ้นต่อเดือน), สัญญาณราคาจาก Adj Close ถึง 2023-06-30

**ผลลัพธ์:**
- 16 trial → สะสม 73; ผู้เข้ารอบ 0; ไม่มีตัวไหนผ่าน S1 (ต้อง ≥ 0.831; EW รายเดือน 0.614, SPY 0.681)
- ใกล้สุด C_SHYQMOM_overall 0.824 (CAGR 15.6% vs 12.2%, S2 100%, DSR 0.301, ช่วงประกอบ 1.182 vs 1.093); C_QMOM_overall 0.793
- momentum เดี่ยว 0.626–0.627; low vol 0.605–0.677 (ช่วงประกอบ 1.451–1.633); value+mom 0.550–0.563
- ก่อนแก้บั๊ก: C_MOM_overall 0.558, C_SHYQMOM_overall 0.787 (ไม่มีผู้เข้ารอบเช่นกัน)

**มุมมอง/การตีความ:** สัญญาณราคาเดี่ยวไม่เด่นในหุ้นใหญ่ช่วงนี้; แกน shareholder yield + quality ยังสม่ำเสมอที่สุดแต่ต่ำกว่า S1 เล็กน้อย

**ขั้นต่อไปที่ควรลอง:** round 004 ตระกูล D (น้ำหนัก, ความถี่, sector cap, turnover buffer) บนฐานที่เลือกด้วยกฎประกาศล่วงหน้า
---

---
## model_A_autorun_round_004_construction — 2026-09-27 (+0700)

**วิธีที่ใช้:** AUTORUN round 004 ตระกูล D: เปลี่ยนการสร้างพอร์ตทีละมิติ (inverse-vol, cap-weight, ความถี่ 2 แบบ, sector cap 25%, turnover buffer top 30%)
บนฐาน 2 ตัวที่เลือกด้วยกฎประกาศล่วงหน้า (Sharpe สูงสุดที่ผ่าน S2/S6: r001_Q_LOWACC_overall, r003_C_SHYQMOM_overall) — สเปก
`model_A/rounds/round_004/HYPOTHESIS.md` (commit 044c41c ก่อนรัน); เพิ่มน้ำหนักแบบกำหนดเองใน `lib/backtest.py` (ทดสอบ unit แล้ว)

**ข้อมูลที่ใช้:** panel รายเดือน (subset ตามความถี่), สัญญาณราคา, market cap จาก panel

**ผลลัพธ์:**
- 12 trial → สะสม 85; ผู้เข้ารอบ 0
- ผ่าน S1 ทั้ง 10/25 bps 5 ตัว: Q_LOWACC W_IV 0.842, W_CAP 0.929, SECCAP 0.863, BUFFER 0.872; SHYQMOM W_CAP 0.923 (EW 0.640/0.614, SPY 0.681)
- DSR ทุกตัว 0.011–0.687 (< 0.95); cap-weighted DSR 0.125–0.189
- ฐาน Q_LOWACC ทุก variant แพ้ EW ในช่วงประกอบ (0.770–1.020 vs 1.108–1.137)

**มุมมอง/การตีความ:** การจัดพอร์ตช่วยผ่าน S1 ได้ แต่ส่วนเกินเทียบ EW ไม่แรงพอหลังปรับจำนวน trial และผูกกับช่วงเวลา; cap-weighting ได้ผลจาก mega-cap tilt

**ขั้นต่อไปที่ควรลอง:** round 005 ตระกูล E (trend filter, vol targeting, drawdown stop) + S5 บนดัชนี 6 ชุด
---

---
## model_A_autorun_round_005_overlays — 2026-09-27 (+0700)

**วิธีที่ใช้:** AUTORUN round 005 ตระกูล E: overlay ระดับตลาด 3 แบบ (trend 10 เดือน, vol target 15%/63 วัน, drawdown stop −15% + trend) บน SPY และ EW(U)
รายเดือน, ตัดสินสิ้นเดือน, เงินสดได้ ^IRX, ต้นทุน 10/25 bps × |Δw|; S5 บนดัชนี ^GSPC 1970–2010, ^N225, ^FTSE, ^GDAXI, ^HSI, ^STI —
สเปก `model_A/rounds/round_005/HYPOTHESIS.md` (commit 80d136f ก่อนรัน)

**ข้อมูลที่ใช้:** SPY Adj Close, NAV ของ EW(U) รายเดือน, ดัชนีต่างประเทศ (price index) ถึง 2023-06-30

**ผลลัพธ์:**
- 6 trial → สะสม 91; ผู้เข้ารอบ 0
- ช่วงตัดสิน Sharpe: trend SPY 0.457, voltarget SPY 0.592, ddstop SPY 0.486, trend EW 0.369, voltarget EW 0.451, ddstop EW 0.347 (SPY 0.681, EW 0.614)
- MaxDD trend SPY −24.9%, trend EW −23.5% (EW −38.4%); ถือเงินสด 100%: trend SPY 17.4% ของเดือน → ตก S6
- S5 (ดีกว่า buy-and-hold): trend 4/6, voltarget 5/6, ddstop 5/6 (เช่น ^GSPC 1970–2010 trend 0.600 vs 0.456)

**มุมมอง/การตีความ:** overlay ช่วยในประวัติยาวหลายตลาด แต่ในช่วง 2017–2022 ออกช้าเข้าช้า → แพ้ buy-and-hold ชัดเจน; ไม่ใช่เครื่องมือชนะตลาดตาม S1

**ขั้นต่อไปที่ควรลอง:** round 006 ตระกูล F (ML baseline แบบ walk-forward)
---

---
## model_A_autorun_round_006_ml_and_final_report — 2026-09-27 (+0700)

**วิธีที่ใช้:** AUTORUN round 006 ตระกูล F: HistGradientBoosting (19 feature เป็น percentile rank, label = อันดับผลตอบแทน 12 เดือนข้างหน้า,
walk-forward expanding เทรนเฉพาะ label ที่รู้ผลแล้ว, ค่าตายตัว) และ DecisionTree ลึก 2 เป็นกฎ; rebalance รายปี top 20% ขั้นต่ำ 50 —
สเปก `model_A/rounds/round_006/HYPOTHESIS.md` (commit 344be1e ก่อนรัน) จากนั้นเขียนรายงานฉบับสมบูรณ์ (`model_A/README.md`, `REPORT.md`)
และตาราง S5 ระดับ factor อ้างอิง (พบและแก้ค่า missing −99.99 ในไฟล์ Ken French)

**ข้อมูลที่ใช้:** panel รายเดือน + สัญญาณราคา (label ถึง 2023-06-30), Ken French factor 6 ชุด (ถึง 2023-06)

**ผลลัพธ์:**
- round 006: 2 trial → สะสม 93; GBM Sharpe 0.636 (EW 0.640, SPY 0.681), tree 0.526; ผู้เข้ารอบ 0
- tree 10 ปี: feature แบ่งชั้นแรก V_FCFP 4 ปี ที่เหลือเปลี่ยนทุกปี
- สรุปทั้ง AUTORUN: ผ่าน S1 6 trial, ผ่าน S1+S2+S6 6 trial (กลุ่ม low accruals 5 + SHY+quality+mom cap-weight 1), ผ่าน S3 = 0; DSR สูงสุด ณ N = 93 = 0.613
- corr(Sharpe เหนือ EW ช่วงประกอบ, ช่วงตัดสิน) ทุก trial = −0.074
- S5 factor อ้างอิง: HML, RMW, CMA, MOM และ combo เป็นบวก 6/6 ชุด (หลังแก้ค่า missing)
- held-out ไม่ถูกใช้ (ไม่มีกฎที่ freeze); ไม่มี adapter (ทำเฉพาะกฎ freeze ตาม AUTORUN ข้อ 7)

**มุมมอง/การตีความ:** ไม่มีกฎ "ชนะขาดรอย" — ทุกกฎระดับ C; factor คลาสสิกมีอยู่จริงในระยะยาว/หลายตลาด แต่ในหุ้นใหญ่ S&P 500 ช่วง 2017–2022
ไม่แรงพอจะผ่านการปรับจำนวนการลอง และไม่เสถียรข้ามช่วงเวลา

**ขั้นต่อไปที่ควรลอง:** ต้องให้ผู้ใช้ตัดสิน (ข้อมูลหุ้นที่ delist แบบเสียเงิน, ขยาย universe เป็นข้อมูลอิสระ) — ห้ามลดเกณฑ์
---

---
## model_A_autorun_round_007_top1500_and_sandbox_demo — 2026-09-27 (+0700)

**วิธีที่ใช้:** (1) round 007 ตามที่ผู้ใช้อนุมัติ: universe top-1500 ตาม market cap แบบ PIT (ไม่มีรายชื่อ S&P 400/600 ย้อนหลังที่ตรวจได้),
candidate pool จาก SEC frames (dei:EntityPublicFloat ทุกไตรมาส), ตัวกรองราคา ≥ $5 และ median dollar volume 63 วัน ≥ $1M, ต้นทุน 10/25/50 bps,
20 สเปกเดิม + 2 สเปกใหม่บน S&P 500 — HYPOTHESIS commit 10e9072 ก่อนรัน; บันทึก deviation (เปลี่ยน universe หลังเห็นผล)
(2) ผู้ใช้สั่งหยุด S&P 1500 → เดโม adapter กฎอันดับ 1–2 ใน `model_A/export/` (experimental-not-frozen) + `model_A/stress_cases/`

**ข้อมูลที่ใช้:** pool 6,676 CIK, companyfacts 6,757 บริษัท (1.59M แถว first-filed), Yahoo ราคา 4,016 ticker (3,596 ไม่มีข้อมูล), panel top-1500 12 รอบ

**ผลลัพธ์:**
- coverage ราคาของ top-1500 ตาม public float: 56.7% (2011) → 82.8% (2022) vs S&P 500 69.6% → 94.4%; ช่วงตัดสินต่ำกว่าเฉลี่ย 14.2 จุด (p < 0.001 ทุกปี)
- บริษัทที่ออกไปแล้วมีราคา: top-1500 19.5% (1,198 บริษัท) vs S&P 500 42.7%
- ตรวจ market cap/public float: median 1.040, < 0.7 = 0.75% (หลังแก้บั๊ก)
- round 007: 22 trial → สะสม 115; ไม่มีตัวไหนผ่าน S1 แม้ที่ 10 bps; EW(U1500) Sharpe 0.525; สูงสุด U1500 Q_ROIC 0.698 (DSR 0.201)
- บั๊กที่พบและแก้ก่อนประเมิน: pool ตกหล่นบริษัทปีบัญชีไม่จบ ธ.ค. (AAPL หาย), split หายแบบเงียบ (ไม่กระทบ S&P 500 เดิม), ราคาดาวน์โหลดล้มเหลวแบบเงียบ (กู้ได้ 1,555 ticker)
- เดโม: adapter เลือกหุ้นตรงกับ backtest round 004 ทุกรอบ (rule1 12, rule2 144); คะแนนเฉพาะก่อน 2023-06-30

**มุมมอง/การตีความ:** ผล top-1500 ติดป้าย "เสี่ยง survivorship สูง" ห้ามใช้เป็นหลักฐานหลัก และก็ไม่ผ่านอยู่ดี; เดโม sandbox เป็นการทดลองระบบ ไม่ใช่หลักฐาน

**ขั้นต่อไปที่ควรลอง:** รอผู้ใช้ตัดสิน (ต่อ sandbox ตาม export/README.md ต้องได้รับอนุมัติแก้ไฟล์ใน sandbox/)
---

---
## model_A_explore2_T0_T1_round008 — 2026-09-27 (+0700)

**วิธีที่ใช้:** EXPLORE2 (`model_A/EXPLORE2.md`) — T0 วินิจฉัย low accruals (ไม่นับ trial); T1 ตัวกรองแนวโน้ม Faber SMA10 (A) และ TSMOM 12 เดือน (B)
บน 11 ตลาด (ข้อมูลถึง 2023-06-30) ด้วยเกณฑ์ `model_A/PREREG_OVERLAY.md` (commit 29b3cf5 ก่อนรัน) และซ้อนบนพอร์ตของเรา (round 008, 3 trial)

**ข้อมูลที่ใช้:** panel รายปีเดิม; ดัชนี Yahoo (^GSPC/^IXIC/^N225 ตั้งแต่ 1970–71, ^FTSE/^GDAXI/^HSI/^STI 1984–88, ^DJI 1992, EEM 2003, TDEX.BK/THD 2008); ^IRX ตั้งแต่ 1960

**ผลลัพธ์:**
- T0: ข้อมูลขาดไม่ใช่สาเหตุ (สัญญาณครบ 98.6–100%); แพ้หนัก 2014–2016; ถือพลังงาน 14.3% (EW 4.2%) ช่วงน้ำมันดิ่ง; ตัดพลังงานแล้วยังแพ้ (0.951 vs 1.223);
  Ken French US RMW 1.1%/ปี (2011–17) vs 6.1%/ปี (2017–23)
- T1 ระดับดัชนี: กฎ A ผ่าน 6/11, กฎ B ผ่าน 6/11 (ต้อง ≥ 8) → ไม่ได้ป้าย "ลดความเสี่ยงได้จริง"; ญี่ปุ่นลด drawdown 43–47 จุด; SET proxy ลดไม่ได้ (crash 2008 อยู่ในช่วงอุ่นเครื่อง)
- T1 ระดับพอร์ต: r008_A_LOWACC_WCAP Sharpe 0.956 ผ่าน S1 แต่ S2 68%, DSR 0.015, S6 ตก; r008_B_EW 0.183; r008_B_LOWACC_WCAP 0.647 — สะสม 118 trial

**มุมมอง/การตีความ:** ความได้เปรียบของ low accruals ผูกกับยุค factor; ตัวกรองแนวโน้มช่วยในตลาดขาลงยาวแต่ไม่ครอบคลุมพอ

**ขั้นต่อไปที่ควรลอง:** T2 factor momentum (round 009)
---

---
## Model A EXPLORE2 round 012 — T4 Lazy Prices (ความเปลี่ยนแปลงของ 10-K) — 2026-09-27 11:05

**วิธีที่ใช้:** ดาวน์โหลด 10-K ของบริษัท S&P 500 จาก EDGAR (`lib/lazyprices.py`) เก็บเฉพาะความถี่คำ คำนวณ cosine similarity ของ term frequency (และ Jaccard เป็นข้อมูลประกอบ) ระหว่าง 10-K ปีนี้กับปีก่อน (ห่าง 9–15 เดือน) ทั้งเอกสารและเฉพาะ Item 1A; ทุกสิ้นเดือนถือ quintile ที่ similarity สูงสุด (เปลี่ยนน้อย) EW ขั้นต่ำ 50 ตัว ใช้ 10-K ล่าสุดที่ยื่น ≤ R−1 วันและอายุ ≤ 15 เดือน; ไม่ใช้ LLM; สเปกตาม HYPOTHESIS ที่ commit ก่อนรัน (6c1fb3e) ไม่มีการจูน ต่างจาก round ก่อนหน้าตรงที่เป็นแหล่งข้อมูลข้อความ ไม่ใช่งบ/ราคา

**ข้อมูลที่ใช้:** SEC submissions API + เอกสารหลัก 10-K/10-K405/10-KT ของ 812 CIK ยื่น 2010-01-01 – 2023-06-30: 9,210 ฉบับ (ดาวน์โหลดครบ 9,210, ใช้เวลา 10:19–11:00 ในงบ 2 ชม.) → 8,395 คู่ปีต่อปี, 7,749 คู่ที่แยก Item 1A ได้; universe รายเดือนจาก `rounds/round_003/run.py::monthly_universe`; ผลใน `model_A/rounds/round_012/results.csv`, `coverage.csv`

**ผลลัพธ์:** ช่วงตัดสิน ก.ค. 2017 – มิ.ย. 2023 (net 10 bps), EW รายเดือน Sharpe 0.614, SPY 0.681
- r012_LAZY_COS_FULL: Sharpe 0.637, CAGR 12.2% (EW 12.2%), MaxDD −38.1% (EW −38.4%), S1 ตก (10/25 bps), S2 22%, DSR 0.002 (N=125), S6 เฉลี่ย 64.0 ต่ำสุด 50, ส่วนเกิน −0.2%/ปี NW t −0.19; ช่วง 2011–16 Sharpe 1.007 vs EW 1.093
- r012_LAZY_COS_1A: Sharpe 0.688, CAGR 13.7%, MaxDD −36.4%, S1 ตก, S2 95%, DSR 0.039, S6 60.0/50, ส่วนเกิน +1.3%/ปี NW t 1.04; ช่วง 2011–16 Sharpe 0.854 vs EW 1.093
- similarity: cosine ทั้งเอกสาร median 0.999 (IQR 0.998–0.999), Item 1A median 0.998 (IQR 0.995–0.999); corr(cosine, Jaccard) 0.39 / 0.57
- ไม่มีผู้เข้ารอบ; trial สะสม 125

**มุมมอง/การตีความ:** Item 1A ให้ทิศทางเดียวกับงานต้นฉบับ (Cohen, Malloy & Nguyen 2020) แต่อ่อนและไม่มีนัยสำคัญ (t 1.04) และแพ้ EW ช่วง 2011–16 → สอดคล้องกับความคาดหวังต่ำใน EXPLORE2 (ผลหลังตีพิมพ์ในหุ้นใหญ่อ่อน); cosine ของความถี่คำดิบถูกคำทั่วไปครอบงำจนแทบทุกฉบับ ≈ 0.999 จึงแยกบริษัทได้น้อย โดยเฉพาะทั้งเอกสาร — ไม่ได้ลอง TF-IDF/ตัด stop-word เพราะจะเป็นการปรับหลังเห็นผล (ต้องนับเป็น trial ใหม่)

**ขั้นต่อไปที่ควรลอง:** EXPLORE2 ครบทุก track แล้ว (ทุกกฎระดับ C, held-out ยังไม่แตะ) — รอคำสั่งผู้ใช้; ถ้าจะลอง TF-IDF ต้องเขียน HYPOTHESIS ใหม่และนับ trial ต่อจาก 125
---

---
## Model A EXPLORE2 round 009 — T2 factor momentum (บันทึกย้อนหลัง: ตกหล่นตอนรัน พบและเพิ่ม 2026-09-27 11:10) — 2026-09-27

**วิธีที่ใช้:** ขั้น 1 (ไม่นับ trial): Ken French 6 ภูมิภาค ทุกเดือนถือเฉพาะ factor ที่ผลตอบแทน 12 เดือนย้อนหลังเป็นบวก (FMOM) เทียบถือทุก factor เท่ากัน; ขั้น 2 (1 trial): ทุก มิ.ย. ใช้เฉพาะสัญญาณ (Q_LOWACC, V_EP, Q_GPA, A_SHY, C_MOM) ที่ spread Q5−Q1 ปีก่อนเป็นบวก แล้ว rank-average เลือก top 20% EW รายปี — ต่างจาก round ก่อนตรงที่สลับสัญญาณตามผลปีก่อนแทนสเปกคงที่

**ข้อมูลที่ใช้:** Ken French regional 5 factors + momentum (US 1964-07 ถึง 2023-06, ภูมิภาคอื่นเริ่ม 1990–1991); panel S&P 500 รายปี (`lib/panel.py`); ผล `model_A/rounds/round_009/results.csv`, `stage1_french.csv`, `stage2_signal_selection.csv`

**ผลลัพธ์:** ขั้น 1: FMOM ผลตอบแทนเฉลี่ยสูงกว่าถือเท่ากันทั้ง 6 ภูมิภาค (+1.3 ถึง +2.7%/ปี, t 1.6–3.5) แต่ Sharpe ต่ำกว่าใน 5/6 (เช่น US 0.730 vs 0.861). ขั้น 2: r009_FMOM_SIGNALS Sharpe 0.597 (EW 0.640, SPY 0.681), CAGR 11.8% (EW 12.5%), MaxDD −35.1% (EW −37.6%), S1 ตก, S2 51%, DSR 0.003 (N=119), S6 79.1/50; ช่วง 2011–16 Sharpe 0.962 vs EW 1.137

**มุมมอง/การตีความ:** spread ของสัญญาณปีก่อนสลับเครื่องหมายบ่อยใน S&P 500 (momentum +0.241 ปี 2020 → −0.478 ปี 2021) จึงไม่ช่วยเลือกสัญญาณปีถัดไป; factor momentum ระดับโลกเพิ่มผลตอบแทนแต่กระจุก factor น้อยตัวจน Sharpe ไม่ดีขึ้น

**ขั้นต่อไปที่ควรลอง:** T5 value+momentum+quality (round 010)
---

---
## Model A EXPLORE2 round 010 — T5 value + momentum + quality (บันทึกย้อนหลัง: ตกหล่นตอนรัน พบและเพิ่ม 2026-09-27 11:10) — 2026-09-27

**วิธีที่ใช้:** rank-average น้ำหนักเท่ากันของ accruals ต่ำ, earnings yield สูง, momentum 12-1 สูง จัดอันดับภายใน sector, top 20% (ขั้นต่ำ 50) EW; 2 trial = rebalance รายปี (A) และรายไตรมาส (Q) — สเปกเดียวไม่จูน ต่างจาก SHYQMOM (round 003) ตรงที่มี value และเป็น sector-neutral

**ข้อมูลที่ใช้:** panel S&P 500 รายเดือน/รายปีเดิม (`rounds/round_003/run.py::monthly_universe`); ผล `model_A/rounds/round_010/results.csv`

**ผลลัพธ์:** r010_VMQ_sector_A Sharpe 0.476 (EW 0.640), CAGR 9.0% (12.5%), MaxDD −36.2% (−37.6%), S2 0%, DSR 0.000; r010_VMQ_sector_Q Sharpe 0.489 (EW 0.625), CAGR 9.2% (12.4%), MaxDD −37.7% (−37.7%), S2 0%, DSR 0.000 (N=121); ช่วง 2011–16 Sharpe 1.003 vs 1.137 และ 0.906 vs 1.108; ไม่มีผู้เข้ารอบ

**มุมมอง/การตีความ:** earnings yield (value) ถ่วงผลเหมือน round 001–003 ในยุคหุ้นเติบโตนำตลาด; การรวมกับ momentum ไม่ได้ทำให้นิ่งขึ้นในหุ้นใหญ่ช่วงนี้

**ขั้นต่อไปที่ควรลอง:** T3 insider buying (round 011)
---

---
## Model A EXPLORE2 round 011 — T3 opportunistic insider buying (บันทึกย้อนหลัง: ตกหล่นตอนรัน พบและเพิ่ม 2026-09-27 11:10) — 2026-09-27

**วิธีที่ใช้:** SEC Form 4 (Insider Transactions Data Sets) จัด insider เป็น routine/opportunistic ตาม Cohen, Malloy & Pomorski (2012) (ซื้อ/ขายเดือนเดียวกัน 3 ปีติด = routine) ใช้เฉพาะ code P วันใช้ได้ = วันยื่น Form 4; trial 1: สัญญาณเดี่ยว (มีการซื้อ opportunistic ใน 6 เดือน) รายเดือน EW; trial 2: ให้น้ำหนัก 2 เท่ากับหุ้นที่มีสัญญาณภายในพอร์ต accruals ต่ำ (r001_Q_LOWACC_overall) รายปี — แหล่งข้อมูลใหม่ที่ไม่ใช่งบ/ราคา

**ข้อมูลที่ใช้:** SEC Insider Transactions Data Sets 2006Q1–2023Q2 → 1,711,391 รายการ non-derivative ของบริษัท S&P 500 (`data/interim/insider_sp500.parquet` จาก `lib/insider.py`); insider-year ที่จัดกลุ่มได้ 31,760 (opportunistic 69.0%); ไม่มีธง 10b5-1 ก่อน 2023; ผล `model_A/rounds/round_011/results.csv`, `signal_coverage.csv`

**ผลลัพธ์:** เดือนที่มีหุ้นสัญญาณ < 20 ตัว = 72.2% (median 16, min 6, max 39) → ใช้เป็นสัญญาณเดี่ยวกับ S&P 500 ไม่ได้; r011_INSIDER_OPP_BUY_M Sharpe 0.524 (EW 0.614), CAGR 11.3% (12.2%), MaxDD −40.6%, S2 11%, DSR 0.003, S6 16.7/6 (ตก); r011_LOWACC_INSIDER_TILT Sharpe 0.845 (EW 0.640), CAGR 18.5% (12.5%), MaxDD −37.3% (−37.6%), S1 ผ่าน, S2 100%, S6 63.3/51, DSR 0.471 (N=123) ตก S3; ช่วง 2011–16 Sharpe 0.806 vs 1.137

**มุมมอง/การตีความ:** ผู้บริหารหุ้นใหญ่ซื้อหุ้นตัวเองแบบ opportunistic น้อยมาก สัญญาณจึงบางเกินไป; ตัวเอียงน้ำหนักกระทบเฉลี่ยแค่ 3.3 หุ้นต่อรอบ ผลจึงแทบเท่าตัวฐาน (0.863)

**ขั้นต่อไปที่ควรลอง:** T4 Lazy Prices (round 012)
---

---
## Sandbox v2 W3 — engine validation + pipeline run แรก (A1 → B stub → C rulebase-exp03 → equal_weight_A) — 2026-09-27 13:05

**วิธีที่ใช้:** engine ใหม่ของ sandbox v2 (`sandbox/v2/engine.py`): อ่าน signal ที่ precomputed เท่านั้น, ตัดสินใจ close วัน t → execute close วัน t+1 (Adj Close), cost 0.10%/ขา, rebalance เฉพาะวันที่เป้าน้ำหนักเปลี่ยน, condition รันใน process แยก (ได้ข้อมูล ≤ t ทีละวัน) — ไม่ใช่การประเมินกลยุทธ์ เป็นการตรวจความถูกต้องของระบบ; ไม่นับเป็น trial ของ Model A

**ข้อมูลที่ใช้:** ราคา yfinance 575 ticker (`sandbox/v2/data/prices/`, 2021-09-27 → 2023-06-30 = 443 วันทำการ, ok 564/partial 11/missing 0); signal A1 จาก `model_A/export/A1_r001_Q_LOWACC_overall/signals.parquet` (สร้างโดย `export/build_history.py`), B stub, C `model_c_rulebase/export/rulebase-exp03/signals.parquet`

**ผลลัพธ์:**
- export ของ Model A: holdings จาก signal ทั้ง 5 กฎ (A1–A5) + backtest engine เดิมของ Model A → NAV ตรงกับ `r001/r004_nav.parquet` (max rel diff ≤ 6e-15)
- sanity `hold_SPY`: equity ต่างจาก SPY buy & hold − cost ที่คำนวณอิสระ < 1e-4 (test ผ่าน), total return 4.91% = SPY 4.91%
- A1 filter + `equal_weight_A` เทียบ NAV ของ Model A ช่วงถือรอบ มิ.ย. 2022 (2022-07-05 → 2023-06-30): ผลตอบแทนสะสม 20.09% vs 19.92%, correlation ผลตอบแทนรายวัน 0.99999, ต่างรายวันสูงสุด 2.3e-4
- A1 filter เดี่ยว ทั้งช่วง: total return 14.17%, Sharpe 0.340, MaxDD −19.85%, 194 trades (SPY 4.91%, EW universe 5.87%)
- pipeline DoD (A1 filter + B stub filter + C rb03 filter + equal_weight_A): total return 10.69%, CAGR 5.96%, Sharpe 0.258, MaxDD −30.84%, trades 12,767, turnover 16.5 เท่า/ปี, ค่าธรรมเนียมรวม 60,587 (6.1% ของทุน); funnel เฉลี่ย 552 → A 74.1 → B 64.4 → C 34.6 → ถือ 34.6
- pytest `sandbox/v2/tests` 19/19 ผ่าน (look-ahead, sanity, held-out guard, condition พัง/วนลูป/น้ำหนักเกิน, cancel)

**มุมมอง/การตีความ:** engine ให้ผลตรงกับ backtest ของ Model A ในจุดที่เทียบได้ ส่วนต่างเล็กน้อยมาจาก execution ช้ากว่า 1 วันและแหล่งราคาต่างกัน; pipeline ที่มี B stub/C กรองรายวันทำให้รายชื่อเปลี่ยนเกือบทุกวัน → `equal_weight_A` rebalance บ่อยมาก ค่าธรรมเนียมกินผลตอบแทน — B เป็น stub และ C เป็น negative result ตัวเลขนี้จึงไม่มีความหมายทางการลงทุน ใช้ยืนยันว่า pipeline ทำงานเท่านั้น ช่วงราคา 5 ปีให้ A รายปีได้แค่ 2 รอบ

**ขั้นต่อไปที่ควรลอง:** W4 persistence + reproducibility test; พิจารณาขยาย PRICE_START เป็น 2010-06-01 เพื่อให้ A มีหลายรอบ
---

---
## Sandbox v2 W7 — auto-detect หุ้น/ข่าวมหภาคในข่าว manual — 2026-09-27 14:10

**วิธีที่ใช้:** rule-based (`sandbox/v2/news.py::detect`): @mention, `$TICKER`/`(TICKER)`, alias จากชื่อบริษัท S&P 500 (ตัด Inc./Corp./Co. ฯลฯ, ไม่ใช้ชื่อสั้นที่เป็นคำทั่วไป เช่น News/Match/Target) + alias เพิ่มเอง (ชื่อเล่น/ชื่อไทย), ticker พิมพ์ใหญ่ลอย ๆ ≥3 ตัวที่ไม่อยู่ใน stopword; keyword มหภาค (Fed/FOMC/CPI/tariff/jobs/GDP/yields/ดอกเบี้ย ไทย) → แนะนำข่าว C — ผลทั้งหมดเป็น "ข้อเสนอ" ผู้ใช้ต้องยืนยัน ไม่ใช่โมเดล ML

**ข้อมูลที่ใช้:** `sandbox/v2/tests/mention_samples.json` 10 ข้อความ (อังกฤษ 9 / ไทย 1, expected 15 ticker, macro 4 ข้อความ) เขียนก่อนวัดผล ไม่ได้ปรับ alias ตามชุดนี้; alias จาก `sandbox/v2/data/sp500_snapshot.csv`

**ผลลัพธ์:** ticker ถูก 14 · ผิด 1 (false positive: "Nasdaq" ดัชนี → NDAQ) · พลาด 1 ("Target" → TGT ถูกกันไว้เพราะเป็นคำทั่วไป) · precision 0.93 · recall 0.93; แนะนำข่าวมหภาคถูก 10/10

**มุมมอง/การตีความ:** ชุดทดสอบเล็กมาก (10 ข้อความ) ตัวเลขนี้แค่บอกว่าใช้งานได้ ไม่ใช่การประเมินที่เชื่อถือได้; จุดอ่อนหลักคือชื่อบริษัทที่ชนกับคำทั่วไป/ชื่อดัชนี ซึ่งเป็น trade-off ระหว่าง false positive กับ recall — เพราะทุกผลต้องให้ผู้ใช้ยืนยันอยู่แล้ว ความเสียหายจาก false positive จึงต่ำ

**ขั้นต่อไปที่ควรลอง:** เพิ่มชุดทดสอบให้ใหญ่ขึ้น (≥100 หัวข่าวจริง) ก่อนตัดสินใจปรับ alias/stopword
---

---
## Sandbox v2 F3 — ขอบเขตการลงทุน (all / 1 sector / 1 ticker) ด้วย A1 filter + equal_weight_A — 2026-09-28 06:05

**วิธีที่ใช้:** เพิ่ม "ขอบเขตการลงทุน" ก่อนกล่อง A ใน engine ของ sandbox v2 — สัญญาณ A อ่านจาก export ที่จัดอันดับจากทั้ง universe แล้วค่อยกรองเหลือหุ้นใน scope (ไม่จัดอันดับใหม่), EW benchmark = EW ของหุ้นใน scope, SPY ไม่เปลี่ยน; รัน 3 กรณีเทียบกัน (config เดียวกันทุกอย่างนอกจาก scope) — เป็นการตรวจความถูกต้องของฟีเจอร์ ไม่ใช่การประเมินกลยุทธ์ และไม่นับเป็น trial ของ Model A

**ข้อมูลที่ใช้:** ราคา yfinance 575 ticker (`sandbox/v2/data/prices/`, 2021-09-27 → 2023-06-30 = 443 วันทำการ); signal `A:A1_r001_Q_LOWACC_overall` (2 รอบ rebalance ในช่วงนี้); scope sector XLE = 21 หุ้น (GICS Energy ตาม `universe_manifest.json`), scope ticker = NVDA (และ XOM ใน pytest)

**ผลลัพธ์:**
- scope = all: funnel เฉลี่ย 552.2 → A 74.1 → ถือ 74.1; total return 14.17%, Sharpe 0.340, MaxDD −19.85%, 194 trades; EW (ทั้ง universe) 5.87%, SPY 4.91% — **metrics/equity/trades/funnel/positions ตรงกับ engine ก่อน F3 ทุกไบต์** (ตรวจ 2 config: A1+EW และ A5+B stub+C rb03)
- scope = sector XLE: funnel ขอบเขต 21.0 → A 10.4 → ถือ 10.4 (ตลาดรวม 552.2); total return 66.47%, Sharpe 0.892, MaxDD −30.82%, 23 trades; **EW ของ 21 ตัว XLE 60.33%** (Sharpe 0.900) — เทียบ EW ทั้งตลาด 5.87% ต่างกันมาก; SPY 4.91%
- scope = NVDA: funnel ขอบเขต 1 → A 0 → ถือ 0 ทุกวัน (A1 ไม่เลือก NVDA ทั้ง 2 รอบ) → พอร์ตเป็นเงินสด 100% ตลอด, return 0.00%; EW ของ NVDA ตัวเดียว 104.43% (MaxDD −66.34%); ระบบเตือนก่อนรัน + หน้าผลแสดง "หุ้นที่เลือกไม่ผ่านเกณฑ์ A ในช่วงเวลานี้"
- pytest `sandbox/v2/tests` 71/71 ผ่าน (รวม test_scope 18 ข้อ: funnel ขั้นแรก = จำนวนหุ้นใน scope ที่มีราคาทุกวัน, EW = `_bench_ew` ของหุ้นใน scope ทุกค่า, บันทึก → restart → เปิดใหม่ scope เดิม, record A ใน scope = record เดียวกับไม่จำกัด scope)

**มุมมอง/การตีความ:** ในช่วงนี้ (ก.ย. 2021 – มิ.ย. 2023) หุ้นพลังงานขึ้นแรงทั้งกลุ่ม — ผล 66% ของ scope XLE จึงมาจากตัวกลุ่มเป็นหลัก (EW ของกลุ่มเองได้ 60%) ส่วนต่าง vs EW ขอบเขต (+6.1 จุด) คือสิ่งที่ A1 เพิ่มให้จริง ถ้าเทียบกับ EW ทั้งตลาด (5.87%) จะดูเหมือน A เก่งเกินจริง — ยืนยันเหตุผลที่ต้องให้ EW ตาม scope; ข้อมูลแค่ 2 รอบ rebalance และ 21 ตัว จึงยังสรุปอะไรเรื่องฝีมือ A ในกลุ่มพลังงานไม่ได้; Sharpe −20 ของกรณี NVDA เป็นผลของสูตร (excess return = −rf ทุกวัน, volatility ≈ 0) ไม่ใช่ความเสี่ยงจริง

**ขั้นต่อไปที่ควรลอง:** ขยาย PRICE_START เป็น 2010-06-01 เพื่อให้เทียบ A ราย sector ได้หลายรอบ; แสดง Sharpe เป็น "—" เมื่อพอร์ตไม่เคยลงทุน
---
