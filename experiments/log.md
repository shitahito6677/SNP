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
