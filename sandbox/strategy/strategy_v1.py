"""
strategy_v1 — ตามตัวอย่างที่ผู้ใช้ระบุ:
    1. C=negative (ของ ticker นั้น วันนั้น) -> sell ทั้งหมดที่ถืออยู่ + จำราคาขาย
    2. cash ที่ว่างอยู่ (รวมจากการขาย) -> DCA เข้า ticker ที่ C=positive วันนั้น
    3. ถ้าราคาตกจากจุดขายเดิม -20% -> ซื้อคืน

**รายละเอียดที่ตัวอย่างไม่ได้ระบุ ต้องตัดสินใจเอง** (documented ตรงนี้เพื่อความโปร่งใส —
ถ้าไม่ตรงกับที่ตั้งใจไว้ แก้ไฟล์นี้ได้ตรงๆ หรือ copy เป็น strategy_v2.py แล้วปรับ):
    - ใช้ C ของ**วันนั้นเป๊ะ**เท่านั้น (ไม่ forward-fill จากวันก่อนหน้า) — วันที่ไม่มี C event
      ของ ticker นั้น ก็ไม่ trigger อะไรสำหรับ ticker นั้นในวันนั้นเลย
    - DCA (ถ้ามีหลาย ticker เป็น C=positive วันเดียวกัน): หารเงินสดเท่าๆ กันทุกตัว (ไม่ได้
      เลือก "ตัวเดียวที่ positive ที่สุด" เพราะ C ไม่มี score ต่อเนื่องให้เทียบใน signal ที่
      ส่งเข้ามา มีแค่ class)
    - ลำดับการรันในโค้ด: sell -> ซื้อคืน (-20%) -> DCA (สลับจากลำดับที่ยกตัวอย่างมา ซึ่งเป็น
      sell -> DCA -> ซื้อคืน) เพื่อให้เงินสดที่เพิ่งขายได้วันนี้ถูกพิจารณา "ซื้อคืน" (ตัว
      เดิมที่เพิ่งขาย ถ้าราคาตกต่อจนเข้าเงื่อนไข -20% จากจุดขายในวันก่อนๆ) ก่อนเอาไป DCA เข้า
      ticker อื่นที่ไม่เกี่ยวข้อง — ถ้ามีหลาย ticker เข้าเงื่อนไข -20% พร้อมกัน หารเงินเท่าๆ
      กันเหมือน DCA ซื้อคืนแล้วเคลียร์ last_sell_price ของ ticker นั้นทันที (กันซื้อคืนซ้ำที่
      จุดเดิมทุกวันที่ราคายังต่ำกว่า -20% ต่อเนื่อง)
"""

from sandbox.strategy.base import PortfolioState, Strategy

BUYBACK_DROP_THRESHOLD = 0.20  # -20% จากราคาขายล่าสุด


class StrategyV1(Strategy):
    name = "strategy_v1"

    def on_day(self, date: str, signals_per_ticker: dict, portfolio_state: PortfolioState) -> list:
        actions = []

        # sell: C=negative -> sell ทั้งหมดที่ถืออยู่ + จำราคาขาย
        for ticker, sig in signals_per_ticker.items():
            price = sig.get("price")
            if price is None or sig.get("c") != "negative":
                continue
            shares = portfolio_state.holdings.get(ticker, 0)
            if shares <= 0:
                continue
            proceeds = shares * price
            portfolio_state.cash += proceeds
            portfolio_state.holdings[ticker] = 0
            portfolio_state.last_sell_price[ticker] = price
            actions.append(
                {
                    "type": "sell",
                    "ticker": ticker,
                    "shares": round(shares, 6),
                    "price": round(price, 4),
                    "reason": f"C=negative on {date}",
                }
            )

        # ซื้อคืน: ราคาตก -20% จากจุดขายเดิม -> ซื้อคืน (เช็คก่อน DCA เสมอ — ดูเหตุผลลำดับใน docstring)
        buyback_tickers = [
            t
            for t, sell_price in portfolio_state.last_sell_price.items()
            if sell_price is not None
            and signals_per_ticker.get(t, {}).get("price") is not None
            and signals_per_ticker[t]["price"] <= sell_price * (1 - BUYBACK_DROP_THRESHOLD)
        ]
        if buyback_tickers and portfolio_state.cash > 0:
            amount_each = portfolio_state.cash / len(buyback_tickers)
            for ticker in buyback_tickers:
                price = signals_per_ticker[ticker]["price"]
                sell_price = portfolio_state.last_sell_price[ticker]
                if price <= 0 or amount_each <= 0:
                    continue
                shares = amount_each / price
                portfolio_state.cash -= amount_each
                portfolio_state.holdings[ticker] = portfolio_state.holdings.get(ticker, 0) + shares
                drop_pct = (sell_price - price) / sell_price * 100
                actions.append(
                    {
                        "type": "buy",
                        "ticker": ticker,
                        "shares": round(shares, 6),
                        "price": round(price, 4),
                        "reason": f"price dropped {drop_pct:.1f}% from last sell "
                        f"({sell_price:.2f}) on {date}",
                    }
                )
                portfolio_state.last_sell_price[ticker] = None  # เคลียร์กันซื้อคืนซ้ำที่จุดเดิม

        # DCA: cash ที่เหลือ -> DCA เข้า ticker ที่ C=positive วันนี้ (หารเท่ากัน)
        positive_tickers = [
            t
            for t, sig in signals_per_ticker.items()
            if sig.get("c") == "positive" and sig.get("price") is not None
        ]
        if positive_tickers and portfolio_state.cash > 0:
            amount_each = portfolio_state.cash / len(positive_tickers)
            for ticker in positive_tickers:
                price = signals_per_ticker[ticker]["price"]
                if price <= 0 or amount_each <= 0:
                    continue
                shares = amount_each / price
                portfolio_state.cash -= amount_each
                portfolio_state.holdings[ticker] = portfolio_state.holdings.get(ticker, 0) + shares
                actions.append(
                    {
                        "type": "dca",
                        "ticker": ticker,
                        "shares": round(shares, 6),
                        "price": round(price, 4),
                        "reason": f"C=positive on {date}, DCA idle cash",
                    }
                )

        return actions


STRATEGY = StrategyV1()
