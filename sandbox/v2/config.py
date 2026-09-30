"""
Config กลางของ sandbox v2 "Pipeline Lab" — single source of truth (ห้าม hardcode ค่าเหล่านี้ซ้ำในไฟล์อื่น)

เปลี่ยนช่วงราคา: แก้ PRICE_START บรรทัดเดียว (เช่น "2010-06-01") แล้วรัน
    python3 -m sandbox.v2.scripts.update_prices
ตัว updater จะดึงเฉพาะช่วงที่ยังไม่มี (ย้อนหลัง/ต่อท้าย) — โค้ดส่วนอื่นไม่ต้องแก้
"""

import json
import os
from pathlib import Path

# ช่วงราคา: ไม่ hardcode วันที่อีกต่อไป — คำนวณให้วันเริ่มซื้อขายตรงกับรอบ rebalance ของ A (ดู compute_start_dates ด้านล่าง)
IDEAL_LOOKBACK_YEARS = 5       # อยากทดสอบย้อนหลังประมาณกี่ปี (นับจากวันนี้)
INDICATOR_WARMUP_DAYS = 90     # วันทำการของราคาก่อนวันเริ่มซื้อขาย ให้ SMA50/EMA20/RSI14 คำนวณได้ตั้งแต่วันแรก (ไม่นับเป็นผล)
ANCHOR_A_VERSION = "A1_r001_Q_LOWACC_overall"  # กฎหลักของ A ที่ใช้เป็นหลักยึดรอบ rebalance
HELD_OUT_START = "2023-07-01"  # ตรงกับ Model A — ห้ามเปลี่ยนโดยไม่ถามผู้ใช้
DEFAULT_END = "2023-06-30"
TRANSACTION_COST = 0.001     # 0.10% ต่อขา ตรงกับ Model A
INITIAL_CAPITAL = 1_000_000
DECISION_FREQ = "daily"
EXECUTION = "next_close"     # signal ณ close วัน t → ซื้อขายที่ close วัน t+1
HOST, PORT = "127.0.0.1", int(os.environ.get("SANDBOX_V2_PORT", "5090"))  # ห้ามใช้ 5060: อยู่ใน unsafe port list ของ Chrome (SIP)

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
LOGOS_DIR = V2 / "static" / "logos"       # gitignored — โลโก้บริษัทที่ cache ไว้ (scripts/fetch_logos.py)



def _anchor_rebalance_dates() -> list:
    """วัน rebalance จริงของ A (ANCHOR_A_VERSION) — อ่านจาก manifest.json → signal_files ของ version นั้น (ห้าม hardcode)"""
    import pandas as pd

    d = REPO / "model_A" / "export" / ANCHOR_A_VERSION
    m = json.loads((d / "manifest.json").read_text())
    dates = set()
    for f in m["signal_files"]:
        dates.update(pd.to_datetime(pd.read_parquet(d / f, columns=["date"])["date"]).dt.normalize().unique())
    return sorted(pd.Timestamp(x) for x in dates)


def compute_start_dates(today=None, allow_held_out: bool = False, rebalance_dates=None, calendar=None,
                        lookback_years: int = None, warmup_days: int = None) -> dict:
    """วันเริ่มของข้อมูลราคา (warm-up) และวันเริ่มซื้อขายจริง ให้ตรงกับรอบ rebalance ของ A

    1. ideal_start = วันนี้ − IDEAL_LOOKBACK_YEARS ปี
    2. decision_start = rebalance date ล่าสุดที่ ≤ ideal_start (ได้จำนวนรอบมากสุด); ถ้าไม่มี → รอบแรกที่ ≥ ideal_start
       — ห้ามใช้รอบที่อยู่ใน held-out (≥ HELD_OUT_START) เว้นแต่ allow_held_out
    3. price_start = ถอยจาก decision_start ไป INDICATOR_WARMUP_DAYS วันทำการ (ราคา warm-up — ไม่ซื้อขาย ไม่นับเป็นผล)
       ใช้ปฏิทินวันทำการจริง (SPY) ถ้ามีข้อมูลครอบคลุม; ไม่งั้นประมาณด้วยวันทำการ + วันหยุดราชการสหรัฐ (+5 วันเผื่อ) — ครั้งแรกที่ยังไม่มีราคาช่วงนั้น
    """
    import pandas as pd
    from pandas.tseries.holiday import USFederalHolidayCalendar
    from pandas.tseries.offsets import CustomBusinessDay

    today = pd.Timestamp(today or pd.Timestamp.today()).normalize()
    years = IDEAL_LOOKBACK_YEARS if lookback_years is None else lookback_years
    warm = INDICATOR_WARMUP_DAYS if warmup_days is None else warmup_days
    ideal = today - pd.DateOffset(years=years)
    Rs = [pd.Timestamp(r) for r in (rebalance_dates if rebalance_dates is not None else _anchor_rebalance_dates())]
    if not allow_held_out:
        Rs = [r for r in Rs if r < pd.Timestamp(HELD_OUT_START)]
    before = [r for r in Rs if r <= ideal]
    after = [r for r in Rs if r >= ideal]
    if before:
        decision, how = max(before), "rebalance ล่าสุดที่ ≤ ideal_start"
    elif after:
        decision, how = min(after), "ไม่มีรอบก่อน ideal_start → รอบแรกหลังจากนั้น"
    else:
        decision, how = ideal, "ไม่พบรอบ rebalance ที่ใช้ได้ — ใช้ ideal_start ตรง ๆ"
    if calendar is None and (PRICES_DIR / f"{BENCHMARK}.parquet").exists():
        calendar = pd.read_parquet(PRICES_DIR / f"{BENCHMARK}.parquet").index
    exact = False
    if calendar is not None and len(calendar):
        cal = pd.DatetimeIndex(calendar).normalize()
        pos = int(cal.searchsorted(decision))  # วันทำการแรกที่ ≥ decision
        if pos - warm >= 0:
            price_start, exact = cal[pos - warm], True
    if not exact:
        price_start = decision - CustomBusinessDay(n=warm + 5, calendar=USFederalHolidayCalendar())
    return {"ideal_start": str(ideal.date()), "decision_start": str(decision.date()), "price_start": str(pd.Timestamp(price_start).date()),
            "warmup_days": warm, "warmup_exact": exact, "anchor": ANCHOR_A_VERSION, "rule": how,
            "lookback_years": years, "today": str(today.date())}


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


# ---- วันเริ่ม (คำนวณครั้งเดียวตอน import) — ผลการทดลองเก่าใช้ start/end ที่บันทึกไว้ใน config.json ของตัวเอง ไม่ใช้ค่านี้ย้อนหลัง
try:
    START_DATES = compute_start_dates()
except Exception as _e:  # noqa: BLE001 — ไม่มี export ของ A (เช่น clone ใหม่) → ใช้ ideal_start ตรง ๆ แต่บอกไว้
    import pandas as _pd
    _ideal = (_pd.Timestamp.today().normalize() - _pd.DateOffset(years=IDEAL_LOOKBACK_YEARS)).date()
    START_DATES = {"ideal_start": str(_ideal), "decision_start": str(_ideal), "price_start": str(_ideal), "warmup_days": 0,
                   "warmup_exact": False, "anchor": ANCHOR_A_VERSION, "rule": f"อ่านรอบ rebalance ของ A ไม่ได้: {_e}"}
PRICE_START = START_DATES["price_start"]        # ราคาเริ่มมี (warm-up indicator)
DECISION_START = START_DATES["decision_start"]  # วันเริ่มซื้อขายจริง (ค่าเริ่มต้นของ run) = วัน rebalance ของ A
