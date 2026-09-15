"""
fetch_fundamentals.py — pre-fetch fundamental snapshot (P/E, market cap, EPS ฯลฯ) ของทุก
ticker ใน universe ผ่าน `sandbox/fundamentals.py` แล้วเก็บ cache ไว้ล่วงหน้า (แทนที่จะรอให้
dashboard เรียกครั้งแรกแล้วช้า/ชนกันถ้าเปิดหลาย ticker พร้อมกัน)

Alpha Vantage free tier = 5 req/min, 25 req/day รวมทุก endpoint ของ key เดียวกัน (ใช้ key
เดียวกับ collect_alpha_vantage.py) — universe มีแค่ 5 ticker พอดี เผื่อ margin sleep 15s/ครั้ง

รัน (จาก project root): python3 -m sandbox.scripts.fetch_fundamentals
"""

import time

from sandbox import config, fundamentals

RATE_LIMIT_SLEEP = 15  # 5 req/min ของ free tier -> อย่างน้อย 12s/ครั้ง เผื่อ margin


def main():
    for i, ticker in enumerate(config.TICKERS):
        result = fundamentals.get_fundamentals(ticker, force_refresh=True)
        if result.get("error"):
            print(f"[{ticker}] error: {result['error']}")
        else:
            print(
                f"[{ticker}] {result.get('name')}: PE={result.get('pe_ratio')} "
                f"MarketCap={result.get('market_cap')} EPS={result.get('eps')}"
            )
        if i < len(config.TICKERS) - 1:
            time.sleep(RATE_LIMIT_SLEEP)


if __name__ == "__main__":
    main()
