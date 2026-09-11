"""
Strategy interface — day-by-day trading simulation, separate from the static `rule_v*.json`
lookup table (`sandbox/rules/` + `sandbox/engine/combine.py`). A strategy receives the day's
signals per ticker (A/B/C class + that day's closing price) and the current portfolio state,
mutates the portfolio directly (sell/buy/DCA), and returns the actions taken for the trade log.

⚠️ ผลจำลองจาก strategy ใช้ signal จาก Model A/B/C ที่ (ส่วนใหญ่) ยังเป็น stub — ทดสอบว่า
logic ของ strategy ทำงานถูกต้องตามที่เขียนไว้เท่านั้น ไม่ใช่การทดสอบว่ากลยุทธ์นี้จะกำไรจริง
(banner นี้บังคับแสดงในหน้า Strategies เสมอ — ดู sandbox/templates/strategies.html)
"""

from dataclasses import dataclass, field


@dataclass
class PortfolioState:
    """cash, holdings (ticker -> shares), และ last_sell_price (ticker -> ราคาตอนขายล่าสุด)
    ตามที่กำหนด — ต้องมี last_sell_price เพื่อให้ strategy เช็คเงื่อนไข "-20% จากจุดขายเดิม" ได้"""

    cash: float
    holdings: dict = field(default_factory=dict)
    last_sell_price: dict = field(default_factory=dict)

    def value(self, prices: dict) -> float:
        """มูลค่าพอร์ตรวม ณ ราคาที่ให้มา (cash + holdings ทุกตัว คูณราคาวันนั้น)
        prices: {ticker: price|None} — ticker ที่ไม่มีราคาวันนั้น (None) ไม่นับรวม"""
        total = self.cash
        for ticker, shares in self.holdings.items():
            price = prices.get(ticker)
            if shares and price is not None:
                total += shares * price
        return total


class Strategy:
    """Base class — strategy ทุกตัวใน sandbox/strategy/strategy_v{N}.py ต้อง subclass นี้
    และ expose `STRATEGY = <ClassName>()` เป็น module-level singleton (ดู strategy_v1.py)"""

    name = "base"

    def on_day(self, date: str, signals_per_ticker: dict, portfolio_state: PortfolioState) -> list:
        """
        Args:
            date: "YYYY-MM-DD"
            signals_per_ticker: {ticker: {"a": str|None, "b": str|None, "c": str|None,
                "price": float|None}}
                - "a": Model A class (มักไม่ใช่ None เพราะ Model A เป็น stub ที่ตอบได้ทุกวัน)
                - "b"/"c": None ถ้าวันนั้นไม่มี event/signal จริงของ ticker นั้น — **ไม่
                  forward-fill จากวันก่อนหน้า ไม่เดา** (ดู sandbox/engine/simulate.py)
                - "price": ราคาปิดวันนั้น (None ถ้าไม่มีข้อมูลราคาของ ticker นั้นในวันนั้น)
            portfolio_state: PortfolioState — strategy แก้ cash/holdings/last_sell_price
                ตรงๆ ได้เลย (mutate in place) engine **ไม่ validate ว่า cash ติดลบหรือไม่**
                — strategy ต้องเช็คเองก่อนซื้อ/DCA

        Returns:
            list ของ action dict {"type": "sell"|"buy"|"dca", "ticker": str, "shares": float,
            "price": float, "reason": str} — สำหรับ trade log เท่านั้น (portfolio ถูกแก้ไป
            แล้วข้างในฟังก์ชันนี้โดยตรง ไม่ได้ apply ซ้ำจาก action list ทีหลัง)
        """
        raise NotImplementedError
