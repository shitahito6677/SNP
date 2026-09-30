"""ตำแหน่งไฟล์/โฟลเดอร์ทั้งหมดของ Model A — single source of truth (ไม่ hardcode path ซ้ำในแต่ละไฟล์)"""

from pathlib import Path

MODEL_A = Path(__file__).resolve().parent.parent
REPO = MODEL_A.parent

DATA = MODEL_A / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"

CONSTITUENTS_DIR = RAW / "constituents"
SEC_DIR = RAW / "sec"
COMPANYFACTS_DIR = SEC_DIR / "companyfacts"
PRICES_DIR = RAW / "prices"

REPORTS = MODEL_A / "reports"
EXPORT = MODEL_A / "export"

# SEC บังคับ User-Agent ที่ระบุตัวตน (ผู้ใช้อนุมัติอีเมลนี้แล้วใน Phase 0)
SEC_USER_AGENT = "SNP-research boeing6677@gmail.com"

# pin commit ของ fja05680/sp500 ไว้เพื่อ reproducibility (ตรวจแล้ว 2026-09-27: อัปเดตล่าสุด 2026-09-07)
FJA_COMMIT = "a2430f2af0"

for _d in (RAW, INTERIM, CONSTITUENTS_DIR, SEC_DIR, COMPANYFACTS_DIR, PRICES_DIR, REPORTS, EXPORT):
    _d.mkdir(parents=True, exist_ok=True)
