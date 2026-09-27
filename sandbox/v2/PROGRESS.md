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
