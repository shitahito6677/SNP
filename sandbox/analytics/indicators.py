"""
Technical indicators — คำนวณจากราคาที่มีอยู่แล้วใน sandbox/data/prices/{TICKER}.csv เท่านั้น
ไม่ดึงข้อมูลใหม่ ไม่เรียก API ภายนอก ไม่ใช่ signal จากโมเดล (deterministic, ไม่ใช่ stub)

Indicators:
    - SMA20, SMA50   : simple moving average ของ Close
    - RSI(14)         : Wilder's smoothing (มาตรฐานที่ใช้กันทั่วไปที่สุด เช่น TradingView default)
    - MACD(12,26,9)   : EMA12 - EMA26, signal = EMA9 ของ MACD line, histogram = MACD - signal
    - Volume          : pass-through จากไฟล์ราคาเดิม (ไม่ต้องคำนวณอะไรเพิ่ม)
"""

import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window, min_periods=window).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI มาตรฐาน (Wilder's smoothing ผ่าน exponential moving average alpha=1/period)"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    result = 100 - (100 / (1 + rs))
    # avg_loss == 0 (ราคาขึ้นต่อเนื่องไม่มีวันลงเลยในช่วง period) -> rs = inf -> RSI ควรเป็น 100
    result = result.where(avg_loss != 0, 100.0)
    return result


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """df ต้องมีคอลัมน์ 'Close' คืน DataFrame ใหม่ (ไม่แก้ df เดิม) ที่มีคอลัมน์ indicator
    เพิ่ม: sma20, sma50, rsi14, macd, macd_signal, macd_hist

    หมายเหตุ: ต้องคำนวณจาก**ราคาย้อนหลังเต็มช่วง**เสมอ (ไม่ใช่แค่ช่วงวันที่ที่ user เลือกดู)
    แล้วค่อย filter วันที่ทีหลัง — ไม่งั้น SMA50/MACD ของวันแรกๆ ในช่วงที่เลือกจะเป็น NaN
    เพราะไม่มีข้อมูลย้อนหลังพอ (ดู sandbox/app/server.py ตอนเรียกใช้ function นี้)
    """
    out = df.copy()
    out["sma20"] = sma(df["Close"], 20)
    out["sma50"] = sma(df["Close"], 50)
    out["rsi14"] = rsi(df["Close"], 14)
    macd_line, signal_line, hist = macd(df["Close"])
    out["macd"] = macd_line
    out["macd_signal"] = signal_line
    out["macd_hist"] = hist
    return out
