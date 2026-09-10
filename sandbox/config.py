"""
Shared config สำหรับ sandbox ทั้งหมด (Phase 0-5) — single source of truth
สำหรับ universe / sector mapping เพื่อไม่ให้ script/app แต่ละส่วนแยกกัน hardcode ซ้ำ

แหล่งที่มา: ยืนยันจริงแล้วใน sandbox/data/validation_report.md (Phase 0)
"""

# หุ้น 5 ตัวใน sandbox universe (คนละ sector ตาม brief)
TICKERS = ["NVDA", "META", "TSLA", "SCHW", "FDX"]

# ticker -> GICS sector (ยืนยันจาก Wikipedia ใน Phase 0)
TICKER_SECTOR = {
    "NVDA": "Information Technology",
    "META": "Communication Services",
    "TSLA": "Consumer Discretionary",
    "SCHW": "Financials",
    "FDX": "Industrials",
}

# GICS sector -> sector ETF ที่ Model C ใช้เทรน
SECTOR_ETF = {
    "Information Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Financials": "XLF",
    "Industrials": "XLI",
}


def ticker_to_sector(ticker: str) -> str:
    if ticker not in TICKER_SECTOR:
        raise ValueError(
            f"'{ticker}' ไม่อยู่ใน sandbox universe ({TICKERS}) — "
            "ถ้าต้องการเพิ่มตัวใหม่ ต้องรัน Phase 0 validation ก่อน"
        )
    return TICKER_SECTOR[ticker]


def ticker_to_etf(ticker: str) -> str:
    return SECTOR_ETF[ticker_to_sector(ticker)]
