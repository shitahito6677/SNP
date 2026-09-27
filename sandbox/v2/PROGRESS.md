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

# สรุปรวม
**ทำครบ W0–W8** — commit แยกทุก phase (`git log --oneline feature/model-a-rebuild..feature/sandbox-v2`)

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
