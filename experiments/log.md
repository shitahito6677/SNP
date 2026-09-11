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
