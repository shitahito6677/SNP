# Phase 0 — Data Validation Report

รันเมื่อ: 2026-09-11T01:53:32+07:00
Source รายชื่อ S&P 500 / GICS sector: https://en.wikipedia.org/wiki/List_of_S%26P_500_companies

## สรุปผลรายตัว

| Ticker | ใน S&P500 ตอนนี้? | GICS Sector (จาก Wikipedia) | Expected Sector (brief) | Sector ตรงกับ brief? | Sector ETF (Model C) | Rows ราคา | ช่วงวันที่ |
|---|---|---|---|---|---|---|---|
| NVDA | ✅ ใช่ | Information Technology | Information Technology | ✅ ตรง | XLK | 1255 | 2021-09-10 00:00:00-04:00 → 2026-09-10 00:00:00-04:00 |
| META | ✅ ใช่ | Communication Services | Communication Services | ✅ ตรง | XLC | 1255 | 2021-09-10 00:00:00-04:00 → 2026-09-10 00:00:00-04:00 |
| TSLA | ✅ ใช่ | Consumer Discretionary | Consumer Discretionary | ✅ ตรง | XLY | 1255 | 2021-09-10 00:00:00-04:00 → 2026-09-10 00:00:00-04:00 |
| SCHW | ✅ ใช่ | Financials | Financials | ✅ ตรง | XLF | 1255 | 2021-09-10 00:00:00-04:00 → 2026-09-10 00:00:00-04:00 |
| FDX | ✅ ใช่ | Industrials | Industrials | ✅ ตรง | XLI | 1255 | 2021-09-10 00:00:00-04:00 → 2026-09-10 00:00:00-04:00 |

## สถานะโดยรวม

✅ ผ่าน — ทั้ง 5 ตัวอยู่ใน S&P500 ปัจจุบัน, sector ตรงกับที่ brief ระบุ, และดึงราคาได้ครบทุกตัว → **Phase 0 done, พร้อมไป Phase 1**

## Sector → ETF mapping ที่ใช้ (จาก brief, สำหรับ Model C)

- Information Technology → `XLK`
- Communication Services → `XLC`
- Consumer Discretionary → `XLY`
- Financials → `XLF`
- Industrials → `XLI`

## หมายเหตุ

- รายชื่อ/sector S&P500 ดึงสดจาก Wikipedia ณ เวลารัน อาจเปลี่ยนแปลงได้ในอนาคต (เช่น ถ้ามีการปรับ index หรือปรับ GICS classification) ควรรัน script นี้ใหม่ก่อนใช้งานจริงทุกครั้งที่ห่างจากวันที่รันนี้นาน
- ไฟล์ราคาดิบ (`sandbox/data/prices/{TICKER}.csv`) มาจาก `yfinance`, field: Date, Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits
