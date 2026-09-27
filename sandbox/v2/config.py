"""
Config กลางของ sandbox v2 "Pipeline Lab" — single source of truth (ห้าม hardcode ค่าเหล่านี้ซ้ำในไฟล์อื่น)

เปลี่ยนช่วงราคา: แก้ PRICE_START บรรทัดเดียว (เช่น "2010-06-01") แล้วรัน
    python3 -m sandbox.v2.scripts.update_prices
ตัว updater จะดึงเฉพาะช่วงที่ยังไม่มี (ย้อนหลัง/ต่อท้าย) — โค้ดส่วนอื่นไม่ต้องแก้
"""

import os
from pathlib import Path

PRICE_START = "2021-09-27"   # 5 ปีย้อนหลังตามที่ผู้ใช้ขอ (ดู DECISIONS_NEEDED.md ข้อ 2)
HELD_OUT_START = "2023-07-01"  # ตรงกับ Model A — ห้ามเปลี่ยนโดยไม่ถามผู้ใช้
DEFAULT_END = "2023-06-30"
TRANSACTION_COST = 0.001     # 0.10% ต่อขา ตรงกับ Model A
INITIAL_CAPITAL = 1_000_000
DECISION_FREQ = "daily"
EXECUTION = "next_close"     # signal ณ close วัน t → ซื้อขายที่ close วัน t+1
HOST, PORT = "127.0.0.1", int(os.environ.get("SANDBOX_V2_PORT", "5060"))

HELD_OUT_CONFIRM_TEXT = "ยืนยัน held-out"

# timeouts ของ condition ที่ผู้ใช้เขียน (รันใน process แยก)
DECIDE_TIMEOUT_SEC = 10      # ต่อการเรียก decide() 1 ครั้ง
JOB_TIMEOUT_SEC = 30 * 60    # ทั้ง job

# ---- paths ----
V2 = Path(__file__).resolve().parent
REPO = V2.parent.parent
DATA = V2 / "data"
PRICES_DIR = DATA / "prices"              # gitignored — parquet ต่อ ticker
UNIVERSE_MANIFEST = DATA / "universe_manifest.json"
DATA_QUALITY_REPORT = DATA / "DATA_QUALITY.md"
CACHE_DIR = V2 / "cache"                  # gitignored
JOBS_DB = V2 / "jobs.db"                  # gitignored
EXPERIMENTS_DIR = V2 / "experiments"
CONDITIONS_DIR = V2 / "conditions"
MANUAL_NEWS = DATA / "manual_news.jsonl"  # gitignored — ข่าว manual ของ v2 (source="manual")

# โฟลเดอร์ export ของแต่ละโมเดลที่ registry สแกนหา version (<root>/<version>/manifest.json)
MODEL_EXPORT_ROOTS = {
    "A": REPO / "model_A" / "export",
    "B": REPO / "model_B" / "export",
    "C": REPO / "model_c_rulebase" / "export",
}
STUB_EXPORT_ROOT = V2 / "stubs"          # stub ของ A/B/C (สร้างด้วย scripts/build_stubs.py)

BENCHMARK = "SPY"
RISK_FREE = "^IRX"
SECTOR_ETFS = {
    "Information Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}
EXTRA_SYMBOLS = [BENCHMARK, RISK_FREE] + list(SECTOR_ETFS.values())
