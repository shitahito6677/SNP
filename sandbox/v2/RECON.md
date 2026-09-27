# RECON — Sandbox v2 (W0, 2026-09-27)

## Git
- branch เดิม: `feature/model-a-rebuild` (71 commit เหนือ `main`) — **รวม `feature/ensemble-sandbox` (sandbox v1) ไว้ทั้งหมดแล้ว** (0 commit ของ ensemble-sandbox ที่ไม่อยู่ใน model-a-rebuild)
- `main` ยังไม่มี sandbox v1 และ model_A → แตก `feature/sandbox-v2` จาก `feature/model-a-rebuild` (7f9f037)
- PR ค้าง: #1 exp_03 (`feature/model-c-rulebase`), #2 exp_04 (`feature/model-c-event-clustering`, รวม #1) — ทั้งคู่ **ยังไม่ merge** → `model_c_rulebase/` ไม่อยู่บน branch ฐาน
  → copy ไฟล์ `model_c_rulebase/` แบบไม่แก้ (byte-identical) เข้ามาใน commit แยก (ดู DECISIONS_NEEDED #1)
- ไฟล์ untracked ของผู้ใช้ (`processed_news_price_15d/`, `sandbox/rules/rule_v2..5*`, `sandbox/data/sample_10_preview.txt`) — ไม่แตะ ไม่ commit

## Model A (`model_A/`) — มีของจริง
- ดู `model_A/export/DATA_CONTRACT.md` (commit แยกแล้ว)
- export เดิม: 2 กฎ (rule1 = `r004_Q_LOWACC_overall_W_CAP` 2 รอบ, rule2 = `r004_C_SHYQMOM_overall_W_CAP` 24 รอบ) เฉพาะ 2021-06 → 2023-05
- **ไม่มี** `r001` (EW), `BUFFER`, `W_IV` ใน export และไม่มีประวัติก่อน 2021 → ต้องสร้างด้วย `build_history.py`
- ข้อมูลที่ต้องใช้สร้างประวัติ **มีครบในเครื่อง**: `model_A/data/interim/panel_{annual,monthly}.parquet`, `price_signals_monthly.parquet`, `data/raw/prices/*.parquet` (1,151 ticker, 2008-01 → 2026-09-25), constituents fja05680 (snapshot ล่าสุด 2026-08-18, 503 ตัว) — gitignored ทั้งหมด (`model_A/.gitignore`)
- `rounds/round_004/run.py:build()` สร้าง holdings ของทั้ง 5 กฎได้ → เรียกของเดิม ไม่ re-implement
- จังหวะเทรดของ Model A = close วัน R; sandbox v2 = close วัน R+1 → ผลจะต่างจาก NAV ของ Model A เล็กน้อย (บันทึกเป็นข้อจำกัด)
- held-out guard ของ Model A (`lib/guard.py`) ตรงกับ `HELD_OUT_START = 2023-07-01` ของสเปค (Model A: rebalance ต้อง < 2023-06-30 → rebalance สุดท้าย 2023-05-31 (M) / 2022-06-30 (A))
  - ⚠️ สเปคเขียน Model A decision period "ก.ค. 2017 – มิ.ย. 2023" แต่ LEADERBOARD ใช้ "2017–2022" — ไม่กระทบ sandbox (sandbox แค่ใช้ cutoff)

## Model B — ไม่มีของจริง
- ไม่พบโฟลเดอร์ `model_B/`, ไม่พบไฟล์ weights (`*.bin/*.safetensors/*.pt/*.ckpt`) ในทุก branch → ใช้ stub อย่างเดียว + interface `runtime: on_demand` เตรียมไว้

## Model C
- stub ของ v1: `sandbox/inference/model_c.py` (`predict(headline, sector)` deterministic)
- `model_c_rulebase/` (exp_03): **ไม่มีไฟล์ R4 score ที่บันทึกไว้** — score ถูกคำนวณสด ๆ ใน `scripts/r5b_validate.py:run_engine_on_all_news()` จาก
  `data/fomc_market_context.csv` (R1+R2) + `data/fomc_structured_vars.csv` (R3 ผล Qwen ที่สกัดไว้แล้ว) → `build_export.py` เรียกฟังก์ชันนี้ **ไม่เรียก Qwen**
  - ข่าว: FOMC statement + Beige Book 1999-03 → 2026 (~16/ปี), 436 ข่าวมี structured vars, 11 sector ETF
  - ผล R5: 0/216 cells ผ่าน |rho|>0.3 (negative result — `experiments/log.md` บน branch PR #1)
  - ⚠️ look-ahead เล็กน้อยในตัว engine เอง: `vix_p90` คำนวณจาก vix_delta **ทั้งช่วง 1999–2026** (`r5b_validate.py`) → threshold ของ VIX amplifier เห็นอนาคต — บันทึกเป็นข้อจำกัดใน manifest ไม่แก้โค้ด exp_03
  - ข่าวออก ~14:00 ET (FOMC) และ equity_move ใช้ close วันข่าว → signal ใช้ได้ ณ close วัน t0 → execute t0+1 (สอดคล้อง next_close)
- `model_c_event_clustering/` (exp_04): ใน working tree มีแค่ `features/` ว่าง; ไฟล์จริงอยู่บน branch PR #2 — ไม่ใช้ใน v2 (ไม่ใช่ signal รายวัน)

## Sandbox v1 (`sandbox/`)
- Flask `app` แบบ module-global (`sandbox/app/server.py:26`), `app.run(debug=True, port=5050)`, 5 หุ้น, ราคา CSV 5 ปี
- reuse ได้: `inference/_stub_utils.deterministic_seed` (stub), `strategy/strategy_v1.py` (port เป็น condition), `events_store.py` (schema ข่าว manual: `id, created_at, source=manual, kind(b|c), ticker, date, headline, class, score, is_stub`)
- v1 hardcode universe 5 ตัวใน `sandbox/config.py` → v2 ไม่ import config ของ v1
- **Legacy v1:** ไม่ mount เป็น blueprint (ต้อง refactor server.py ของ v1 ซึ่งห้ามแก้) → navbar ลิงก์ไป `http://127.0.0.1:5050` และบอกวิธีรัน v1

## Environment
- Python 3.9.6 (system) → ใช้ `from __future__ import annotations`; pandas 2.3.3, numpy 2.0.2, pyarrow 21, yfinance 1.2.0, flask 3.1.3
- ไม่มี pytest / playwright → ติดตั้งแบบ `--user` (pytest) / ลอง playwright ใน W5 ถ้าไม่ได้ใช้ checklist

## แผนปรับจากสเปค
| สเปค | ของจริง | ปรับเป็น |
|---|---|---|
| A 5 rule มีใน export | มี 2 rule, 2021+ | `build_history.py` เรียก `round_004.build` สร้างครบ 5 rule 2011-06 → 2023-05 |
| `model_A/export/<version>/manifest.json` | export เป็นไฟล์แบน | สร้างโฟลเดอร์ย่อยต่อ version (ไม่ลบไฟล์เดิม — adapter v1 ยังใช้ได้) |
| R4 score รายข่าว × sector มีอยู่ | ไม่มีไฟล์ | `build_export.py` รัน engine เดิม (deterministic, ไม่เรียก LLM) |
| B weights จริง | ไม่มี | stub + interface on_demand |
| Universe ราคา = S&P ปัจจุบัน ∪ export | Model A มีราคาในเครื่องแล้ว 1,151 ตัว | ดึงใหม่ด้วย yfinance ตามสเปค (แหล่งเดียวทุกตัว, มี OHLCV) |
