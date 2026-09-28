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
