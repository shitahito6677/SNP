# DECISIONS NEEDED — Sandbox v2

รูปแบบ: เรื่อง / ตัวเลือก / เลือกอะไรไป / ย้อนกลับยังไง
(โหมด unattended: เลือกทางที่ย้อนกลับง่ายที่สุดแล้วทำต่อ — ผู้ใช้ตรวจทีหลังได้)

## 1. `model_c_rulebase/` ไม่อยู่บน branch ฐาน (PR #1/#2 ยังไม่ merge)
- ตัวเลือก: (ก) merge branch PR #2 เข้ามา (ข) copy เฉพาะโฟลเดอร์ `model_c_rulebase/` แบบไม่แก้ (ค) รอ merge
- **เลือก (ข)** — commit `c3dede5`, ไฟล์ byte-identical กับ branch PR → merge PR ทีหลังไม่ conflict
- ย้อนกลับ: `git revert c3dede5` (และ build_export/manifest ของ C จะหายไปด้วย)

## 2. ช่วงราคา 5 ปี (PRICE_START = 2021-09-27) สั้นเกินสำหรับ rule รายปี
- ช่วงก่อน held-out มีแค่ ~21 เดือน → Model A รายปี rebalance ได้แค่ 2 รอบ (มิ.ย. 2021 ที่ถือต่อมา, มิ.ย. 2022)
- **เลือก:** default 5 ปีตามที่ผู้ใช้ขอ; เปลี่ยนเป็น `"2010-06-01"` ได้โดยแก้บรรทัดเดียวใน `sandbox/v2/config.py` แล้วรัน `python3 -m sandbox.v2.scripts.update_prices`
- ตัว signal ของ A สร้างไว้ครบตั้งแต่ 2011-06 อยู่แล้ว (ไม่ต้องสร้างใหม่เมื่อขยายช่วงราคา)

## 3. Model A execution timing ต่างจาก backtest เดิม
- Model A backtest: ซื้อที่ close วัน R / sandbox v2: `next_close` (R+1) ตามสเปค
- **เลือก:** ตามสเปค (next_close) — ผลไม่เท่ากับ NAV ของ Model A เป๊ะ; แสดงเป็นข้อจำกัดในหน้า About
- ย้อนกลับ: `EXECUTION` ใน config (ยังไม่รองรับ same-close — ถ้าต้องการต้องเพิ่ม)

## 4. Legacy v1 ไม่ mount เป็น blueprint
- v1 สร้าง `app` แบบ module-global และห้ามแก้ v1 → ลิงก์ไป `http://127.0.0.1:5050` (รัน v1 แยก)

## 5. Model C rulebase: `vix_p90` ใช้ข้อมูลทั้งช่วง (look-ahead เล็กน้อยใน exp_03)
- ไม่แก้โค้ด exp_03 (ห้ามแก้ข้อมูล/ผลของ exp_01–04) → ใช้ตามเดิมและติดป้ายใน manifest `notes`
- ถ้าต้องการ strict: เขียน export version ใหม่ที่คำนวณ `vix_p90` แบบ expanding window (ยังไม่ได้ทำ)

## 6. commit ไฟล์ signal (parquet) ของ export
- สเปคห้าม commit ราคา/parquet ของผลทดลอง แต่ signal ของโมเดลไม่ใช่ราคาดิบ และ **สร้างใหม่ไม่ได้ถ้าไม่มี `model_A/data/` (gitignored, 3 GB)**
- **เลือก:** commit `model_A/export/A*/signals.parquet` (~3.8 MB), `model_c_rulebase/export/rulebase-exp03/signals.parquet`, `sandbox/v2/stubs/*` (~0.3 MB)
- ย้อนกลับ: เพิ่ม `model_A/export/*/signals.parquet` ใน .gitignore แล้ว `git rm --cached`

## 7. Model C rulebase: ช่วง sandbox อยู่ใน test set ของ exp_03 ทั้งหมด
- exp_03 แบ่ง train/test ตามเวลา: test เริ่ม **2020-12-02** และ R5 "ห้ามแตะ test set จนกว่า R6 เสร็จ" — R6 ตัดสินแล้ว (negative, ไม่ calibrate)
- การรัน sandbox ด้วย C rulebase-exp03 = ดูผลของ engine (ที่ไม่ได้ calibrate) บนช่วง test → **ไม่ควรเอาผล sandbox ไปปรับ engine ของ exp_03**
- ติดคำเตือนใน manifest + reasons ของทุกแถวที่อยู่ใน test set แล้ว

## 8. class ของ C rulebase: neutral band ±0.10
- engine ให้ score ต่อเนื่อง ไม่มี class → ตั้ง |score| ≤ 0.10 = neutral (ค่าแสดงผล **ไม่ได้ tune** กับผลตอบแทน)
- ย้อนกลับ/ปรับ: `NEUTRAL_BAND` ใน `model_c_rulebase/export/build_export.py` แล้วรันใหม่ (condition ใช้ `score` ดิบได้อยู่แล้ว)

## 9. (F1) ไฟล์ fixture `manual_news_sample.csv` — ไม่มีวางไว้ตอนเริ่มงาน
- สเปคบอกว่าผู้ใช้จะ copy ไฟล์มาวางที่ `sandbox/v2/tests/fixtures/` แต่ตอนเริ่มงานยังไม่มี
- เจอ 2 ไฟล์ที่ header ตรงกับที่สเปคบรรยาย: `~/Desktop/model_b_pilot_META_news.csv` (META ล้วน 9 แถว, 2021-10-25 → 2023-04-26) และ `~/Downloads/model_b_pilot_META_news.csv` (20 แถว, 7 ticker)
- **เลือก:** copy ไฟล์บน Desktop เป็น fixture — META ทุกแถวและช่วงวันที่ตรงกับสเปคเป๊ะ; **ไฟล์มี 10 บรรทัด = หัวตาราง 1 + ข่าว 9 แถว** (สเปคเขียน "10 แถว" — test ตรวจ 9 แถวตามไฟล์จริง)
- ไฟล์ 20 แถวใน Downloads ก็นำเข้าได้ครบ 20/20 (ตรวจด้วยมือ ไม่ได้ใส่ใน test)
- ย้อนกลับ: วางไฟล์ที่ถูกต้องทับ แล้วแก้ `EXPECTED_ROWS` ใน `tests/test_csv_import.py`

## 10. (F1) label ตัวเลข -2..+2 → สเกลภายใน
- ระบบเดิมใช้ 3 ระดับ `sentiment` ∈ {positive, neutral, negative} + `score` ∈ {1, 0, -1} (condition/B/C อ่านทั้ง `class` และ `score`)
- **เลือก:** class ตามเครื่องหมาย (>0 positive, 0 neutral, <0 negative); `score = label / สเกล` → -2 → **-1.0** (แย่สุด = เท่ากับข่าว negative ที่พิมพ์เอง), -1 → -0.5, +1 → +0.5, +2 → +1.0; เก็บค่าดิบใน `label_raw` + `label_scale` ("±2")
- สเกลอ่านจากหัว column (`(-2..+2)`) ถ้ามี ไม่งั้นใช้ |label| สูงสุดในไฟล์ (ปัดขึ้น); ค่านอกสเกล/ข้อความที่ไม่รู้จัก → ข้ามแถวพร้อมเหตุผล (ไม่เดา)
- ถ้าผู้ใช้เปลี่ยน sentiment ในหน้า preview → score กลับเป็น ±1/0 ตาม class (ค่าดิบยังเก็บไว้)
- ย้อนกลับ/ปรับ: `parse_label()` ใน `news.py`

## 11. (F1) หา 500 ของ CSV ตามภาพไม่เจอ — เจอแค่ 400
- รันไฟล์ fixture ผ่าน endpoint จริง (test client, server ที่ผู้ใช้เปิดอยู่ port 5090, server ใหม่แบบ cold start + request พร้อมกัน, และลากไฟล์ผ่าน UI ด้วย Playwright): **ได้ 400 `หา column headline ไม่เจอ` ทุกครั้ง ไม่ใช่ 500** (โค้ด news/server ไม่เปลี่ยนตั้งแต่ W7)
- root cause ของ "นำเข้าไม่ได้" ที่ยืนยันได้ = mapping เดิม match ชื่อ column แบบตรงตัว (`headline`, `title`…) → column `ข่าวแบบย่อ (short_news)` ไม่ match เลย
- 500 ในภาพอาจมาจาก request อื่น/สถานะอื่นที่ reproduce ไม่ได้ → **ไม่เดา**; ใส่ global error handler: exception ใด ๆ → JSON ภาษาไทย + `error_id` + traceback เต็มใน `sandbox/v2/logs/server.log` — ถ้าเจออีก ให้ค้น `error_id` ใน log

## 12. (F2) หน้าหุ้น META "HTTP 500" — root cause ที่ reproduce ได้คือช่วงวันที่ใน held-out (ไม่เฉพาะ META)
- reproduce ด้วย query เดียวกับที่ UI ส่ง: `/api/stock/META` (ไม่มีบริบท / A1+C default / ทุก 26 run + 1 exp ที่มีในเครื่อง) = 200 ทุกครั้ง; sweep ทุก 575 ticker = ไม่มี exception
- **ที่ 500 จริง:** `/api/stock/<ทุก ticker>?start=2026-08-14&end=2026-11-12` → traceback: `stock_view.build` ตัด `end` เหลือ `DEFAULT_END` (2023-06-30) เพราะ held-out แต่ไม่ตัด `start` → `prices.check_range` raise `ValueError: start 2026-08-14 > end 2023-06-30` → endpoint จับแค่ `KeyError` → 500 HTML ดิบ
- ใครเรียกแบบนั้น: mini chart ของหน้าเพิ่มข่าว (±45 วันรอบวันที่ข่าว) — พิมพ์ `@meta` + วันที่ข่าวหลัง ~2023-08-14 → กล่องกราฟขึ้น `HTTP 500` (ตรงกับอาการ "พิมพ์ @meta แล้วเลือก → 500")
- **เลือก:** ช่วงที่อยู่ใน held-out ทั้งหมด → 200 + bars ว่าง + หมายเหตุ "ล็อกไว้" (UI เดิมมีข้อความรองรับอยู่แล้ว); คร่อม → ตัดที่ DEFAULT_END + หมายเหตุ
- manifest ปัจจุบัน **ไม่มี status `missing`** (ok 564 / partial 11) → test ของ missing ใช้ manifest จำลอง 1 รายการ

## 13. (F3) ขอบเขตการลงทุน — การออกแบบ
- **กรองหลังอ่าน A:** `stage_day()` อ่าน snapshot ของ A (ranking ทั้ง universe ที่ precomputed ใน export) แล้วค่อยตัดเหลือ scope — ไม่มีโค้ดจัดอันดับใหม่ใน sandbox เลย (test ยืนยันว่า record ของ A ใน scope เท่ากับตอนไม่จำกัด scope ทุกตัวอักษร)
- **ราคา/columns ที่ส่งให้ condition ไม่ถูกตัด** (ยังเห็นราคาทุกตัว + ETF) — scope จำกัดแค่ `ctx.universe` และสิ่งที่ซื้อได้; ETF ยังซื้อได้เหมือนเดิม
- **sector ของ scope = GICS ใน `universe_manifest.json` (snapshot S&P 500 ปัจจุบัน)** — หุ้นที่หลุด index แล้ว 59 ตัวไม่มี GICS ย้อนหลัง (sector = Unknown) → อยู่ได้เฉพาะ scope "ทั้งตลาด"; scope ราย sector จึงมี survivorship bias มากกว่า "ทั้งตลาด" เล็กน้อย
- **backward compatible:** scope = all → metrics/equity/trades/funnel/positions ตรงกับ engine ก่อน F3 ทุกไบต์ (ตรวจแล้ว 2 config) — key ใหม่ (`funnel.market`, `metrics.scope`) ใส่เฉพาะเมื่อจำกัด scope เพื่อให้ Re-run การทดลองเก่าได้ "REPRODUCED"
- **EW เมื่อ scope ยังไม่มีราคาวัน rebalance** (เช่นหุ้น IPO ตัวเดียว) → ถือเงินสดรอบนั้น (เดิมจะหารด้วยศูนย์) — ไม่กระทบ scope = all
- "พอร์ตว่าง" คำนวณตอนเปิดผล (`experiments_store.empty_reason`) จาก funnel ไม่ได้เขียนลง metrics.json

## 14. (F1b) แก้ #10 — label 5 ระดับเป็นค่าหลัก ไม่ยุบเหลือ 3 กลุ่ม (ผู้ใช้สั่ง)
- **เดิม (#10):** เก็บ `sentiment` 3 กลุ่มเป็นหลัก + `score = label/2`, ค่า -2..+2 เป็นแค่ metadata (`label_raw`) → หน้า preview/hover/trade reasons แสดง +1 กับ +2 เป็น "positive" เหมือนกัน
- **ตอนนี้:** ข่าว manual เก็บ `label` (int -2..+2) เป็นฟิลด์หลัก ไม่เก็บ `sentiment`/`score` ซ้ำ; ตอนสร้าง record ของ signal ค่อย derive `class` (≤-1 negative / 0 neutral / ≥1 positive) + `score = label/2` สำหรับเกณฑ์กรองแบบ Model B เท่านั้น; record มี `label` + `label_text` ให้ condition และ trade reasons
- ข่าวที่พิมพ์เอง: ฟอร์มเปลี่ยนเป็น 5 ปุ่ม; API ยังรับ `sentiment` แบบเดิม (→ +1/0/-1) เพื่อไม่ให้ของเดิมพัง
- **ข่าวที่บันทึกไว้แล้วไม่ต้องแก้ไฟล์:** `label_of()` อ่านได้ทุกรูปแบบ — `label` → ใช้เลย; `label_raw` + `label_scale` (ข่าว 463 แถวที่ผู้ใช้นำเข้าช่วง F1 แรก เวลา 06:19) → คืนความแรงเดิม (ตรวจแล้ว: ทั้ง 463 แถว label = label_raw, กระจาย -2:32 · -1:22 · 0:160 · +1:147 · +2:102); `sentiment` อย่างเดียว (ข่าวพิมพ์เองรุ่นเก่า) → +1/0/-1 (ความแรงเดิมไม่มีให้กู้)
- ผลต่อ backtest: ข่าว manual ที่พิมพ์เอง "negative" เดิม score -1.0 → ตอนนี้ label -1 → score -0.5 (ความแรง -1.0 สงวนไว้ให้ -2) — มีผลเฉพาะเงื่อนไขที่ใช้ `min_score` หรืออ่าน `score` ของข่าว manual

## 15. (G1) กล่อง A/B/C = เปิด/ปิด + version — ผลเก่าที่ใช้เกณฑ์ในกล่อง
- **mode ใหม่:** `off` / `on` เท่านั้น; A on = `class == selected AND applicable` ของ version ตรง ๆ; B/C on = แนบสัญญาณ ไม่ตัดหุ้น (C เดิมมีปุ่มกรองแบบเดียวกับ B → เอาออกด้วย)
- **ผลเก่า (config มี `filter`/`score-only`/`criteria`):** เลือกทาง **read-only + ยืนยันก่อน Re-run** (ไม่ auto-migrate เป็น condition snippet) — เหตุผล: การห่อ condition เดิมด้วยตัวกรองเปลี่ยนทั้ง funnel, `ctx.universe` ที่ condition เห็น และ reasons ของ trade ทำให้ผลไม่เท่าเดิมอยู่ดีในหลายกรณี และเสี่ยงสร้างโค้ดที่ผู้ใช้ไม่ได้เขียน
  - เปิดผลเก่า: กราฟ/metrics/trade มาจากไฟล์ที่บันทึกไว้ → เหมือนเดิมทุกอย่าง + แถบ LEGACY บอกว่าอะไรเปลี่ยน
  - config ที่ **เทียบเท่าพอดี** (A filter + เกณฑ์ default selected, B/C score-only หรือ off) → แปลงเงียบ ๆ เป็น on/off และ **รันซ้ำได้ผลเดิมทุกไบต์** (ตรวจแล้ว 4 config เทียบ engine ก่อน G1: metrics/equity/trades/funnel/positions ตรงกัน) — ผลจริงในเครื่อง `20260928-065141_elk-nonb` (A1 + XLK) อยู่กลุ่มนี้
  - ที่ทำแบบเดิมไม่ได้ (A min_score / class_in อื่น, A score-only → รันเป็น A ปิด, B/C filter → รันเป็นแนบคะแนน) → API `/rerun` คืน 409 พร้อมรายการ; UI ถามยืนยัน → `?force=1` → config ใหม่มี `legacy_migration` + คำเตือน LEGACY
  - ย้อนกลับ/ทำ migration จริงทีหลัง: `engine.legacy_notes()` มีข้อมูลเกณฑ์เดิมครบ
- **B ไม่มีข่าว → `applicable: False` (score/class = None, date = None)** แทนการไม่มี key — ไม่ใส่ date ของวันนี้ เพื่อไม่ให้ condition ที่เช็ค "ข่าววันนี้" (`b["date"] == ctx.date`) ทำงานผิด
- **สัญญา B: score -2..+2** → B stub เดิมเก็บ "ความมั่นใจ" 0.34–0.99 → แปลงในที่ (class เดิมทุกแถว): positive → +1/+2, negative → -1/-2 (ความมั่นใจ ≥ 2/3 = แรง), neutral → 0; `build_stubs.py` ใช้สูตรเดียวกัน; registry ปฏิเสธ B ที่ score นอก -2..+2 — ผลเก่าที่ใช้ B stub: metrics เท่าเดิมถ้า condition ใช้ `class` (เช่น B_filter_then_EW) แต่ตัวเลข score ใน reasons เปลี่ยน
- ข่าว manual (toggle รวมข่าว manual): `score` = label -2..+2 (เดิม label/2 ตาม #14) ให้ตรงสัญญา B
- ตัวเลข "ผ่าน N ตัว" ก่อนรัน = ณ วันทำการสุดท้ายของช่วงที่เลือก (ไม่ใช่ค่าเฉลี่ย) — หลังรันเปลี่ยนเป็นค่าเฉลี่ยต่อวันจาก funnel
- `AsOf`: `max_age_days: 0` เดิมถูกตีความเป็น "ไม่กำหนด" (3,650 วัน) → แก้ให้ 0 = point-in-time (ไม่มี version เดิมใดใช้ 0)

## 16. (G2) B version จากข่าว manual — build อัตโนมัติ ไม่ commit
- สร้างโดย `sandbox/v2/manual_labels.py` → `model_B/export/manual-labels/{manifest.json, signals.parquet}` จาก `manual_news.jsonl` (ข้อมูลส่วนตัว gitignored) → **gitignore ผลที่สร้างด้วย** (`model_B/export/manual-labels*/`); build ใหม่ตอน server start, หลังเพิ่ม/ลบ/นำเข้าข่าว และตอนกด Rescan (เขียนไฟล์เฉพาะเมื่อ `content_sha256` เปลี่ยน)
- `created_at` ของ manifest = เวลาของข่าวล่าสุดที่ใช้ (ไม่ใช่เวลา build) → rebuild ด้วยข่าวชุดเดิมไม่ทำให้ Re-run บอกว่า "signal ถูกสร้างใหม่"
- **point-in-time** (`max_age_days: 0`) ตามสเปค — วันที่ของสัญญาณ = `effective_date` ของข่าว (วันทำการที่ข่าวมีผล; ข่าวเสาร์-อาทิตย์ → จันทร์) — เหตุผลอยู่ใน manifest `notes`
- ข่าวหลายรายการของหุ้นเดียวกันในวันเดียว (key ซ้ำไม่ได้) → label เฉลี่ยปัดครึ่งออกจาก 0 + reasons เก็บทุกข่าวและบอกวิธีรวม — ถ้าต้องการกติกาอื่น (เช่น ตัวแรงสุด) แก้ `_rows()`
- ไม่มีข่าวเลย → version ยังอยู่ (เลือกได้) แต่ว่าง + คำเตือน; ทุกวัน applicable False
- test ใช้โฟลเดอร์ export ชั่วคราว (`tests/conftest.py`) ไม่ทับไฟล์ที่ build จากข่าวจริง

## 17. (G2b) แยก Oracle (hindsight) ออกจาก real-time
- ข่าว manual มี `label_method` ∈ {hindsight, real_time, unknown}; **ไม่ระบุ = unknown และไม่เข้า version ใดเลย** (ไม่เดาให้) — ข่าว 463 รายการที่ผู้ใช้นำเข้าเมื่อ 2026-09-28 06:19 ยังเป็น unknown ทั้งหมด (label_reason บางรายการอ้างผลราคาจริง แต่ระบบไม่ตัดสินแทน) → ผู้ใช้ระบุได้ทีละชุดในหน้าเพิ่มข่าว
- version `manual-labels` (G2) ถูกแทนด้วย `manual-labels-oracle` + `manual-labels-realtime` (โฟลเดอร์เก่าถูกลบตอน build) — ผลที่บันทึกด้วย `B:manual-labels` (ถ้ามี) เปิดดูได้ แต่ Re-run จะ error "ไม่พบ version" (version นั้นปนสองประเภท ไม่ควรรันซ้ำ)
- `contains_oracle_signal` = ใช้ B/C version badge oracle **หรือ** toggle "รวมข่าว manual" ดึงข่าว hindsight เข้ามา (อีกทางที่ข่าวรู้ผลล่วงหน้าจะเข้าสู่ pipeline ได้) + `manual_label_methods` นับจำนวนตามวิธี; ผลเก่าที่ไม่มี field นี้ = false เว้นแต่ version เป็น oracle
- ORACLE ติดเป็น badge แรกของผล (gallery/compare/หน้าผล) + แถบเตือนบนสุดของหน้าผล; preflight เตือน ORACLE / unknown ก่อนรัน
- สี: ORACLE = ม่วงบานเย็น (#D946EF) ต่างจากทุก badge; MANUAL = ฟ้า

## 18. (I2) แหล่งโลโก้บริษัท = Wikidata → Wikimedia Commons
- ตัวเลือกที่พิจารณา: Clearbit Logo API (ปิดบริการ free logo แล้ว), logo API เชิงพาณิชย์อื่น (ต้องสมัคร key/ToS จำกัด), ชุดโลโก้ ticker บน GitHub (license ไม่ชัด) → **เลือก Wikidata (CC0) property P154 "logo image" ของบริษัทที่มี ticker (P249) บน NYSE/NASDAQ → ไฟล์บน Wikimedia Commons** (Commons รับเฉพาะไฟล์ที่ license อนุญาตให้ใช้ซ้ำ; เก็บ license/ผู้สร้างทุกไฟล์ใน `static/logos/ATTRIBUTION.json` และแสดงเครดิตเมื่อชี้ที่โลโก้ — จำเป็นสำหรับไฟล์ CC BY/BY-SA ~14 ไฟล์)
- มารยาทกับ server: User-Agent ระบุโปรเจค (URL ของ repo — ไม่ใส่อีเมลผู้ใช้), ยิงทีละ request หน่วง 0.5 วินาที, 429/5xx ถอยแล้วหยุด, ดึงครั้งเดียวแล้ว cache (`scripts/fetch_logos.py`) — ตัวที่เคยข้ามไม่ยิงซ้ำ (ต้องสั่ง `--retry-skipped`)
- **ไม่เดา mapping:** ใช้โลโก้เมื่อชื่อบริษัทใน Wikidata ตรงกับ universe_manifest (คำสำคัญตัวแรกตรง / คำทับกัน ≥ ครึ่งโดยไม่นับคำกว้าง ๆ เช่น American / label เป็น ticker เอง) และไม่กำกวมหลายบริษัท — เช่น `P` (Everpure) ไม่ใช้โลโก้ Pandora ที่เคยใช้ ticker เดียวกัน
- ผล: โลโก้จริง 382/547 หุ้น status ok (public domain 371 ไฟล์), ที่เหลือ = avatar อักษรย่อสีตาม sector (ไม่พบใน Wikidata 86, ไม่มีชื่อบริษัทให้ตรวจ 61, ชื่อไม่ตรง 12, กำกวม 6, ภาพถ่ายไม่ใช่โลโก้ 1 = CTSH) — รายละเอียดใน `static/logos/_fetch_report.json`
- ตรวจไฟล์ .jpg/.gif ทุกไฟล์ด้วยตา: CTSH เป็นภาพถ่ายป้ายบนอาคาร → ตัดออก (`EXCLUDE` ในสคริปต์)
- โลโก้เป็นเครื่องหมายการค้าของแต่ละบริษัท ใช้เพื่อระบุบริษัทในเครื่องมือวิจัยส่วนตัวเท่านั้น; โฟลเดอร์ cache gitignored (derived asset จากภายนอก)
- **ข้อผิดพลาดของผม:** ตอนเช็คว่าเข้าถึง Wikidata ได้ไหม (request ทดสอบ 1 ครั้ง) ผมใส่อีเมลของผู้ใช้ใน User-Agent — ไม่ควรทำ; สคริปต์จริงใช้ URL ของ repo แทน

## 19. (J1) วันเริ่มจากรอบ rebalance ของ A1 + backfill ราคาแบบไม่แตะแถวเดิม
- `compute_start_dates()` (config.py): ideal = วันนี้ − `IDEAL_LOOKBACK_YEARS` (5) → รอบล่าสุดของ A1 ที่ ≤ ideal (ได้จำนวนรอบมากสุด; ไม่มี → รอบแรก ≥ ideal) โดยไม่ใช้รอบใน held-out → `DECISION_START`; ถอย `INDICATOR_WARMUP_DAYS` (90) วันทำการตามปฏิทิน SPY จริง → `PRICE_START` (ถ้ายังไม่มีราคาช่วงนั้น ประมาณด้วยวันทำการ+วันหยุดราชการสหรัฐ +5 วันเผื่อ แล้วแม่นยำเองหลัง backfill)
- **อ่านวัน rebalance จาก signal file ที่ manifest ของ A1 ชี้ไป** — manifest เก็บแค่ coverage/จำนวนรอบ ไม่มีรายการวันที่ (ไม่แก้ export ของ Model A)
- วันนี้ 2026-09-28 → DECISION_START 2021-06-30, PRICE_START 2021-02-22 (ค่าจะเลื่อนเองเมื่อเวลาผ่านไป — ideal ข้าม 2022-06-30 ใน 2027-07)
- **ราคา:** `update_prices` เดิมดึงใหม่ทั้งช่วง (Adj Close ของ Yahoo เปลี่ยนย้อนหลังเมื่อมีปันผล → ผลเก่าจะรันซ้ำไม่ตรง) → เพิ่ม `--backfill-only`: ดึงเฉพาะช่วงต้นที่ขาด, ตรวจรอยต่อ (Close ต้องตรง, Adj Close rescale เข้า basis เดิมถ้าจำเป็น), ไม่เพิ่ม/ลด ticker, แถวเดิมไม่เปลี่ยน (ตรวจกับสำรองแล้ว 575 ไฟล์) — ครั้งนี้รอยต่อตรงกันทุกตัว; สถานะ ok 560 / partial 15 (บางตัวเริ่มหลัง PRICE_START ใหม่ → gallery เหลือ 547)
- stub A/B/C build ใหม่ให้ครอบช่วงต้น — แถวเดิมตรงกันทุกค่า (เพิ่มเฉพาะวันก่อนหน้า)
- **warm-up:** config ใหม่มี `warmup: {days, requested, start, end}`; engine ส่งราคา warm-up ให้ condition ด้วย `prices_only` ก่อนวันแรก (ไม่ตัดสินใจ/ไม่ซื้อขาย/ไม่อยู่ใน equity/metrics) + `provenance.warmup_data_hash`; ราคาไม่พอ → ลดวัน warm-up ตามที่มี + คำเตือน WARMUP
- **ผลเก่า:** เปิดดูใช้ไฟล์ที่บันทึกไว้ (ไม่คำนวณใหม่); Re-run ของ config ที่ไม่มี key `warmup` → `days: 0` = พฤติกรรมเดิม — ตรวจแล้วผลในเครื่องทั้ง 2 รายการรันซ้ำได้ identical
- ขอบล่างของวันเริ่ม = ราคาที่มีจริงในเครื่อง (`prices.data_start()`) ไม่ใช่ PRICE_START (ผลเก่าที่เริ่มก่อน PRICE_START ปัจจุบันยังรันซ้ำได้)
- **หมายเหตุ META:** ช่วงถือเงินสดต้นกราฟของ scope = META มาจาก A1 ไม่เลือก META ในรอบ 2021-06-30 — แก้ด้วยการเลื่อนวันเริ่มไม่ได้ (และไม่ควร)

## 20. (K1) กันข่าวซ้ำตอน import ไฟล์ที่โตขึ้นเรื่อย ๆ
- สเปคอ้างถึง H1/H2 (`claude_code_prompt_dedupe_manual_news.md`) ว่าทำไปแล้ว แต่ **ไม่พบใน repo/branch ใดเลย** (ไม่มี commit/ไฟล์) → K1 สร้าง flow "ต้องตรวจสอบ" (ข้าม / แทนที่ / เก็บทั้งคู่) เองแบบเรียบง่าย: ตัวเลือกต่อแถวในตาราง preview (ไม่มี popup) — ถ้าต้องการ flow แบบ H1 ตามสเปคเดิม ต้องส่งสเปคนั้นมา
- hash = `sha256(ticker|publish_date|normalize(headline))` ต่อ ticker (ข่าวหลาย ticker มีหลาย hash, ข่าวมหภาคไม่มี ticker ใช้ "macro"), `publish_date` = วันที่ข่าว (ไม่ใช่วันที่มีผล), headline ใช้ความยาวที่บันทึกจริง (500 ตัวอักษร) → เก็บใน `content_hashes`
- **exact** = hash ของทุก ticker มีอยู่แล้ว → ข้ามเงียบ ๆ (ทั้ง preview และ server ตรวจซ้ำตอน commit — ส่งแถวซ้ำมาก็ไม่เบิ้ล) · แถวซ้ำกันเองในไฟล์เดียวกัน → ตัวหลังข้าม
- **review** = (ticker, วันที่) ตรงกับข่าวที่มีอยู่ก่อน import แต่ headline ต่าง หรือซ้ำเฉพาะบาง ticker → ไม่บันทึกจนกว่าผู้ใช้เลือก (ไม่เดาแทน) — รวมกรณีแก้ typo ใน headline (hash ไม่ตรงเป๊ะ → ตรวจสอบ ไม่ข้ามเงียบ ๆ)
- ข่าวต่างหัวข้อของหุ้นเดียวกันวันเดียวกัน **ภายในไฟล์เดียวกัน** = คนละข่าว (ไม่เข้า review) — เทียบ review เฉพาะกับข่าวที่มีอยู่ก่อน import
- "แทนที่" = ข่าวเดิม `deleted: true, replaced_by: <id ใหม่>` (soft delete ย้อนกลับได้)
- migrate: ข่าวเดิมที่ยังไม่มี hash ได้ `content_hashes` ตอน server start (สำรองไฟล์เดิมเป็น `manual_news.jsonl.bak-before-content-hash` ครั้งแรก, gitignored) — ข่าว 463 รายการของผู้ใช้: ไม่มี hash ซ้ำ ไม่มี ticker+วันที่ซ้ำ
- ฟอร์มพิมพ์ข่าวเอง: ซ้ำเป๊ะ → ปฏิเสธพร้อมข้อความ (400)
- ประสิทธิภาพ: index แบบ dict (O(n)), commit เป็น batch อ่าน/เขียนไฟล์ครั้งเดียว (เดิมเขียนทั้งไฟล์ทุกแถว), ปฏิทินวันทำการ cache, แถวที่มี column ticker ไม่ต้องไล่ alias ~1,000 ตัว — 600 แถว preview+commit 0.36 วินาที; เพดานแถวต่อไฟล์ 2,000 → 20,000

## 21. (L1) ข่าว label_method = unknown — แก้แบบ bulk + เตือน (ไม่เปลี่ยนกติกาว่า unknown ไม่เข้า version ใด)
- กติกาเดิม (#17) คงไว้: unknown ไม่เข้าทั้ง B-manual และ B-oracle — ระบบยังไม่เดาแทนผู้ใช้ แต่ทำให้ **เห็นและแก้ได้ง่าย**
- ข่าวจริงของผู้ใช้: MU มีข่าว unknown 7 รายการ (ตรงกับอาการที่รายงาน) — ทั้ง 463 ข่าวยังเป็น unknown (ตรวจผ่านหน้าเว็บแบบสำรอง/คืนไฟล์ ไม่ได้แก้ข้อมูลจริงให้)
- ตัวกรองทำฝั่ง server (`/api/news?ticker=&sector=&date_from=&date_to=&method=`) — "เลือกทั้งหมดที่กรองอยู่" ส่งตัวกรองไปให้ server เลือกเอง (รายการบนหน้าแสดงสูงสุด 500 แถว แต่ข่าวมีมากกว่านั้นได้); `sector` = ข่าวของหุ้นใน sector นั้น + ข่าวมหภาคที่ติด sector นั้น
- ตั้งค่าแล้ว → build signal ของ `manual-labels-*` ใหม่ทันที (`content_sha256` เปลี่ยน → registry.scan ล้าง cache; `created_at` = updated_at ล่าสุด → cache AsOf ของ preflight ก็ไม่ค้าง); หน้าหุ้นล้าง cache ของตัวเองเมื่อข่าวเปลี่ยน
- คำเตือน: หน้าหุ้น (นับข่าว unknown ของหุ้นนั้น + ข่าวมหภาคของ sector ETF) พร้อมลิงก์ `#/news?method=unknown&ticker=…`; preflight เมื่อ B = manual-labels-* (นับในขอบเขต); หน้าผล (บันทึก `manual_unknown_news` ใน provenance ณ เวลารัน)

## 22. (L2) โหมดทดสอบ "จัดอันดับ A ใหม่เฉพาะใน scope"
- **สัดส่วนเดิมของกฎ = selected ÷ จำนวนที่กฎจัดอันดับจริงในรอบนั้น (applicable = `n_ranked`)** ไม่ใช่ ÷ universe ทั้งหมด (~500) ตามตัวอย่างในสเปค ("20 จาก 500 = 4%") — เหตุผล: ใน scope ก็ตัด applicable False ออกก่อนเหมือนกัน ตัวหารต้องเป็นกลุ่มเดียวกัน ไม่งั้นโหมดทดสอบจะเลือกน้อยกว่าความเข้มจริงของกฎ (A1 เลือก 20% ของที่จัดอันดับ แต่ 14.6% ของทั้งหมด); bmf20 = 20/344 ≈ 5.8% → XLK ได้ 3 ตัว (ตรงกับที่สเปคคาด "~3")
- ปัด: floor(n × สัดส่วน + 0.5) และอย่างน้อย 1 ถ้ามีหุ้น applicable ใน scope; scope มีแต่ applicable False → 0 ตัว (ไม่บังคับ 1)
- จัดอันดับด้วย score เดิมจาก export เรียงมาก→น้อย (เสมอกันเรียงตาม ticker); ตรวจแล้วทุกกฎยกเว้น A3 เลือกด้วย top-k ตาม score → scope ทั้งตลาดในโหมดนี้ได้ชุดเดิมพอดี; **A3 (BUFFER) มีเงื่อนไขพิเศษที่โหมดนี้ทำแทนไม่ได้** → คำเตือนเพิ่มเมื่อเลือก A3
- จัดอันดับในกลุ่มหุ้นใน scope ทั้งหมด (ไม่ขึ้นกับว่าวันนั้นมีราคาหรือไม่ — เหมือนโหมดทั้งตลาด) คงที่ตลอดรอบ rebalance
- record ที่ condition เห็น (`ctx.a`): `class`/`weight` ตามโหมดทดสอบ (weight = 1/k) + `global_class` (class จริงทั้งตลาด), `scoped_rank`, `scoped_n`, `ranking: "scoped"`; trade reasons ติด "[โหมดทดสอบ อันดับ r/k ใน scope · ทั้งตลาด …]"
- ไม่ใช่ค่าเริ่มต้น; config มี key `ranking` เฉพาะโหมดทดสอบ (config โหมดปกติเหมือนเดิมทุกตัวอักษร → ผลเก่ารันซ้ำเหมือนเดิม); `provenance.a_ranking_mode` = global / scoped ทุก run ที่เปิด A
- คำเตือน (ข้อความตามสเปค): แถบ sticky บนหน้า Pipeline (เมื่อเลือกโหมด), ในกล่อง A, หน้าผล (รวมผลที่บันทึกแล้วเปิดย้อนหลัง), หน้าหุ้นที่เปิดจากผลนั้น, badge อันแรกใน gallery/compare, คำเตือน preflight

## 23. (M1) ไม่รัน trial ใหม่ — "BM60/Fscore40 top-20" คือ trial 127 ที่มีอยู่แล้ว
- สเปค M1 บอกว่าเป็น "ไอเดียใหม่ที่ยังไม่เคยลองใน 125 trial" แต่บน `feature/model-a-rebuild` มี **round 013 (BMF20) กฎ S2_WEIGHTED = `r013_BMF20_WEIGHTED` เป็น trial ที่ 127** แล้ว (trials.csv มี 127 แถว ไม่ใช่ 125): เปอร์เซ็นไทล์ BM + เปอร์เซ็นไทล์ F-score ในปีนั้น, 0.6/0.4, top 20 EW, รายปี มิ.ย., ไม่รวมการเงิน, ข้อมูลประกอบ 2011–2016 + ตัดสิน 2017–2023, 10 และ 25 bps, S1–S7 + DSR, ไม่แตะ held-out — ตรงสเปค M1 ทุกข้อ
- ต่างกันแค่การตัดสินคะแนนเสมอ (สเปค: ticker A-Z · round 013: BM สูงกว่า) → **ตรวจแล้วรายชื่อ 20 ตัวเหมือนกันทุกปีทั้ง 12 ปี (ต่างกัน 0 ตัว)** จึงให้ผลเดียวกันทุกตัวเลข
- ผลที่บันทึกไว้แล้ว: Sharpe ช่วงตัดสิน 0.415 (EW 0.640, SPY 0.681), CAGR 9.6%, MaxDD −55.2%, ระดับ C (ตก S1/S2/S3/S6), DSR 0.003 — export `A:bmf20-weighted` (experimental-not-frozen) มีอยู่แล้วและ sandbox อ่านได้
- **เลือก:** ไม่รันซ้ำเป็น trial 128 — การนับสมมติฐานเดิมซ้ำทำให้จำนวน trial เกินจริงและลด DSR ของทุก trial (ขัดกติกา pre-registration ของ Model A); ไม่แตะ branch `feature/model-a-rebuild` / `trials.csv` / `CONCLUSION.md` · ใช้ `A:bmf20-weighted` ใน M2 และ Experiment 1
- ถ้าต้องการกฎที่ต่างจริง (เช่น น้ำหนักอื่น, universe อื่น, top-N อื่น) ให้ระบุ — จะเป็น trial ใหม่ได้
- `condition_fixed.py` ที่ขั้นตอน Experiment 1 อ้างถึง **ไม่มีในเครื่อง** (ไม่พบใน repo / Downloads / Desktop) — ไม่ได้สร้างให้ (ไม่รู้ว่าต้องการตรรกะไหน)

## 24. (M2) โหมดทดสอบ "Top-N คงที่ภายใน scope"
- โหมดที่ 3 ของกล่อง A (`ranking: "scoped_fixed_n"`, `n`): เรียงด้วย score เดิมเฉพาะหุ้น applicable ใน scope → เอา N ตัวบนสุด; applicable ไม่พอ → ได้เท่าที่มี (ไม่ error ไม่ปัดเพิ่ม); ใช้กลไกเดียวกับ L2 (cache ต่อรอบ, record `ctx.a`, chip ใน reasons)
- N เริ่มต้น = `coverage.avg_selected` ใน manifest ของ version (bmf20 = 20, A1 = 63); รับ 1–5000; 0/ค่าที่ไม่ใช่ตัวเลข = error
- `provenance.a_ranking_mode = "scoped_fixed_n"` + `a_ranking_n = {requested, per_rebalance: {รอบ: N ที่ได้จริง}, min, max}` (ค่าต่อรอบ เพราะ "N ที่ใช้จริง" ต่างกันได้แต่ละรอบ)
- คำเตือนข้อความตามสเปคที่ทุกจุดเดียวกับ L2 (แถบ sticky Pipeline / หน้าผลรวมผลที่บันทึก / หน้าหุ้น, กล่อง A, badge อันแรก, preflight)

## 25. (N0) สาเหตุจริงจากการรัน — ไม่ใช่สมมติฐาน (หลักฐาน: `python3 -m sandbox.v2.scripts.diagnose_run` → `sandbox/v2/debug/N0_evidence.md`, gitignored เพราะมีเนื้อข่าวของผู้ใช้)
1. **"Top-N ได้ 1 ตัวทั้งที่ตั้ง N=20" — โหมด Top-N ไม่เคยถูกรันในเคสของผู้ใช้เลย**
   - `jobs.db` (config ที่ server ได้รับจริง): run ของผู้ใช้ที่ใช้ bmf20 + XLK ทั้ง 19 ครั้ง ได้ A เป็น `filter` (กล่องแบบเดิม), `on` **ไม่มี key `ranking`** (= ทั้งตลาด) หรือ `scoped` (คงสัดส่วน) → ผ่าน A เฉลี่ย 0.5–3 ตัว; run ที่เป็น `scoped_fixed_n` มีครั้งเดียว (ของผมตอนทดสอบ M2) ได้ 20 ตัว
   - ในโหมดทั้งตลาด bmf20 เลือกหุ้น XLK **0 ตัวในรอบ 2021 และ 2 ตัว (HPE, MU) ในรอบ 2022** → เฉลี่ย ~1 = ตัวเลขที่ผู้ใช้เห็น — ถูกต้องตามโหมดนั้น
   - สมมติฐาน "Top-N กรองด้วย `selected` ของทั้งตลาดก่อน" **ไม่จริง**: log DEBUG ของ `scoped_select` = scope 72 → มี record 54 → applicable+score 52 → เลือก 20 (ไม่มีขั้นที่ใช้ class/selected); ยืนยันด้วย regression test ใน N2
   - run 2 ครั้งล่าสุดของผู้ใช้ (29 ก.ย. 13:58/14:00 น.) เกิดหลัง server restart เป็นโค้ด M2 (13:55 น.) แต่ request ไม่มี `ranking` และคำเตือน preflight ไม่มี "โหมดทดสอบ" → หน้าเว็บตอนกด RUN อยู่ที่โหมดทั้งตลาด; ทดสอบ UI ปัจจุบันด้วย Playwright (เลือก Top-N แล้วเปลี่ยน version / scope / B / condition / ปิด-เปิด A / Rescan / ออกไปหน้าอื่นแล้วกลับ) ค่ายังอยู่ทุกขั้น → สาเหตุที่เป็นไปได้มากที่สุด: **แท็บเบราว์เซอร์ที่เปิดไว้ตั้งแต่ก่อน restart (หน้าเก่ายังไม่มีตัวเลือก Top-N)** — หน้า `/` ไม่มี cache header และไม่มีอะไรบอกว่าหน้าเก่ากว่า server; พิสูจน์ 100% ไม่ได้เพราะ server ไม่เก็บ access log → แก้แบบกันทุกทาง (ดู N2): บังคับรีโหลดเมื่อ server เปลี่ยนเวอร์ชัน + `no-store` + แสดงโหมดที่ server ได้รับจริงก่อนรัน
   - บั๊กจริงที่เจอระหว่างทดสอบ: N เริ่มต้นถูกตั้งจาก version ที่เลือกอยู่ตอนกดเลือก Top-N (A1 → 63) แล้วไม่ตามเมื่อเปลี่ยนเป็น bmf20 (ควรเป็น 20)
2. **`_news()` ใน condition ของผู้ใช้ (`equal_weight_A_v2_v2_v2`) — ยืนยันบั๊ก**: ctx.b ดิบของข่าว `label: 2, class: "positive", score: 2.0` → `_news()` คืน **1**; `label: -2, class: "negative"` → คืน **-1** (INTC 2022-07-28, HPE 2022-06-01/11-29, WDC 2022-10-27 …) เพราะลำดับ field ที่ลองอ่านเจอ `class` (ข้อความ 3 ระดับ) ก่อน `label`/`score` แล้วแปลง "negative" → -1 ด้วย `_CATEGORY_MAP` → **กฎ "ข่าว -2 ขายครึ่งทันที" และ "ย้ายเงินไปข่าว +2" ไม่เคยทำงานเลย** (ข่าว -2 ถูกทำเป็น -1 = รอหลุดเส้นค่าเฉลี่ย) — ไม่ใช่บั๊กของ ctx.b (ค่าที่ส่งให้ถูกต้องครบ)
3. **sector**: mapping ถูกต้องตาม GICS (S&P 500 snapshot) — ข่าว 463 รายการ: Information Technology (XLK) 68 หุ้น / 450 ข่าว, Communication Services (XLC) 3 หุ้น / 13 ข่าว (META 9, NFLX 2, GOOGL 2) → scope XLK ทิ้งข่าวแค่ 13 รายการ **ไม่ใช่สาเหตุของ "ได้หุ้นน้อย"** (สาเหตุคือข้อ 1) แต่ควรเตือน (N4)

## 26. (N2) Top-N — โค้ดคัดหุ้นถูกอยู่แล้ว (N0) → แก้ที่สาเหตุจริง: หน้าเว็บส่งโหมดไม่ตรงกับที่ผู้ใช้เข้าใจ
- ไม่แก้ `scoped_select` (log ยืนยันว่าไม่ใช้ class/selected ของทั้งตลาด) — ล็อกพฤติกรรมด้วย regression test: รอบที่ทั้งตลาดเลือก XLK 0 ตัว → Top-N 20 ได้ 20 ทุกวัน; ชุดสังเคราะห์ที่ทุกตัวใน scope ต่ำกว่า cutoff และสลับ class แบบสุ่มแล้วผลเดิม
- กันหน้าเก่า: `/` ส่ง `Cache-Control: no-store`; หน้าเว็บส่ง `X-App-Version` (static + template + เวลา start ของ server) ทุก request → server ตอบ 409 `stale_page` สำหรับ preflight/รัน ถ้าไม่ตรง → แถบแดง "ต้องรีโหลด" + ปิดปุ่ม RUN (request ที่ไม่ส่ง header เช่น script/test ยังใช้ได้)
- แสดงสิ่งที่ server จะรันจริง: บรรทัด "จะรัน: A … · การจัดอันดับ … · ขอบเขต … · B … · C … · เงื่อนไข …" จาก preflight (ไม่ใช่จาก state ของหน้า) + บันทึกใน server log และ log ของ job
- N เริ่มต้นตาม version ที่เลือก (A1 63 / bmf20 20) จนกว่าผู้ใช้จะพิมพ์ N เอง
