# PROGRESS — Sandbox v2 "Pipeline Lab"

> ถ้า context ถูกล้าง: อ่านไฟล์นี้ + `RECON.md` + `DECISIONS_NEEDED.md` ก่อนทำต่อ
> branch: `feature/sandbox-v2` (แตกจาก `feature/model-a-rebuild` @ 7f9f037)

## W0 — Recon ✅
- ทำ: สำรวจ git/Model A/B/C/sandbox v1 → `RECON.md`; เขียน `model_A/export/DATA_CONTRACT.md` จากโค้ดจริง (commit แยก `b2ff51c`); copy `model_c_rulebase/` จาก branch PR (commit `c3dede5`)
- ไฟล์: `sandbox/v2/{RECON,DECISIONS_NEEDED,PROGRESS}.md`, `model_A/export/DATA_CONTRACT.md`, `model_c_rulebase/**` (copy)
- DoD: RECON ✅ / DATA_CONTRACT (commit แยก) ✅ / branch ✅ / ไม่มีไฟล์เดิมถูกแก้ ✅
- ค้าง: —

## W1 — ราคา S&P 500 ✅
- ทำ: `scripts/update_prices.py` (yfinance, batch 40 + sleep 3 วิ, incremental ตาม `checked_through`), `scripts/data_quality.py`, `prices.py` (loader + held-out guard + `data_hash`)
- ผลรันจริง (2026-09-27): universe **560** = S&P 500 ปัจจุบัน 503 (Wikipedia snapshot) ∪ Model A export 44 ตัวที่หลุด index แล้ว ∪ SPY/11 ETF/^IRX
  - **ok 549 / partial 11 / missing 0** (partial = IPO/spin-off หลัง PRICE_START เช่น CEG, GEHC, KVUE)
  - SPY + 11 ETF + ^IRX: ok ครบ 13 ตัว
  - รอบสอง: "ต้องดึง 0 ตัว (ข้าม 560)" ✅ ; `git status` ไม่มี parquet ✅ (prices/ 36 MB gitignored)
  - DATA_QUALITY: big_move 11 ครั้ง / 10 ตัว, unadjusted_split_suspect 7 ครั้ง / 4 ตัว (PARA 2024 น่าสงสัยสุด — กระโดด ~2 เท่าหลายวัน)
- ข้อสังเกต: Model A universe ไม่มีหุ้นที่ Yahoo ไม่มีราคา (เช่น TWTR, ATVI, CTXS = `no_price` ใน panel ของ Model A) → survivorship bias ติดมาจาก Model A เอง ไม่ใช่เฉพาะ sandbox
- DoD: ✅ ทุกข้อ

## W2 — Registry + Conditions ✅
- ทำ:
  - `model_A/export/build_history.py` — เรียก `rounds.round_004.run.build()/ranked()` เดิม สร้าง signal 5 กฎ A1–A5 (2011-06 → ก่อน held-out)
    - **ตรวจแล้ว:** ชุดหุ้น + น้ำหนักตรงกับ `scores_rule1/2.csv` ทุกรอบ และ backtest engine ของ Model A บน holdings จาก signal ได้ NAV ตรงกับ `r001/r004_nav.parquet` (max rel diff ≤ 6e-15) ทั้ง 5 กฎ
    - A1–A4: 12 รอบ (มิ.ย. 2011–2022) เฉลี่ยถือ 63.2 ตัว · A5: 144 รอบรายเดือน (2011-06 → 2023-05) เฉลี่ย 64.3 ตัว
  - `model_c_rulebase/export/build_export.py` — รัน engine exp_03 เดิม (ไม่เรียก LLM): 4,785 แถว, 435 ข่าว 1999-05 → 2026-07, badge negative
  - `scripts/build_stubs.py` — A/B/C stub (sha256) ใน `sandbox/v2/stubs/`
  - `registry.py` (scan + validate manifest/signal), `condition_registry.py` (ตรวจด้วย ast ไม่ exec), `server.py` (GET /api/registry, POST /api/registry/rescan)
  - conditions 5 ตัว: `equal_weight_A`, `follow_A_weights`, `hold_SPY`, `B_filter_then_EW`, `c_veto_dca_buyback` (port strategy_v1)
  - `model_B/export/README.md`
- DoD: registry คืน A (5 จริง + stub), B (stub), C (rulebase-exp03 negative + stub), conditions 5 ✅; manifest เสีย (badge/rebalance/coverage/ไฟล์หาย) → โผล่ใน invalid พร้อม 4 เหตุผล แล้วลบทิ้ง → invalid ว่าง ✅
- universe ราคาอัปเดตหลังมี history: 575 ตัว (ok 564 / partial 11 / missing 0)

## W3 — Engine + Simulator + Jobs ✅
- ทำ: `signals.py` (as-of, ห้ามอนาคต), `condition_worker.py` (process แยก, รับข้อมูล ≤ t ทีละวัน), `engine.py` (pipeline A→B→C, simulator next_close, delist→cash, benchmark SPY/EW, reasons ต่อ trade, artifacts), `metrics.py`, `jobs.py` (process แยก + SQLite + ETA + cancel/kill), API `/api/preflight`, `/api/jobs[/<id>[/stream|/cancel]]`
- ผลรันจริง: ดู `experiments/log.md` "Sandbox v2 W3" — hold_SPY = SPY B&H (4.91%), A1 เทียบ Model A corr 0.99999, DoD run ได้ metrics + funnel, ETA ลดลงต่อเนื่อง 5.4 → 0 วิ
- tests: 19/19 ผ่าน (`python3 -m pytest sandbox/v2/tests`)
- แก้ระหว่างทาง: parent ไม่รู้ว่า condition process ตาย (ตอน spawn ล้ม) → เพิ่มเช็ค `is_alive()` ทุก 0.2 วิ + ปิด child pipe ฝั่ง parent
- ข้อจำกัด: B on-demand มีแค่ interface ใน registry (ไม่มี B จริงให้ทดสอบ — engine ยังไม่เรียก infer.py); หุ้นที่ condition ให้ซื้อวันที่ไม่มีราคา → ข้าม (log) และไม่ลองซ้ำวันถัดไปถ้าเป้าไม่เปลี่ยน
- DoD: ✅

## W4 — Persistence ✅
- ทำ: `experiments_store.py` (save/list/load/trades แบ่งหน้า/delete ต้อง confirm/bundle zip/diff re-run/compare), API `/api/experiments*`, `/api/results/<run|exp>/<id>[/trades]`, `/api/compare`
- git policy: commit ได้ `config.json`, `condition_snapshot.py`, `metrics.json`, `provenance.json`, `summary.json` (การ์ด+sparkline เล็ก) — parquet/round_trips.json/zip gitignored
- แก้ระหว่างทาง: re-run ได้ metrics ต่างกันระดับ 1e-14 → สาเหตุ: ลำดับการบวกเลขตามลำดับ `set` ที่สุ่มต่อ process (hash randomization) → เรียงทุกจุด + `PYTHONHASHSEED=0` ให้ job/condition process
- DoD test (`tests/test_persistence.py`): รัน → save → restart server → เปิด → `metrics` และ equity ตรงกัน 100% ✅; re-run → `identical: true` ✅ (รันซ้ำ 3 ครั้ง ผ่านทุกครั้ง); ลบต้อง confirm ✅
- tests รวม 20/20 ผ่าน

## W5 — UI Shell + Pipeline Builder ✅
- ทำ: `templates/index.html` (SPA hash-route), `static/app.css` (design tokens, glass, gradient ต่อโมเดล, grid+noise+glow, reduced-motion), `static/app.js` (store/router/⌘K palette/คีย์ลัด R S /, gallery, compare), `static/pipeline.js` (กล่อง A→B→C→ƒ, เส้นโค้ง SVG + อนุภาคระหว่างรัน, สวิตช์โหมด/เวอร์ชัน/เกณฑ์, ไฟสถานะ coverage, คำเตือนเห็นเสมอ, Monaco + autocomplete `ctx.`, Validate dry-run, Save as new, timeline แรเงา held-out + toggle/พิมพ์ยืนยัน, RUN + stepper + ETA ภาษาไทย + log สด SSE + ยกเลิก, mini-progress บน topbar), `static/results.js`, `static/stock.js`; API เพิ่ม `/api/meta`, `/api/stock/<t>`, `/api/validate` (subprocess `dryrun.py`), `engine.stage_day()/dry_run()`
- vendor offline: `scripts/fetch_vendor.py` + `static/vendor/vendor.lock.json` (sha256); commit Alpine 3.14.1, lightweight-charts 4.2.0, confetti, fonts (IBM Plex Sans Thai, JetBrains Mono); Plotly 2.35.2 + Monaco 0.52.0 ต้องรัน fetch_vendor (gitignored)
- Legacy v1: ลิงก์ไป 127.0.0.1:5050 (ไม่ mount — ดู DECISIONS #4)
- ทดสอบ: `scripts/ui_smoke.py` (Playwright headless): pipeline → เปิด B/C กรอง → RUN จาก UI จนจบ → ผลลัพธ์ → บันทึก → คลิก trade → หน้าหุ้น → gallery → compare → registry/about/news — **console/page errors = 0**, screenshot ใน `sandbox/v2/screenshots/`
- บั๊กที่เจอและแก้: `x-for` ใช้ใน `<svg>` ไม่ได้ (→ x-html), Alpine เรียก `init()` ซ้ำ 2 รอบ (ลบ x-init), **Monaco/chart/EventSource ถูก Alpine ห่อ proxy → หน้าค้าง** (ย้ายไปเก็บนอก reactive state), `/api/stock` 500 (itertuples กับชื่อ column `class`)
- DoD: ✅

## W6 — ผลลัพธ์ + หุ้นรายตัว + Gallery ✅
- หน้าสรุปผล: hero cards count-up + delta vs SPY/EW + badge, equity (strategy/SPY/EW) แรเงา held-out, underwater, heatmap รายเดือน, sector exposure stacked area, Sankey funnel (เฉพาะกล่องที่เปิด), holdings วันสุดท้าย (คลิกไปหน้าหุ้น), top winners/losers, metrics เต็ม, trade log + reason chips สีตามโมเดล + ค้นหา/กรอง/แบ่งหน้า, snapshot เงื่อนไข + provenance, ปุ่มบันทึก (confetti) / Re-run diff / Export zip / ลบ (พิมพ์ exp_id)
- หน้าหุ้น: แท่งเทียน + ▲ซื้อ/▼ขาย ณ วันที่ execute, hover แสดง reasons, layer: ช่วงที่ A เลือก, จุด B, เส้น C ตามทิศ, ข่าว manual, SMA20/50, EMA20, volume, RSI14 (chart แยก sync กัน); เลือกหุ้นจาก trade log/holdings/ช่องค้นหา
- Gallery: การ์ด + sparkline + metrics + config chips + badge; เลือก 2–3 → Compare (equity normalize + ตาราง)
- ทดสอบ (`scripts/ui_smoke.py`): เปิดผลที่บันทึก → กราฟครบ, คลิก trade → หน้าหุ้นโฟกัสวันนั้นพร้อมลูกศร, compare 2 การทดลอง, ผล held-out มี badge HELD-OUT + แรเงาแดง — console errors 0; screenshot เปลี่ยนเป็น JPEG (8.2 MB → 2.0 MB)
- DoD: ✅

## W7 — Automention ✅
- ทำ: `news.py` (detect, trading_day_info, add/list/delete, CSV preview), API `/api/news*`, หน้าเพิ่มข่าว: `@` dropdown fuzzy (ticker+ชื่อ, ↑↓ Enter/Tab) → chip สีตาม sector; ข้อเสนอจากเนื้อข่าวกดยืนยัน/ปฏิเสธทีละตัว; แนะนำข่าว C (ทุก sector / sector ที่เจอ keyword) ต้องยืนยัน; วันตลาดปิด → ปุ่มเลื่อนเป็นวันทำการถัดไป (effective_date = วันทำการถัดไปเสมอ); mini chart ±45 วันพร้อม marker; CSV drag-and-drop → auto map column → ตาราง review แก้ได้ → บันทึกที่เลือก; รายการข่าว + ลบ
- เก็บที่ `sandbox/v2/data/manual_news.jsonl` (gitignored), `source="manual"` ทุกแถว, ใช้ใน pipeline เฉพาะเมื่อเปิด toggle "รวมข่าว manual" (badge MANUAL NEWS)
- **ความแม่นยำ auto-detect (10 ข้อความ `tests/mention_samples.json`, `scripts/eval_mentions.py`): ถูก 14 · ผิด 1 (Nasdaq→NDAQ) · พลาด 1 (Target) · precision 0.93 / recall 0.93 · แนะนำมหภาคถูก 10/10**
- tests: 23/23 (เพิ่ม `test_manual_news.py`: ข่าว manual เข้า pipeline เฉพาะเมื่อ toggle, เสาร์→จันทร์, ไม่แตะ training data); UI smoke รวมหน้าข่าว (พิมพ์ @nvi → Enter, ยืนยัน Apple, บันทึก, นำเข้า CSV) console errors 0
- DoD: ✅

## W8 — เอกสาร + End-to-End ✅ (ยังไม่ push/PR — รอผู้ใช้ยืนยัน)
- `README.md` (รันคำสั่งเดียว, คำเตือน security, เพิ่ม version, เขียน condition, held-out, เปลี่ยน PRICE_START, test, git policy); หน้า About/Methodology ในเว็บ (ทำใน W5)
- `tests/test_e2e.py`: A1 (จริง) + B stub + C rulebase-exp03 + equal_weight_A → run → save → restart server → load → metrics/equity/funnel ตรงกัน 100%, badge STUB+NEGATIVE, provenance ครบ, reasons ทุก trade มี A — **ผ่าน**
- tests ทั้งหมด **24/24 ผ่าน** · UI smoke console errors **0** · sandbox v1: diff = 0 บรรทัด, `sandbox.scripts.smoke_test` ผ่าน

## F1 — แก้นำเข้า CSV ✅
- วินิจฉัย (รันจริง): ไฟล์ `tests/fixtures/manual_news_sample.csv` → `/api/news/csv/preview` ได้ **400 "หา column headline ไม่เจอ"** — mapping เดิม match ชื่อ column แบบตรงตัว, column ไทย+วงเล็บ (`ข่าวแบบย่อ (short_news)`) ไม่ match; 500 ตามภาพ reproduce ไม่ได้ (DECISIONS #11)
- แก้ `news.py`: จับคู่ column ด้วย keyword ในชื่อ + คะแนน (greedy, 1 column/field, ตัด `label_reason` ออกจาก label), label ตัวเลข (สเกลจากหัว column/ค่าในไฟล์) + ข้อความ, column ที่ไม่รู้จัก → `extra` ต่อแถว, ข้ามแถวที่เสียพร้อมเหตุผล (ไม่ทำให้ทั้งไฟล์ fail), ไม่มีหัวข่าว → ประโยคแรกของเนื้อข่าว, body limit 4,000 → 20,000 ตัวอักษร (เดิมตัดข่าวยาวเงียบ ๆ)
- `server.py`: global error handler (JSON ภาษาไทย + `error_id` + traceback ลง `sandbox/v2/logs/server.log`), CSV preview/commit จับ error ทุกจุด, commit คำนวณวันที่มีผลใหม่จากวันที่ที่ผู้ใช้แก้
- UI: อ่านไฟล์เป็น UTF-8 (fallback Windows-874), หน้า preview มี dropdown แก้ mapping ต่อ field, รายการแถวที่ถูกข้าม+เหตุผล, แสดง label ดิบ → score, column ที่เก็บเป็น metadata
- test `tests/test_csv_import.py` 12 ข้อ: ไฟล์จริงนำเข้า 9/9 แถว META, `source=manual`, วันที่ 2021-10-25 → 2023-04-26 ตรงทุกแถว, body ตรงต้นฉบับ (ความยาว + sha256), label -2 → negative / score -1.0 (ต่ำสุด), extra ครบ, BOM, text label, แถวเสียถูกข้าม, แก้ mapping เอง, ไฟล์ว่าง/ซ้ำ/encoding ผิด → 400 ภาษาไทย, exception → 500 JSON + error_id อยู่ใน log
- ผ่านเว็บจริง (Playwright, server port 5096): ลากไฟล์ → mapping ถูก → "บันทึก 9 ข่าว", 5xx = 0, console error = 0 (สำรอง/คืน `manual_news.jsonl` ของผู้ใช้หลังทดสอบ) — screenshot `screenshots/F1_csv_*.jpg`
- DoD: ✅

## F2 — แก้หน้าหุ้นรายตัว ✅
- วินิจฉัย (รันจริง, DECISIONS #12): META ด้วย query ของ UI = 200 ทุกบริบท; **500 ที่ reproduce ได้ = ช่วงวันที่เริ่มหลัง DEFAULT_END** (`start > end` หลังตัด held-out → `ValueError` ที่ endpoint ไม่จับ) — เกิดกับทุก ticker, ถูกเรียกจาก mini chart หน้าเพิ่มข่าว
- แก้ `stock_view.py`: `StockError` (ข้อความไทย + status) สำหรับ ticker ไม่รู้จัก / status missing (บอก reason) / วันที่ผิด / start > end / ไม่พบ run-exp; ช่วง held-out ทั้งหมด → bars ว่าง + หมายเหตุ; partial → หมายเหตุช่วงราคา; ไม่มี trade ของหุ้นนี้ในการทดลอง / ไม่มี trades.parquet → หมายเหตุ ไม่ error; layer A/B/C/manual แต่ละตัวพัง → log traceback + หมายเหตุ หน้าไม่พัง; `reasons` ว่าง/None ไม่พัง
- `server.py`: `/api/stock` จับ StockError → JSON ภาษาไทย, อื่น ๆ → 500 JSON + error_id + traceback ใน log; ticker `brk.b`/ตัวเล็ก → `BRK-B`
- UI: กล่อง "หมายเหตุ" บนหน้าหุ้น, หัว error เป็น "โหลดหน้าหุ้นไม่ได้"
- test `tests/test_stock_detail.py` 17 ข้อ: META/AAPL (ไม่มี trade) 200 + layer A/C, partial (CEG) + หมายเหตุ, missing (manifest จำลอง) → 404 ข้อความไทยมี reason, ticker ไม่รู้จัก, ช่วง held-out 3 แบบ, พารามิเตอร์ผิด 6 แบบ, เปิดจากการทดลองที่ไม่มี META/ไม่มี parquet, layer พัง, exception → JSON+error_id, **ทุก 575 ticker เปิดได้**
- ผ่านเว็บจริง (Playwright): หน้าหุ้นพิมพ์ `@meta` → Enter → กราฟขึ้น ไม่มีกล่อง error; หน้าข่าว `@meta` + วันที่ 2026-09-10 → `/api/stock/META?start=2026-07-27&end=2026-10-25` = 200 (เดิม 500) กล่องกราฟแสดง "ไม่มีราคาในช่วงนี้ (held-out)"; 5xx/console error = 0 — screenshot `screenshots/F2_stock_META.jpg`
- DoD: ✅

## F3 — ขอบเขตการลงทุน ✅
- engine: `normalize_scope/scope_members/scope_label`, `config.scope = {mode, sectors, tickers, members}`, `stage_day(..., scope)` กรองหลังอ่าน A, funnel ขั้นแรก `universe` = หุ้นใน scope ที่มีราคา (+ `market` = ทั้งตลาด), EW benchmark จากหุ้นใน scope, `metrics.scope`; preflight ปฏิเสธ sector/ticker ผิดหรือว่าง, เตือนถ้าหุ้นใน scope ไม่ผ่าน A ทุกรอบ; dry-run (Validate) ใช้ scope ด้วย
- UI: "ขั้น 0 — ขอบเขตการลงทุน" เหนือกล่อง A (radio 3 โหมด, chip 11 sector พร้อมจำนวนหุ้น, ช่องค้นหา `@` เลือกหลายตัว, สรุป "sector XLE → 21 ตัว"), ป้าย flow "ขอบเขต N →"; หน้าผล: แถบ "ขอบเขต", Sankey node แรก "ขอบเขต XLE 21", กราฟ/ตาราง "EW ขอบเขต (21 ตัว)", กล่อง "พอร์ตว่าง" บอกเหตุผล; gallery chip `scope: XLE`
- ผลรันจริง (experiments/log.md "F3"): all = 14.17% (EW 5.87%) ตรงกับก่อน F3 ทุกไบต์; XLE = 66.47% vs EW XLE 60.33%; NVDA = ไม่ผ่าน A ทั้ง 2 รอบ → พอร์ตว่าง + ข้อความอธิบาย
- test `tests/test_scope.py` 18 ข้อ (all / 1 sector XLE / 1 ticker XOM ผ่าน API จริง → บันทึก → restart → เปิดใหม่): funnel ขั้นแรก = จำนวนหุ้นใน scope ที่มีราคาทุกวัน, EW = EW ของ scope ทุกค่า (และ ≠ EW ทั้งตลาด), SPY เท่าเดิม, scope/chips/metrics/funnel/equity หลังเปิดใหม่ตรงกัน, A record ไม่ถูกจัดอันดับใหม่, NVDA → เตือน + empty_reason, scope ผิด 5 แบบ, sector ไม่มีสมาชิก → preflight 400
- ผ่านเว็บจริง (Playwright): เลือก Sector แต่ยังไม่เลือก → เตือนก่อน RUN; XLE → "21 ตัว"; `@nvda` → เตือนไม่ผ่าน A → RUN → หน้าผลแสดง "พอร์ตว่าง"; XLE → RUN → บันทึก → เปิดใหม่ → scope เดิม; 5xx/page error = 0 (เจอ+แก้ `sectorList()` อ่าน meta ก่อนโหลด); `ui_smoke` เดิม console errors 0 — screenshot `screenshots/F3_*.jpg`
- tests รวม **71/71 ผ่าน**
- DoD: ✅

## F1b — label ข่าว 5 ระดับ (-2..+2) เป็นค่าหลัก ✅
- `news.py`: `LABELS` 5 ระดับ, ข่าว manual เก็บ `label` int เป็นฟิลด์หลัก (preview CSV, ฟอร์มพิมพ์เอง, API รับ `label` หรือ `sentiment` แบบเดิม), `label_of()` อ่านข่าวรูปแบบเก่าได้โดยไม่แก้ไฟล์ (DECISIONS #14), `label_class()` derive 3 กลุ่มเฉพาะเกณฑ์กรองแบบ Model B
- `signals.load_manual_news`: record มี `label`, `label_text`, reasons `MANUAL 2022-02-02 [-2 negative แรงมาก]: …`; `class`/`score` derive จาก label; `FIELDS` + label → `ctx.b[t]["label"]` ใช้ในเงื่อนไขได้
- `engine._chip`: trade reasons ของข่าว manual แสดง `label -2 negative แรงมาก` แทน class 3 กลุ่ม; `stock_view` + `stock.js`: hover "ข่าว manual · label +2 positive แรงมาก", marker `M-2`…`M+2` สีตามระดับ
- UI: dropdown preview 5 ตัวเลือก, ฟอร์มพิมพ์เอง 5 ปุ่ม, รายการข่าวแสดง label, `/api/meta.news_labels`
- test `test_csv_import.py` 16 ข้อ (+ fixture จริง `manual_news_5levels.csv` 20 แถวที่มีครบ -2,-1,0,1,2): preview/บันทึก/signal/chip/hover แยก 5 ระดับไม่ยุบรวม, condition อ่าน `ctx.b["META"]["label"]` และ trade reasons มี label -2/-1/+1/+2 ต่างกัน, สเกล ±1 → 5 ระดับ, ฟอร์ม/label ผิด → 400, ข่าวรูปแบบ F1 แรก + รุ่นเก่า อ่านกลับได้ความแรงเดิมโดยไฟล์ไม่เปลี่ยน
- ผ่านเว็บจริง (Playwright, สำรอง/คืน `manual_news.jsonl`): นำเข้า 20 แถว → dropdown ตรงกับไฟล์ทุกแถว → "บันทึก 20 ข่าว" → hover หน้าหุ้น META/MSFT เห็น -2 / -1 / 0 / +1 / +2 ต่างกัน; 5xx/page error = 0 (รอบแรก timeout รอกราฟหลังเปลี่ยน hash 1 ครั้ง — รันซ้ำ 2 รอบไม่เกิด) — screenshot `screenshots/F1b_*.jpg`
- tests รวม **75/75 ผ่าน**
- DoD: ✅

## G1 — กล่อง A/B/C เหลือ เปิด/ปิด + version ✅
- engine: `MODES = off/on`; A on = `class == selected AND applicable` ของ version ตรง ๆ; B/C on = แนบสัญญาณ ไม่ตัดหุ้น (funnel after_B = after_C = after_A); B ไม่มีข่าว → record `applicable: False` (ไม่เดาค่า); ลบ `criteria` ออกจาก config; `legacy_notes()` + `LegacyConfigError` สำหรับ config เก่า (DECISIONS #15); `box_stats()` ตัวเลขบนกล่อง
- สัญญา B: `score` -2..+2 (registry ตรวจ) → แปลง B stub ในที่ (class เดิม) + `build_stubs.py`; ข่าว manual score = label; `AsOf` รองรับ `max_age_days: 0`
- UI: กล่องมีแค่ ปิด/เปิด + version + badge (tooltip `(?)`) + คำอธิบายบทบาท + "ผ่าน N ตัว · ณ วันที่" + การกระจาย B/C (positive · neutral · negative · ไม่มีข้อมูล); tooltip ของทุก badge (pipeline, registry, ผลลัพธ์, gallery, compare, About); หน้าผลเก่า: แถบ LEGACY + Re-run ถามยืนยัน
- condition template ใหม่: `exclude_negative_B` (score < 0 → ไม่ถือ, ปรับ `CUT_BELOW`/`CUT_IF_NO_SIGNAL` ได้), `a_score_threshold` (`MIN_SCORE = 90`) — มี comment "เดิมเคยเป็นปุ่มในกล่อง ตอนนี้ย้ายมาที่นี่"
- ตรวจ compat: config ที่เทียบเท่าพอดี 4 แบบ (A only / A+B+C แนบ / B_filter_then_EW / A filter แบบเก่า) → metrics/equity/trades/funnel/positions ตรงกับ engine ก่อน G1 ทุกไบต์
- test `tests/test_boxes.py` 14 ข้อ: HTML/JS ไม่มี field เกณฑ์กรอง, config/preflight/registry API ไม่มี criteria, "ผ่าน N" ของ A = นับ selected+applicable เอง, B/C ไม่ตัดหุ้น + ไม่มีข่าว = applicable False, template ทั้งสองให้ผลตรงชื่อ (ทุกการซื้อผ่านเกณฑ์ ณ วันตัดสินใจ), config เก่า 5 แบบ, ผลที่บันทึกในเครื่องเปิดได้ทั้งหมด, ผลเก่าแบบ B กรอง เปิดได้ + Re-run 409, tooltip STUB; อัปเดต test เดิม (mode, score ของข่าว manual, look-ahead ยอมรับ record ไม่มีข้อมูล)
- ผ่านเว็บจริง (Playwright): กล่อง A/B/C มีปุ่ม ปิด/เปิด + select version 1 อัน ไม่มี input อื่น; A "ผ่าน 75 ตัว · ณ 2023-06-30", B "positive 15 · neutral 10 · negative 10 · ไม่มีข้อมูล 40"; STUB tooltip ขึ้น; template ใหม่อยู่ในรายการ; `ui_smoke` console errors 0 — screenshot `screenshots/G1_boxes.jpg`
- tests รวม **89/89 ผ่าน**
- DoD: ✅

## G2 — B version `manual-labels` ✅
- `manual_labels.py`: ข่าว manual → signal ต่อ (ticker, วันที่มีผล): score = label -2..+2, applicable True, point-in-time (`max_age_days 0`); manifest `result_badge: "manual"`, coverage = วันที่/ticker ที่มีข่าวจริง, notes อธิบาย point-in-time; rebuild อัตโนมัติ (server start / ข่าวเปลี่ยน / Rescan) — DECISIONS #16
- registry: badge `manual`/`oracle`, export นอก repo ได้ (test)
- build จากข่าวจริงของผู้ใช้ (อ่านอย่างเดียว): 463 แถว, 71 ticker, 2021-10-20 → 2023-06-28, score -2:32 · -1:22 · 0:160 · +1:147 · +2:102
- test `tests/test_manual_labels.py` 4 ข้อ: import META → เลือก B = manual-labels → รันจริง: condition assert ทุกวันว่า `ctx.b["META"]` = label ในไฟล์เป๊ะในวันที่มีข่าว และ `applicable False` วันอื่น; rebuild ตามการเพิ่ม/ลบข่าว; ข่าวซ้ำวันเดียวกันเฉลี่ย; ไม่มีข่าว = version ว่างแต่ valid
- ผ่านเว็บจริง: กล่อง B เลือก "B-manual · Manual labels … [MANUAL]" ได้, badge MANUAL (?) + tooltip, คำเตือน MANUAL — screenshot `screenshots/G2_manual_labels.jpg`
- DoD: ✅

## G2b — แยก Oracle label ออกจาก real-time ✅
- `news.py`: `label_method` (hindsight / real_time / unknown — ไม่ระบุ = unknown), `import_batch`, `method_summary()` (ชุดข่าวที่ยังไม่ระบุ + ตัวอย่างเหตุผลของ label), `set_label_method()`; API `/api/news/methods`, `POST /api/news/label_method` (rebuild B version ทันที)
- `manual_labels.py`: 2 version — `manual-labels-oracle` (hindsight, badge ORACLE + tooltip) / `manual-labels-realtime` (real_time, badge MANUAL); ไม่ผสมข้ามประเภท, ไม่มีข่าวประเภทนั้น = applicable False; signal มี `label_method`
- engine: `provenance.contains_oracle_signal` (version oracle หรือ toggle ข่าว manual ที่มี hindsight) + `manual_label_methods`; preflight เตือน ORACLE / unknown
- UI: ฟอร์มข่าวเลือกวิธี label (default ยังไม่ระบุ + คำเตือน), นำเข้า CSV ถามวิธีของทั้งไฟล์ + แก้รายแถว, รายการข่าวแสดงวิธี + กล่องระบุทีละชุด; หน้าผล: badge ORACLE เป็นอันแรก + แถบเตือนบนสุด; hover หน้าหุ้นบอกวิธี label — DECISIONS #17
- tests รวม **96/96 ผ่าน** · `ui_smoke` console errors 0
- test `tests/test_manual_labels.py` (7 ข้อรวม G2): META hindsight → ORACLE version 9 แถว / real_time 3 ข่าว → REALTIME 3 แถว / unknown ไม่เข้าทั้งคู่; run ORACLE → `contains_oracle_signal` + badge ORACLE + คำเตือน; run REALTIME → ไม่มี ORACLE; toggle ข่าว manual ที่มี hindsight → ติดธง; label_method ผิด → 400; ระบุทีละชุดแล้ว rebuild
- ผ่านเว็บจริง (Playwright, สำรอง/คืนข่าวของผู้ใช้ + rebuild): กล่อง "ยังไม่ระบุ" แสดงชุด 463 ข่าว; นำเข้า CSV default unknown + ถามก่อน → เลือก hindsight → ทุกแถว hindsight; เพิ่มข่าว real-time 3 รายการผ่านฟอร์ม; รัน B = oracle → แถบ ORACLE บนสุด + badge; รัน B = realtime → ไม่มีแถบ ORACLE, badge B MANUAL; 5xx/page error = 0 — screenshot `screenshots/G2b_*.jpg`
- DoD: ✅

## I1 — gallery หุ้นรายตัว (หน้าเริ่มต้นแทนหน้าว่าง) ✅
- API `/api/stocks/gallery`: หุ้น `status: ok` + `kind: stock` จาก `universe_manifest.json` (551 ตัว), จำนวนข่าว manual ต่อหุ้น (ไม่นับที่ลบแล้ว), `logo` = มีไฟล์ใน cache เครื่องแล้วเท่านั้น (ไม่ยิง network)
- UI: grid การ์ด responsive (โลโก้/avatar, ticker, ชื่อ, chip สี GICS ชุดเดียวกับหน้าอื่น, จุด "● n" เมื่อมีข่าว manual), ตัวกรอง sector แบบ chip เลือกหลายอัน (ไม่เลือก = ทั้งหมด), "ทั้งหมด N หุ้นที่มีข้อมูล", เรียง ticker A-Z (เลือกเรียงตามชื่อ/จำนวนข่าวได้), skeleton ระหว่างโหลด; พิมพ์ค้นหา → ซ่อน gallery + autocomplete เดิม; คลิก → หน้ารายละเอียดเดิม
- fallback avatar: สี่เหลี่ยมมุมโค้ง gradient สีตาม sector + อักษรย่อ ticker 2 ตัว (ใช้กับทุกหุ้นจนกว่าจะมีโลโก้จริงใน cache)
- แก้ระหว่างทาง: การเปลี่ยนหน้าไปหุ้นตัวหนึ่งยิง event `route` 2 ครั้ง → โหลด/วาดกราฟซ้ำ 2 รอบ → กันด้วย `_inflight`; timeout ของสคริปต์ทดสอบ (รวมครั้งเดียวใน F1b) มาจาก selector `.stock-chart canvas` ไปเจอ canvas ภายในของ lightweight-charts ที่กว้าง 0 ไม่ใช่บั๊กของหน้าเว็บ
- test `tests/test_stock_gallery.py`: รายชื่อ = status ok ทุกตัวพอดี, จำนวนข่าว, flag โลโก้; ผ่านเว็บจริง (Playwright): การ์ด 551 = API, กรอง Energy 21 / Energy+Utilities 51 ตรง, พิมพ์ "nvid" → gallery ซ่อน + autocomplete NVDA, คลิก XOM → หน้ารายละเอียด, error 0 — screenshot `screenshots/I1_gallery.jpg`
- DoD: ✅ (โลโก้จริง → I2)

## I2 — โลโก้บริษัท ✅
- `scripts/fetch_logos.py`: Wikidata P154 → Commons thumbnail 128px → PNG ที่ `static/logos/{ticker}.png` (gitignored) + `ATTRIBUTION.json` (license/ผู้สร้าง) + `_fetch_report.json` (เหตุผลที่ข้าม); ตรวจชื่อบริษัทก่อนใช้, ไม่ยิงซ้ำตัวที่ cache/ข้ามแล้ว — DECISIONS #18
- ผลรันจริง: โลโก้ 382/547 (Public domain 371 · CC BY-SA 4.0 7 · CC BY-SA 3.0 3 · อื่น ๆ 4), ขนาดรวม 2.6 MB; รันซ้ำ → "ต้องหา 0" ไม่มี network request
- หน้าเว็บ: `/api/stocks/gallery` บอก `logo` จากไฟล์ในเครื่องเท่านั้น → ไม่มีเน็ตก็ไม่ค้าง (ไม่มีไฟล์ = avatar ทันที, ไม่ยิงหา); skeleton ระหว่างโหลดรูป; เครดิต license ใน tooltip + บรรทัดเครดิตใต้ gallery
- test (`tests/test_stock_gallery.py` +7): การจับคู่ชื่อ (ตรง/ticker/ticker ถูกใช้ซ้ำ/คำกว้าง ๆ/กำกวม)
- ผ่านเว็บจริงแบบ **ออฟไลน์** (Playwright บล็อกทุก request ที่ไม่ใช่ server ในเครื่อง): การ์ด 547, โลโก้จริง 383 / avatar 164, ไม่มี request ออกนอกเครื่อง, error 0, กรอง/ค้นหา/คลิกทำงานเหมือนเดิม — screenshot `screenshots/I2_gallery_logos.jpg`
- DoD: ✅

## J1 — วันเริ่มซื้อขายตรงรอบ rebalance ของ A + warm-up indicator ✅
- `config.compute_start_dates()`: DECISION_START = รอบ A1 ล่าสุดที่ ≤ วันนี้ − 5 ปี (ไม่ใช้รอบใน held-out), PRICE_START = −90 วันทำการ (ปฏิทิน SPY จริง) — วันนี้ได้ 2021-06-30 / 2021-02-22; `IDEAL_LOOKBACK_YEARS`, `INDICATOR_WARMUP_DAYS` ใน config — DECISIONS #19
- ราคา: `update_prices --backfill-only` เติม 87,723 แถว (ช่วง 2021-02-12 → 2021-09-24) แถวเดิมไม่เปลี่ยน (ตรวจกับสำรองครบ 575 ไฟล์); stub build ใหม่ครอบช่วงต้น (แถวเดิมตรงกัน)
- engine: run ใหม่เริ่มที่ DECISION_START + warm-up 90 วัน (ส่งราคาให้ condition ก่อนวันแรก ไม่ซื้อขาย ไม่อยู่ในผล, `warmup_data_hash`), ราคาไม่พอ → ลด warm-up + คำเตือน; ผลเก่า re-run = ไม่มี warm-up (เหมือนเดิม)
- UI: "ราคาเริ่มมี: 2021-02-22 (warm-up indicator 90 วันทำการ — ไม่ซื้อขาย ไม่นับในผล) · เริ่มซื้อขายจริง: 2021-06-30 (รอบ rebalance ของ A1)", แถบลายบน timeline, หน้าผลมีแถบ WARM-UP, หน้า About อธิบายที่มาของวันที่
- test `tests/test_price_start_alignment.py` 12 ข้อ: "วันนี้" 5 ค่า → วัน rebalance จริงของ A1 เป๊ะ, held-out ข้าม/อนุญาต, PRICE_START = 90 วันทำการพอดี, default run, SMA50/EMA20/RSI14 มีค่าวันแรก (assert ใน condition), ซื้อครั้งแรกวันทำการถัดจาก DECISION_START, META = รอบที่ A1 เลือก, **ผลที่บันทึกในเครื่อง 2 รายการรันซ้ำ identical**
- ผลรันจริง (experiments/log.md "J1"): 504 วันทำการแทน 443, รอบแรกครบ, ซื้อ 2021-07-01; META ว่างถึง 2022-07-01 เพราะ A1 ไม่เลือก META ในรอบ 2021 (ไม่ใช่วันเริ่ม)
- ผ่านเว็บจริง: ช่องวันเริ่ม = 2021-06-30, บรรทัดสองวันที่แยกกัน, แถบ warm-up, รัน → หน้าผลแสดง WARM-UP, error 0 — screenshot `screenshots/J1_start_dates.jpg`
- tests รวม **117/117 ผ่าน**
- DoD: ✅

## K1 — import ไฟล์ข่าวที่โตขึ้นซ้ำได้โดยไม่เบิ้ล ✅
- `news.py`: `content_hash()` / `hashes_for()` (normalize: trim · lower · ยุบช่องว่าง), `ensure_hashes()` migrate + สำรองไฟล์, `hash_index()` (dict O(1)), `dup_check()` → exact / review / new, `commit_rows()` batch + ตรวจซ้ำฝั่ง server, `make_row()` แยกจากการเขียนไฟล์ — DECISIONS #20 (H1/H2 ไม่มีใน repo → สร้าง flow ตรวจสอบเอง)
- preview: สรุป "นำเข้าใหม่ X แถว · ข้ามอัตโนมัติเพราะซ้ำเป๊ะ Y แถว · ต้องตรวจสอบ Z แถว", ซ่อนแถวซ้ำเป๊ะ (ไม่มี popup), แถวต้องตรวจสอบแสดงข่าวเดิมที่ชน + เลือก ข้าม/แทนที่/เก็บทั้งคู่ (ไม่เลือก = ไม่บันทึก); หลังบันทึกแสดงผลจริงจาก server
- แก้บั๊กที่เจอระหว่างทดสอบ: (1) เลือกไฟล์เดิมซ้ำด้วยปุ่ม "เลือกไฟล์" ไม่เกิด event change → รีเซ็ต input หลังอ่าน (workflow หลักของงานนี้) (2) ปิด preview หลังบันทึกเกิด page error `null.mapping` → guard ทุก binding (3) commit เดิมเขียนทั้งไฟล์ทุกแถว → batch
- test `tests/test_csv_dedupe.py` 9 ข้อ: import ไฟล์ META 9 แถว → 9 ใหม่; ซ้ำ → 0 ใหม่ / ข้าม 9 ไม่มีอะไรให้เลือก; เพิ่ม 2 แถวท้ายไฟล์ → 2 ใหม่ / ข้าม 9 รวม 11; ตัวพิมพ์/ช่องว่างต่าง = ซ้ำเป๊ะ; ticker+วันที่ตรงแต่ headline ต่าง → review (ไม่เลือก/ข้าม/เก็บทั้งคู่/แทนที่); แก้ typo → review; ซ้ำในไฟล์เดียวกัน; migrate + backup; ฟอร์มปฏิเสธข่าวซ้ำ; 600 แถว 0.36 วินาที / import ซ้ำ 601 แถว 0.37 วินาที
- ผ่านเว็บจริงกับข่าวจริงของผู้ใช้ (สำรอง/คืนไฟล์): ไฟล์ META 9 แถว → "นำเข้าใหม่ 0 · ข้ามอัตโนมัติ 9" (มีอยู่ใน 463 ข่าวแล้ว), เลือกไฟล์เดิมซ้ำ → เหมือนเดิม, ไฟล์ 20 แถว → ข้าม 20, ข่าวรวม 463 → 463, popup 0, page error 0; ไฟล์ผสม → "ใหม่ 1 · ข้าม 3 · ตรวจสอบ 1" — screenshot `screenshots/K1_dedupe_preview.jpg`
- tests รวม **126/126 ผ่าน** · `ui_smoke` console errors 0
- DoD: ✅

## L1 — แก้ label_method แบบ bulk + เตือนข่าว unknown ✅
- `news.py`: `filter_news()` (ticker / sector / ช่วงวันที่ / วิธี label), `unknown_count()`; API `/api/news` รับตัวกรอง (คืน `{rows, total}`), `POST /api/news/label_method` รับ `ids` หรือ `filter` ("เลือกทั้งหมดที่กรองอยู่") → build B manual-labels ใหม่ทันที — DECISIONS #21
- หน้าเพิ่มข่าว: แถบตัวกรอง + ปุ่ม "แสดงเฉพาะที่ยังไม่ระบุ", checkbox ต่อแถว/ทั้งหน้า, "เลือกทั้งหมดที่กรองอยู่ (N)", ตั้งวิธี label ให้ทุกแถวที่เลือก; เปิดด้วย `#/news?method=unknown&ticker=MU` ได้
- คำเตือน: หน้าหุ้น "มีข่าว N รายการที่ยังไม่ได้ระบุว่ารู้ผลล่วงหน้าหรือไม่ จึงยังไม่ถูกใช้ในทั้ง B-manual และ B-oracle" + ลิงก์ไปแก้; preflight (B = manual-labels-*) และหน้าผล (`provenance.manual_unknown_news`)
- แก้ระหว่างทาง: หน้าหุ้นใช้ข้อมูล cache เดิมหลังข่าวเปลี่ยน (คำเตือนค้าง) → event `news-changed`; `etfs()` เรียกก่อน meta โหลด (page error)
- test `tests/test_label_method_bulk.py` 3 ข้อ: ข่าว MU แบบไม่ระบุ → `ctx.b["MU"]` วันข่าวร้าย = applicable False (ยืนยัน bug) + ไม่ขาย + คำเตือน → bulk ด้วยตัวกรอง → signal B ใหม่ทันที → รันใหม่ `ctx.b["MU"]` = −2 และเกิด trade ขายจริงวันนั้น (reasons "label -2 negative แรงมาก"); ตัวกรองทุกแบบ; หน้าเว็บมีเครื่องมือครบ
- ผ่านเว็บจริงกับข่าวจริง (สำรอง/คืนไฟล์): หน้า MU เตือน "มีข่าว 7 รายการ…" → คลิกลิงก์ → ตัวกรอง MU + ยังไม่ระบุ 7 แถว → เลือกทั้งหมดที่กรองอยู่ → real-time → เหลือ 0, กลับหน้า MU ไม่มีคำเตือน, error 0 — screenshot `screenshots/L1_bulk_label_method.jpg`
- DoD: ✅

## L2 — โหมดทดสอบ "จัดอันดับ A ใหม่เฉพาะใน scope" ✅
- engine: `scoped_select()` (score เดิม, เทียบเฉพาะ applicable ใน scope, k = round(n × สัดส่วนเดิมของกฎ) ≥ 1, cache ต่อรอบ), `stages.A.ranking = "scoped"` (ไม่ใช่ค่าเริ่มต้น), record `ctx.a` มี `global_class`/`scoped_rank`, chip ใน trade reasons, `provenance.a_ranking_mode` — DECISIONS #22
- UI: กล่อง A มี dropdown "การจัดอันดับ" (ทั้งตลาด / จัดอันดับใหม่เฉพาะใน scope (สำหรับทดสอบ)); ข้อความเตือนตามสเปคเป็นแถบ sticky บนหน้า Pipeline, หน้าผล (รวมผลที่บันทึก), หน้าหุ้นจากผลนั้น + ในกล่อง A; badge "A โหมดทดสอบ" อันแรก
- test `tests/test_scoped_ranking.py` 6 ข้อ: META + A1 ทั้งตลาดผ่าน 0 / โหมดทดสอบผ่าน 1 และซื้อจริง; XLK + bmf20 = 3 ตัว (52 × 5.81% / 53 × 5.63%) ตรงกับ top-k ที่คำนวณแยก; scope ทั้งตลาด = ผลเดียวกับโหมดปกติ; applicable False ถูกตัดเสมอ; ค่าเริ่มต้น global + ตรวจค่าผิด + คำเตือน A3; ข้อความเตือนตรงสเปคทุกจุด
- ผ่านเว็บจริง: "ผ่าน 0" → เลือกโหมดทดสอบ → "ผ่าน 1" + แถบเตือน, เลื่อนหน้าแถบยังอยู่, รัน → หน้าผลมีแถบ (เลื่อนแล้วยังอยู่) + badge, บันทึกแล้วเปิดใหม่ยังมีแถบ, คลิกไปหน้าหุ้นมีแถบ, error 0 — screenshot `screenshots/L2_*.jpg`
- ผลรันจริงบันทึกใน experiments/log.md "L2" (ระบุชัดว่าไม่ใช่ผลของ Model A) · tests รวม **135/135 ผ่าน** · `ui_smoke` console errors 0
- DoD: ✅

## M1 — ไม่รัน (ซ้ำกับ trial 127 ที่มีอยู่แล้ว) ⚠️
- สเปค = round 013 กฎ `r013_BMF20_WEIGHTED` (trial 127) ทุกข้อ; tie-break ต่างกันแต่ตรวจแล้วรายชื่อเหมือนกันทุกปี (ต่าง 0 ตัวใน 12 ปี) → ไม่รันซ้ำ ไม่แตะ `feature/model-a-rebuild` — DECISIONS #23
- ผลเดิม: Sharpe 0.415 vs EW 0.640 / SPY 0.681, CAGR 9.6%, MaxDD −55.2%, ระดับ C, DSR 0.003; export `A:bmf20-weighted` พร้อมใช้ใน sandbox

## M2 — โหมดทดสอบ "Top-N คงที่ภายใน scope" ✅
- engine: `ranking: "scoped_fixed_n"` + `n` (ค่าเริ่มต้น = จำนวนที่กฎเลือกจริงจาก manifest), `scoped_select(..., fixed_n)`, `provenance.a_ranking_n` ต่อรอบ, คำเตือนตามสเปค — DECISIONS #24
- UI: ตัวเลือกที่ 3 ในกล่อง A + ช่อง N, แถบเตือน sticky ทุกหน้า (ข้อความตามโหมด), badge "A โหมดทดสอบ (Top-N คงที่ N=20)", หน้าผลแสดง N ที่ตั้ง/ได้จริง
- test `tests/test_fixed_n_ranking.py` 4 ข้อ: XLK + bmf20-weighted N=20 → 20 ตัวเป๊ะทั้ง 2 รอบ = top-20 score ที่คำนวณแยก, provenance/badge/reasons; N=100 กับ 10 ตัว applicable → 10 ไม่ error (applicable False ไม่นับ); N เริ่มต้น + ค่าผิด; ข้อความเตือนตรงสเปค
- ผ่านเว็บจริง (ตั้งค่าแบบ Experiment 1: bmf20-weighted · Top-N 20 · XLK · B manual-labels-realtime · C ปิด): "ผ่าน 20 ตัว", แถบเตือนทุกหน้า (เลื่อนแล้วยังอยู่, เปิดผลที่บันทึกย้อนหลังยังอยู่, หน้าหุ้นมี), badge ใน gallery, error 0 — screenshot `screenshots/M2_*.jpg`
- DoD: ✅

## N0 — สืบสาเหตุจริงจาก log ก่อนแก้ ✅
- `scripts/diagnose_run.py` (อ่านอย่างเดียว): config ที่ server ได้รับจริงจาก jobs.db, log DEBUG ของ `scoped_select` (logger `sandbox.v2.engine`), ctx.b ดิบเทียบ `_news()` ของ condition ผู้ใช้, sector ของหุ้นที่มีข่าว → `debug/N0_evidence.md` (gitignored)
- ผล (DECISIONS #25): (1) โหมด Top-N ไม่เคยถูกใช้ในเคสผู้ใช้ — ทุก run ที่ได้ ~1 ตัวคือโหมดทั้งตลาด (bmf20 เลือก XLK 0 / 2 ตัวต่อรอบ); Top-N ทำงานถูก (20) (2) `_news()` อ่าน `class` ก่อน `label` → ±2 กลายเป็น ±1 กฎ ±2 ไม่เคยทำงาน (3) sector ถูกต้อง ข่าวนอก XLK มี 13/463

## N1 — ล้างข้อมูลทดลอง (backup ก่อนเสมอ) ✅
- `workspace.py` + `scripts/reset_workspace.py` (แสดงแผน / `--yes` / `--restore <dir>`) + ปุ่ม "ล้างข้อมูลทดลอง (backup อัตโนมัติ)" ในหน้า Registry (ต้องพิมพ์ "ล้างข้อมูลทดลอง") + API `/api/workspace[/reset]`
- backup: `sandbox/v2/backups/<ts>/` (gitignored) = `manual_news.jsonl` (กู้คืนตรงทุก field) + `manual_news_backup_<ts>.csv` + `conditions_backup_<ts>/` + `experiments_backup_<ts>/` + `BACKUP.json`; ตรวจว่า backup ครบก่อนลบ
- ไม่แตะ: export Model A/C, ราคา, stub, template condition ของระบบ
- รันจริง: backup `sandbox/v2/backups/20260929-142129/` = ข่าว 465 แถว (463 ที่ใช้งาน), condition 3 ไฟล์ (equal_weight_A_v2, _v2_v2, _v2_v2_v2), ผลการทดลอง 3 รายการ → หลังล้าง ข่าว 0 · condition ผู้ใช้ 0 · ผลที่บันทึก 0
- test `tests/test_workspace_reset.py`: ต้องพิมพ์ยืนยัน, backup ครบ (ข่าวตรงไบต์), template ระบบยังอยู่, กู้คืนได้

## N2 — Top-N: ล็อกพฤติกรรมด้วย regression test + กันหน้าเว็บเก่า/โหมดไม่ตรง ✅
- ตามหลักฐาน N0 โค้ดคัด Top-N ถูก → ไม่แก้ตรรกะ; เพิ่ม regression test (XLK รอบ 2021: ทั้งตลาด 0 → Top-N 20 ได้ 20 ทุกวัน; ชุดสังเคราะห์ต่ำกว่า cutoff + สลับ class แล้วผลเดิม) — DECISIONS #26
- กันสาเหตุจริง: `no-store` บนหน้าเว็บ, `X-App-Version` + 409 `stale_page` + แถบ "ต้องรีโหลด" + ปิด RUN, บรรทัด "จะรัน: …" จาก preflight, log โหมด A ใน server/job, N ตาม version
- ผ่านเว็บจริง: N 63 → 20 เมื่อเปลี่ยนเป็น bmf20 (พิมพ์เองแล้วไม่ถูกทับ), "จะรัน: A A:bmf20-weighted · การจัดอันดับ Top-15 คงที่ใน scope (ทดสอบ) · ขอบเขต sector XLK …", restart server ขณะหน้าเปิด → แถบแดง + RUN กดไม่ได้ → รีโหลด → หาย — screenshot `screenshots/N2_effective_line.jpg`

## N3 — บังคับเลือกวิธีตั้ง label ตอน import ✅
- preview: `has_method_column`, `label_method` รายแถว (ถ้ามีคอลัมน์), `method_hint` (แนะนำ hindsight จากคอลัมน์เหตุผล) — commit ฝั่ง server ปฏิเสธแถวที่ไม่ใช่ real_time/hindsight — DECISIONS #27
- UI: ตัวเลือก "ทั้งไฟล์ real_time / ทั้งไฟล์ hindsight / ระบุรายแถว" (ค่าเริ่มต้น = ยังไม่เลือก), แถบแดง "ต้องเลือก", ปุ่ม "ยืนยัน import" ปิดจนครบ, รายแถวไม่มี unknown; ฟอร์มพิมพ์เองก็ต้องเลือก
- test (+3 ใน `tests/test_csv_dedupe.py`) + อัปเดต test เดิมให้เลือกวิธี label; ผ่านเว็บจริงกับ `model_b_IT_news.csv`: ค่าเริ่มต้นว่าง + ยืนยันกดไม่ได้, แนะนำ hindsight "15 จาก 463 แถว" พร้อมตัวอย่าง, เลือก hindsight → ทุกแถว hindsight + กดได้, รายแถว → กดไม่ได้จนเลือกครบ (ไม่ได้ import) — screenshot `screenshots/N3_method_required.jpg`
- tests รวม **145 ผ่าน**

## N4 — เตือนข่าวที่หุ้นอยู่นอกขอบเขตที่เลือก ✅
- `news.scope_check()` + API `/api/news/scope_check`; preflight เตือน "SCOPE-NEWS: มีข่าว N รายการเป็นของหุ้นนอกขอบเขตที่เลือก … META (Communication Services) …" เมื่อใช้ข่าว manual (B manual-labels / toggle) และ scope ไม่ใช่ทั้งตลาด; หน้า Pipeline มีแถบเตือน + ลิงก์ "ดูรายชื่อข่าวทั้งหมด" (`#/news?tickers=…`); หน้าเพิ่มข่าวเตือนตามขอบเขตที่เลือกในหน้า Pipeline
- หน้าเพิ่มข่าว: ticker ในรายการข่าวแสดง sector ETF กำกับ (`META · XLC`) + preview CSV แสดง sector ของทุก ticker
- เลือกหลาย sector พร้อมกันได้อยู่แล้ว (F3) — test ยืนยัน XLK + XLC ไม่มีข่าวนอกขอบเขต
- test `tests/test_scope_news.py` 4 ข้อ (sector GICS จริง, นับนอก/ใน, preflight มี/ไม่มีคำเตือน, ลิงก์รายชื่อ)

## N5 — แผง "ทำไมวันนี้ทำ/ไม่ทำ" ต่อหุ้นต่อวัน ✅
- engine: `decisions.parquet` (บันทึกตอนรัน) + worker ส่ง snapshot `ctx.state`; API `/api/results/<kind>/<id>/decisions?ticker=&date=`; หน้าหุ้น: คลิกวันไหนก็ได้บนกราฟ → แผงแสดงสรุป, note ของ condition, state ของหุ้นนั้น (cut/pending), ctx.b/ctx.a/ctx.c ดิบ — DECISIONS #28
- `conditions/condition_fixed.py` = condition ของผู้ใช้ + แก้ `_news()` (อ่าน label/score ก่อน class) + `ctx.note` ทุกทางแยก
- test `tests/test_decision_log.py` 4 ข้อ: ข่าว KR -2 (2021-09-15) → condition_fixed ขายครึ่งวันนั้น (weight 5% → 2.5%); บันทึกวันนั้น: ctx.b label -2, summary "ลดเป้า", note "ข่าว -2 → ขายครึ่งทันที", state cut.done = False; วันถัดไป note "_is_reduced=True"; วันเสาร์ → วันทำการก่อนหน้า; ผลเก่า → available False

## N6 — Experiment 1 (BMF20 Top-20 · หุ้นที่มีข่าว · B oracle · condition_fixed) ✅
- import `model_b_IT_news.csv` ใหม่ (463 แถว, hindsight) → รันผ่านหน้าเว็บ + บันทึก `20260929-143958_experiment-1-bmf20-top-20-b-oracle-condi`
- หลักฐาน: funnel ผ่าน A = 20 ทุกวัน (504/504) ถือ 20; `a_ranking_n` = 20 ทั้ง 2 รอบ; ข่าว -2 → ขายครึ่ง 9 ครั้ง (เช่น META 2022-02-02 เป้า 5% → 2.5%); ผล 1.11% / SPY 6.05% / EW scope 15.73% (experiments/log.md) — DECISIONS #29
- แก้แผงคลิกวันที่ (N5): กราฟถูกสร้างกว้าง 0 ตอนหน้ายังซ่อน → รอ ResizeObserver ก่อนวาด; คลิกจริง 15/15; ui_smoke ตรวจคลิก → แผงขึ้น
- screenshot: `N6_scope_xlk_news_warning.jpg`, `N6_experiment1_results.jpg`, `N5_explain_panel.jpg` (คลิกเมาส์จริงที่ 2022-02-02)

## Q0 — สาเหตุจริงของ SELL/BUY บนหุ้นที่ไม่มีข่าวร้าย ✅
- `trade_causes.py` (จัดชนิด trade จากบันทึกตอนรัน) + `scripts/diagnose_trades.py` (อ่านอย่างเดียว)
- สมมติฐาน "ถูกดึงเงินคืน" ผิดเป็นส่วนใหญ่: สาเหตุหลัก = engine ปรับทุกตัวกลับเป้าเมื่อเป้าตัวใดตัวหนึ่งเปลี่ยน (NOW: SELL 3 = รายปี 1 + ปรับกลับเป้า 2, ดึงคืน 0) — DECISIONS #30

## Q1 — ป้าย SELL/BUY บอกสาเหตุบนกราฟหุ้นรายตัว ✅
- ชนิด: SELL ข่าวร้าย · SELL → คืนให้ <ticker> · SELL/BUY รอบปี · BUY ← รับเงินจาก <ticker> · BUY ซื้อคืน · ปรับกลับเป้า (จุดเทาเล็ก) · delist / เงื่อนไขอื่น — สีเดียวกันทั้งระบบ (`trade_causes.KINDS`)
- legend ใต้กราฟแสดงคำอธิบายทุกชนิด + จำนวนในหุ้นนั้น (ไม่ต้องชี้/คลิก); แผงชี้เมาส์ + แผง "ทำไมวันนี้" + ตาราง trade แสดงสาเหตุ
- `ctx.note(..., kind=, ref=)` + `tags_json` ใน decisions; ผลเก่าใช้ข้อความ note (ต้นทางขึ้น "(อนุมาน)") — DECISIONS #31
- test `tests/test_trade_causes.py` 4 ข้อ (condition สาธิต `tests/fixtures/cause_demo_condition.py` ได้ครบทุกชนิด, fallback ผลเก่า, คำที่เคยชน, kind ผิด = error); ui_smoke รัน condition สาธิตแล้วตรวจ marker ทั้ง 4 ชนิด + legend บนกราฟจริง

## Q2 — MA_DAYS / SMA-EMA ปรับได้จากหน้าเว็บ ✅
- กลไก PARAMS ของ condition (registry ตรวจ, config.condition.params, worker แทนค่าก่อน decide, chip/log/"จะรัน:" แสดงค่า) — DECISIONS #32
- condition_fixed: MA_DAYS 5–250 + MA_TYPE SMA/EMA พร้อมคำอธิบายว่าใช้แค่ยืนยันข่าว -1
- ตรวจด้วยการรันจริง: ค่าเริ่มต้น = Experiment 1 ทุก trade; SMA100 รันซ้ำตรงกัน; SMA20 เปลี่ยนวันยืนยันข่าว -1 ของ META (trade 368) — experiments/log.md
- test `tests/test_condition_params.py` 4 ข้อ; ui_smoke: ตั้ง MA_DAYS=100 + EMA แล้วบรรทัด "จะรัน:" ต้องแสดง, ใส่ 999 ต้องขึ้น error

# สรุปรวม
**ทำครบ W0–W8 + F1–F3 + F1b + G1–G2b + I1–I2 + J1 + K1 + L1–L2 + M2 (M1 ซ้ำ trial 127 — ไม่รัน) + N0–N6** — commit แยกทุก phase (`git log --oneline feature/model-a-rebuild..feature/sandbox-v2`)

**ตรวจแล้วด้วยการรันจริง**
- signal Model A ทั้ง 5 กฎ reproduce NAV ของ backtest เดิมเป๊ะ (≤ 6e-15); engine ของ sandbox ตาม NAV ของ A1 (corr รายวัน 0.99999)
- hold_SPY = SPY buy&hold − cost (< 0.01%); look-ahead/held-out guard มี test ที่พยายามโกงแล้ว fail; บันทึก→restart→เปิด ตัวเลขตรง 100%; re-run ได้ผลเดิมทุกหลัก
- auto-detect ข่าว: precision/recall 0.93 บน 10 ตัวอย่าง (ชุดเล็ก)

**ข้อจำกัด / ยังไม่ได้ทำ**
- B on-demand (`runtime: on_demand` + `infer.py`): registry validate ได้ แต่ **engine ยังไม่เรียก infer.py** (ไม่มี B จริงให้ทดสอบ) — on_demand version ตอนนี้ = ไม่มีสัญญาณ
- ราคา default 5 ปี → A รายปี 2 รอบก่อน held-out (DECISIONS #2)
- หุ้นที่เงื่อนไขสั่งซื้อในวันที่ไม่มีราคา → ข้าม และไม่ลองซ้ำถ้าเป้าไม่เปลี่ยน
- sector ของหุ้นที่หลุด index แล้ว (44 ตัว) = "Unknown" (ไม่มี GICS ย้อนหลัง) → C ไม่มีผลกับหุ้นกลุ่มนี้
- screenshot PNG ชุดแรก (8 MB) อยู่ใน history ของ commit W5 (เปลี่ยนเป็น JPEG ใน W6)
- push branch + เปิด PR: รอผู้ใช้ยืนยัน (ห้าม merge เอง)
