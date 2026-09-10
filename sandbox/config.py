"""
Shared config สำหรับ sandbox ทั้งหมด (Phase 0-5) — single source of truth
สำหรับ universe / sector mapping เพื่อไม่ให้ script/app แต่ละส่วนแยกกัน hardcode ซ้ำ

แหล่งที่มา: ยืนยันจริงแล้วใน sandbox/data/validation_report.md (Phase 0)
"""

from pathlib import Path

import pandas as pd

PRICES_DIR = Path(__file__).resolve().parent / "data" / "prices"

# หุ้น 5 ตัวใน sandbox universe (คนละ sector ตาม brief)
TICKERS = ["NVDA", "META", "TSLA", "SCHW", "FDX"]

# ticker ไหนมี company-level news ให้ inject event แบบ B ได้ (ตอนนี้ทุกตัว เพราะ Model B ยัง
# เป็น stub ที่รับ headline อะไรก็ได้ — placeholder ไว้เผื่ออนาคตที่ Model B จริงอาจไม่ cover
# ทุก ticker ใน universe) UI ใช้ set นี้ตัดสินใจ disable ปุ่ม B อัตโนมัติ
TICKERS_WITH_COMPANY_NEWS = set(TICKERS)

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


def has_company_news(ticker: str) -> bool:
    return ticker in TICKERS_WITH_COMPANY_NEWS


def price_date_range() -> tuple:
    """อ่านช่วงวันที่จริงจากไฟล์ราคา (intersection ของทั้ง 5 ตัว) ไม่ hardcode — ใช้จำกัด
    date picker ของ manual event injection (Phase 3) ให้อยู่ในช่วง 5 ปีที่มีข้อมูลราคาจริง
    คืน (min_date, max_date) เป็น string "YYYY-MM-DD" """
    starts, ends = [], []
    for ticker in TICKERS:
        csv_path = PRICES_DIR / f"{ticker}.csv"
        df = pd.read_csv(csv_path, usecols=["Date"])
        dates = pd.to_datetime(df["Date"], utc=True).dt.strftime("%Y-%m-%d")
        starts.append(dates.min())
        ends.append(dates.max())
    # intersection: วันที่ล่าสุดในบรรดา start ทั้งหมด, วันที่เก่าสุดในบรรดา end ทั้งหมด
    # (กันกรณีไฟล์ใดไฟล์หนึ่งมีช่วงสั้นกว่าตัวอื่นในอนาคต)
    return max(starts), min(ends)
