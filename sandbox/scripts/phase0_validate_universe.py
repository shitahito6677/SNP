"""
Phase 0 — Data validation สำหรับ ensemble sandbox (Model A+B+C)

ตรวจสอบจริงด้วยโค้ด (ห้ามสมมติ ตาม CLAUDE.md):
1. ดึงรายชื่อ S&P 500 ปัจจุบันจาก Wikipedia (pandas.read_html) แล้วเช็คว่า
   NVDA, META, TSLA, SCHW, FDX ยังอยู่ในลิสต์จริงหรือไม่
2. ดึง GICS sector ปัจจุบันของแต่ละตัวจากแหล่งเดียวกัน แล้ว map ไปยัง sector ETF
   ที่ Model C ใช้เทรน
3. ดึง OHLCV รายวัน 5 ปีล่าสุดของทั้ง 5 ตัวด้วย yfinance เก็บเป็น
   sandbox/data/prices/{TICKER}.csv
4. เขียนสรุปผลลงท sandbox/data/validation_report.md

รัน: python3 sandbox/scripts/phase0_validate_universe.py
"""

import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

SANDBOX_DIR = Path(__file__).resolve().parent.parent
PRICES_DIR = SANDBOX_DIR / "data" / "prices"
REPORT_PATH = SANDBOX_DIR / "data" / "validation_report.md"

TICKERS = ["NVDA", "META", "TSLA", "SCHW", "FDX"]

# Sector -> ETF mapping ที่ Model C ใช้เทรน (ตามที่ระบุใน brief)
EXPECTED_SECTOR_ETF = {
    "Information Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Financials": "XLF",
    "Industrials": "XLI",
}

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKI_HEADERS = {
    "User-Agent": "SNP-sandbox-research-script/1.0 (contact: boeing6677@gmail.com)"
}


def fetch_sp500_table() -> pd.DataFrame:
    """ดึงตาราง S&P 500 constituents ปัจจุบันจาก Wikipedia จริง (ไม่ hardcode)."""
    req = urllib.request.Request(WIKI_URL, headers=WIKI_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read()
    tables = pd.read_html(html)
    # ตารางแรกของหน้านี้คือ constituents table (Symbol, Security, GICS Sector, ...)
    df = tables[0]
    df.columns = [str(c).strip() for c in df.columns]
    # Wikipedia ใช้ตัวคั่น "." บางครั้ง (เช่น BRK.B) — yfinance ใช้ "-" (BRK-B)
    df["Symbol"] = df["Symbol"].astype(str).str.strip()
    return df


def main() -> int:
    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    report_lines = []
    report_lines.append("# Phase 0 — Data Validation Report")
    report_lines.append("")
    report_lines.append(f"รันเมื่อ: {run_ts}")
    report_lines.append(f"Source รายชื่อ S&P 500 / GICS sector: {WIKI_URL}")
    report_lines.append("")

    # --- Step 1+2: S&P 500 membership + GICS sector ---
    print("Fetching current S&P 500 constituent list from Wikipedia...")
    try:
        sp500_df = fetch_sp500_table()
    except Exception as e:
        print(f"FATAL: fetch S&P500 list failed: {e}", file=sys.stderr)
        report_lines.append("## ผล: FAILED")
        report_lines.append("")
        report_lines.append(f"ดึงรายชื่อ S&P 500 จาก Wikipedia ไม่สำเร็จ: `{e}`")
        REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
        return 1

    sector_col = "GICS Sector"
    if sector_col not in sp500_df.columns:
        # เผื่อ Wikipedia เปลี่ยนชื่อคอลัมน์ในอนาคต
        candidates = [c for c in sp500_df.columns if "sector" in c.lower()]
        sector_col = candidates[0] if candidates else None

    sp500_symbols = set(sp500_df["Symbol"])
    print(f"Fetched {len(sp500_symbols)} S&P 500 constituents from Wikipedia.")

    row_results = []
    for ticker in TICKERS:
        in_sp500 = ticker in sp500_symbols
        if in_sp500 and sector_col:
            match = sp500_df.loc[sp500_df["Symbol"] == ticker, sector_col]
            actual_sector = match.iloc[0] if not match.empty else None
        else:
            actual_sector = None
        row_results.append(
            {"ticker": ticker, "in_sp500": in_sp500, "actual_sector": actual_sector}
        )
        status = "IN S&P500" if in_sp500 else "NOT FOUND IN S&P500"
        print(f"  {ticker}: {status}, GICS sector = {actual_sector}")

    # --- Step 3: OHLCV 5y via yfinance ---
    print("\nDownloading 5y daily OHLCV via yfinance...")
    price_results = []
    for ticker in TICKERS:
        try:
            hist = yf.Ticker(ticker).history(period="5y", interval="1d", auto_adjust=False)
        except Exception as e:
            print(f"  {ticker}: download FAILED ({e})", file=sys.stderr)
            price_results.append(
                {"ticker": ticker, "rows": 0, "start": None, "end": None, "error": str(e)}
            )
            continue

        if hist.empty:
            print(f"  {ticker}: download returned 0 rows", file=sys.stderr)
            price_results.append(
                {"ticker": ticker, "rows": 0, "start": None, "end": None, "error": "empty"}
            )
            continue

        hist = hist.reset_index()
        csv_path = PRICES_DIR / f"{ticker}.csv"
        hist.to_csv(csv_path, index=False)
        n_rows = len(hist)
        start_date = hist["Date"].min()
        end_date = hist["Date"].max()
        price_results.append(
            {
                "ticker": ticker,
                "rows": n_rows,
                "start": start_date,
                "end": end_date,
                "error": None,
            }
        )
        print(f"  {ticker}: {n_rows} rows, {start_date} -> {end_date} -> {csv_path}")

    # --- Build report ---
    report_lines.append("## สรุปผลรายตัว")
    report_lines.append("")
    report_lines.append(
        "| Ticker | ใน S&P500 ตอนนี้? | GICS Sector (จาก Wikipedia) | Expected Sector (brief) | Sector ตรงกับ brief? | Sector ETF (Model C) | Rows ราคา | ช่วงวันที่ |"
    )
    report_lines.append("|---|---|---|---|---|---|---|---|")

    expected_sectors = {
        "NVDA": "Information Technology",
        "META": "Communication Services",
        "TSLA": "Consumer Discretionary",
        "SCHW": "Financials",
        "FDX": "Industrials",
    }

    price_by_ticker = {r["ticker"]: r for r in price_results}
    all_ok = True
    for row in row_results:
        ticker = row["ticker"]
        in_sp500 = row["in_sp500"]
        actual_sector = row["actual_sector"]
        expected_sector = expected_sectors[ticker]
        sector_match = actual_sector == expected_sector
        etf = EXPECTED_SECTOR_ETF.get(expected_sector, "?")
        p = price_by_ticker.get(ticker, {})
        rows_n = p.get("rows", 0)
        date_range = (
            f"{p['start']} → {p['end']}" if p.get("start") is not None else "N/A"
        )

        if not in_sp500 or not sector_match or rows_n == 0:
            all_ok = False

        report_lines.append(
            f"| {ticker} | {'✅ ใช่' if in_sp500 else '❌ ไม่พบ'} | "
            f"{actual_sector or 'N/A'} | {expected_sector} | "
            f"{'✅ ตรง' if sector_match else '⚠️ ไม่ตรง'} | {etf} | "
            f"{rows_n} | {date_range} |"
        )

    report_lines.append("")
    report_lines.append("## สถานะโดยรวม")
    report_lines.append("")
    if all_ok:
        report_lines.append(
            "✅ ผ่าน — ทั้ง 5 ตัวอยู่ใน S&P500 ปัจจุบัน, sector ตรงกับที่ brief ระบุ, "
            "และดึงราคาได้ครบทุกตัว → **Phase 0 done, พร้อมไป Phase 1**"
        )
    else:
        report_lines.append(
            "⚠️ ยังไม่ผ่านทั้งหมด — มีตัวที่ไม่อยู่ใน S&P500, sector ไม่ตรง, หรือดึงราคาไม่สำเร็จ "
            "→ ดูรายละเอียดในตารางด้านบนก่อนไป Phase 1"
        )

    report_lines.append("")
    report_lines.append("## Sector → ETF mapping ที่ใช้ (จาก brief, สำหรับ Model C)")
    report_lines.append("")
    for sector, etf in EXPECTED_SECTOR_ETF.items():
        report_lines.append(f"- {sector} → `{etf}`")

    report_lines.append("")
    report_lines.append("## หมายเหตุ")
    report_lines.append("")
    report_lines.append(
        "- รายชื่อ/sector S&P500 ดึงสดจาก Wikipedia ณ เวลารัน อาจเปลี่ยนแปลงได้ในอนาคต "
        "(เช่น ถ้ามีการปรับ index หรือปรับ GICS classification) ควรรัน script นี้ใหม่ก่อนใช้งานจริงทุกครั้งที่ห่างจากวันที่รันนี้นาน"
    )
    report_lines.append(
        "- ไฟล์ราคาดิบ (`sandbox/data/prices/{TICKER}.csv`) มาจาก `yfinance`, "
        "field: Date, Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits"
    )

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"\nWrote report to {REPORT_PATH}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
