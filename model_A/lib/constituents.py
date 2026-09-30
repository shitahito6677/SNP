"""
รายชื่อสมาชิก S&P 500 ย้อนหลัง (point-in-time) จาก github.com/fja05680/sp500

ไฟล์ `S&P 500 Historical Components & Changes (Updated).csv` มี 1 แถวต่อ "วันที่มีการเปลี่ยนแปลง"
คอลัมน์ tickers = รายชื่อสมาชิกทั้งหมด ณ วันนั้น (ใช้ได้ต่อไปจนถึงแถวถัดไป)
ticker เป็นชื่อ ณ วันนั้น (เช่น FB ก่อนเปลี่ยนเป็น META) — ticker เดียวกันอาจเป็นคนละบริษัทในคนละช่วงเวลา
"""

import pandas as pd
import requests

from lib.paths import CONSTITUENTS_DIR, FJA_COMMIT

FJA_BASE = f"https://raw.githubusercontent.com/fja05680/sp500/{FJA_COMMIT}"
HIST_FILE = "S&P 500 Historical Components & Changes (Updated).csv"
LOCAL = CONSTITUENTS_DIR / "hist_components.csv"


def download(force: bool = False) -> None:
    if LOCAL.exists() and not force:
        return
    url = f"{FJA_BASE}/" + requests.utils.quote(HIST_FILE)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    LOCAL.write_bytes(r.content)


def load_history() -> pd.DataFrame:
    """คืน DataFrame: date, tickers(list) — เรียงตามวันที่"""
    download()
    h = pd.read_csv(LOCAL, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    h["tickers"] = h["tickers"].str.split(",").apply(lambda l: sorted(set(t.strip() for t in l)))
    return h


def members_on(date, hist: pd.DataFrame = None) -> list:
    """รายชื่อสมาชิก ณ วันที่ date (ใช้แถวล่าสุดที่ date <= วันนั้น)"""
    hist = load_history() if hist is None else hist
    row = hist[hist["date"] <= pd.Timestamp(date)]
    if row.empty:
        raise ValueError(f"ไม่มีข้อมูลสมาชิกก่อน {date}")
    return row.iloc[-1]["tickers"]


def membership_spells(hist: pd.DataFrame = None) -> pd.DataFrame:
    """แปลงเป็นช่วงเวลาที่แต่ละ ticker อยู่ในดัชนี: ticker, start, end (end = วันก่อนแถวที่หายไป / NaT ถ้ายังอยู่)"""
    hist = load_history() if hist is None else hist
    dates = list(hist["date"])
    rows, open_ = [], {}
    prev = set()
    for i, (d, ts) in enumerate(zip(hist["date"], hist["tickers"])):
        cur = set(ts)
        for t in cur - prev:
            open_[t] = d
        for t in prev - cur:
            rows.append((t, open_.pop(t), d - pd.Timedelta(days=1)))
        prev = cur
    for t, s in open_.items():
        rows.append((t, s, pd.NaT))
    return pd.DataFrame(rows, columns=["ticker", "start", "end"]).sort_values(["ticker", "start"]).reset_index(drop=True)


def to_yahoo(ticker: str) -> str:
    """BRK.B -> BRK-B (รูปแบบของ Yahoo)"""
    return ticker.replace(".", "-")
