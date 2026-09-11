"""
Simulation engine (Strategy engine) — วน day-by-day ตามช่วงวันที่ที่เลือก เรียก
`strategy.on_day()` ทุกวัน บันทึก trade log เต็ม (ซื้อ/ขาย/DCA วันไหน ราคาเท่าไหร่ เหตุผล
อะไร) + มูลค่าพอร์ตรายวัน

signal ที่ป้อนให้ strategy ต่อ (ticker, date):
    - a: `model_a.predict(ticker, date)` เสมอ (stub, ตอบได้ทุกวัน)
    - b: manual company (B) event **ตรงวันนั้นเป๊ะ**เท่านั้น (ไม่ forward-fill, ไม่มี
      historical data จริงของ Model B เลย — ดู sandbox/inference/README.md)
    - c: manual macro (C) event + real historical macro data (477 ข่าว FOMC/Beige Book —
      เหมือนที่ Dashboard ใช้แสดง marker) **ตรงวันนั้นเป๊ะ**เท่านั้น ถ้าวันเดียวกันมีทั้ง
      manual และ real historical event พร้อมกัน (กรณีหายาก) manual ชนะ (ผู้ใช้ inject เอง
      เจาะจงกว่า general historical data)

⚠️ ไม่ forward-fill สัญญาณข้ามวัน — วันที่ไม่มี event จริงของ ticker นั้น b/c จะเป็น None
และ strategy (เช่น strategy_v1) จะไม่ trigger อะไรสำหรับ ticker นั้นในวันนั้น นี่คือการ
ตัดสินใจตาม "ห้ามเดา" ไม่ใช่บั๊ก
"""

import importlib
import re
from pathlib import Path

import pandas as pd

from sandbox import events_store, historical_data
from sandbox.analytics import metrics as metrics_module
from sandbox.inference import model_a
from sandbox.strategy.base import PortfolioState

PRICES_DIR = Path(__file__).resolve().parent.parent / "data" / "prices"
STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategy"
STRATEGY_MODULE_RE = re.compile(r"^strategy_v\d+$")


def list_available_strategies() -> list:
    """สแกน sandbox/strategy/strategy_v*.py ที่มีอยู่จริง (ไม่รวม base.py) เรียงชื่อ"""
    names = [
        f.stem for f in STRATEGY_DIR.glob("strategy_*.py") if STRATEGY_MODULE_RE.match(f.stem)
    ]
    return sorted(names)


def load_strategy(name: str):
    if not STRATEGY_MODULE_RE.match(name):
        raise ValueError(f"strategy module name ต้องเป็นรูปแบบ 'strategy_v{{N}}' (ได้ {name!r})")
    try:
        module = importlib.import_module(f"sandbox.strategy.{name}")
    except ModuleNotFoundError as e:
        # เช็ค e.name ให้ชัดว่าเป็น module ที่เราพยายาม import เอง ไม่ใช่ import ที่พังข้างใน
        # ไฟล์ strategy (เช่น strategy_v2.py พิมพ์ import ผิด) — กรณีนั้นควรเห็น traceback จริง
        if e.name == f"sandbox.strategy.{name}":
            raise FileNotFoundError(
                f"ไม่พบ sandbox/strategy/{name}.py — strategy ที่มีอยู่จริง: {list_available_strategies()}"
            ) from e
        raise
    if not hasattr(module, "STRATEGY"):
        raise ValueError(
            f"sandbox.strategy.{name} ไม่มี STRATEGY (module-level singleton instance ของ Strategy)"
        )
    return module.STRATEGY


def _load_price_series(ticker: str, start: str, end: str) -> dict:
    """คืน {date: close_price} ของ ticker ในช่วง [start, end]"""
    csv_path = PRICES_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ราคา {csv_path.name}")
    df = pd.read_csv(csv_path)
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.strftime("%Y-%m-%d")
    df = df[(df["Date"] >= start) & (df["Date"] <= end)]
    return dict(zip(df["Date"], df["Close"].round(4)))


def _build_signal_index(ticker_set: list, start: str, end: str) -> tuple:
    """คืน (b_index, c_index) — {(ticker, date): class} จาก manual event + real historical
    (สำหรับ C) เฉพาะวันที่ตรงเป๊ะ ไม่ forward-fill"""
    b_index, c_index = {}, {}
    for ticker in ticker_set:
        manual = events_store.list_events_for_ticker(ticker)
        for e in manual["b"]:
            if start <= e["date"] <= end:
                b_index[(ticker, e["date"])] = e["class"]

        real_c = historical_data.load_real_macro_events_for_ticker(ticker)
        # ใส่ real historical ก่อน แล้วค่อยใส่ manual ทับ — ถ้าวันเดียวกันมีทั้งคู่ manual
        # ชนะ (ผู้ใช้ inject เองเจาะจงกว่า) ดู docstring ของไฟล์นี้
        for e in real_c:
            if start <= e["date"] <= end:
                c_index[(ticker, e["date"])] = e["class"]
        for e in manual["c"]:
            if start <= e["date"] <= end:
                c_index[(ticker, e["date"])] = e["class"]
    return b_index, c_index


def run_simulation(strategy_name: str, ticker_set: list, start: str, end: str, initial_cash: float) -> dict:
    if not ticker_set:
        raise ValueError("ticker_set ห้ามว่าง")
    if start > end:
        raise ValueError(f"start ({start}) ต้องไม่มากกว่า end ({end})")
    if initial_cash <= 0:
        raise ValueError("initial_cash ต้องมากกว่า 0")

    strategy = load_strategy(strategy_name)

    price_by_ticker = {t: _load_price_series(t, start, end) for t in ticker_set}
    all_dates = set()
    for series in price_by_ticker.values():
        all_dates.update(series.keys())
    dates = sorted(all_dates)

    b_index, c_index = _build_signal_index(ticker_set, start, end)

    portfolio = PortfolioState(cash=float(initial_cash))
    trade_log = []
    portfolio_value_series = []

    for date in dates:
        signals_per_ticker = {}
        for ticker in ticker_set:
            price = price_by_ticker[ticker].get(date)
            a_class = model_a.predict(ticker, date)["class"]
            signals_per_ticker[ticker] = {
                "a": a_class,
                "b": b_index.get((ticker, date)),
                "c": c_index.get((ticker, date)),
                "price": price,
            }

        actions = strategy.on_day(date, signals_per_ticker, portfolio)
        for act in actions:
            trade_log.append({"date": date, **act})

        day_prices = {t: signals_per_ticker[t]["price"] for t in ticker_set}
        value = portfolio.value(day_prices)
        portfolio_value_series.append(
            {"date": date, "value": round(value, 2), "cash": round(portfolio.cash, 2)}
        )

    final_value = portfolio_value_series[-1]["value"] if portfolio_value_series else float(initial_cash)

    strategy_metrics = metrics_module.compute_metrics(trade_log, portfolio_value_series, float(initial_cash))
    benchmark = metrics_module.compute_buy_and_hold(price_by_ticker, dates, ticker_set, float(initial_cash))

    return {
        "strategy": strategy.name,
        "ticker_set": ticker_set,
        "start": start,
        "end": end,
        "initial_cash": float(initial_cash),
        "final_value": final_value,
        "trade_log": trade_log,
        "portfolio_value_series": portfolio_value_series,
        "final_holdings": {t: round(s, 6) for t, s in portfolio.holdings.items() if s},
        "final_cash": round(portfolio.cash, 2),
        "metrics": strategy_metrics,
        "benchmark": benchmark,
    }
