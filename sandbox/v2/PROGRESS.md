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
