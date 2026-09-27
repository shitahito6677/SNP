"""
Price loader ของ sandbox v2 — จุดเดียวที่อ่าน sandbox/v2/data/prices/*.parquet

Held-out guard: ขอข้อมูลถึงวันที่ ≥ HELD_OUT_START โดยไม่ได้ allow_held_out=True → HeldOutError
(และตัดแถวหลัง end ทิ้งเสมอ — ผู้เรียกไม่มีทางได้ราคาหลัง end ที่ขอ)
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg

FIELDS = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "adj": "Adj Close", "volume": "Volume"}


class HeldOutError(RuntimeError):
    pass


def check_range(start, end, allow_held_out: bool = False) -> None:
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError(f"start {start} > end {end}")
    if pd.Timestamp(end) >= pd.Timestamp(cfg.HELD_OUT_START) and not allow_held_out:
        raise HeldOutError(
            f"ขอข้อมูลถึง {pd.Timestamp(end).date()} ซึ่งอยู่ในช่วง held-out (≥ {cfg.HELD_OUT_START}) — "
            f"ต้องเปิด toggle held-out และพิมพ์ '{cfg.HELD_OUT_CONFIRM_TEXT}' ก่อน")


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads(cfg.UNIVERSE_MANIFEST.read_text())


def reload() -> None:
    manifest.cache_clear()
    _all.cache_clear()


def available_tickers(kind: str | None = "stock") -> list:
    return sorted(t for t, r in manifest()["tickers"].items()
                  if r.get("status") in ("ok", "partial") and (kind is None or r.get("kind") == kind))


def sector_of(ticker: str) -> str:
    r = manifest()["tickers"].get(ticker)
    return (r or {}).get("sector") or "Unknown"


def name_of(ticker: str) -> str | None:
    return (manifest()["tickers"].get(ticker) or {}).get("name")


@lru_cache(maxsize=1)
def _all() -> dict:
    """{field: wide DataFrame (date × ticker)} ของทุก ticker ที่มีไฟล์ — โหลดครั้งเดียวต่อ process"""
    frames = {}
    for t in available_tickers(kind=None):
        f = cfg.PRICES_DIR / f"{t}.parquet"
        if f.exists():
            frames[t] = pd.read_parquet(f)
    out = {}
    for k, col in FIELDS.items():
        out[k] = pd.DataFrame({t: d[col] for t, d in frames.items() if col in d}).sort_index()
    return out


def load(field: str, tickers=None, start=None, end=None, allow_held_out: bool = False) -> pd.DataFrame:
    start = start or cfg.PRICE_START
    end = end or cfg.DEFAULT_END
    check_range(start, end, allow_held_out)
    w = _all()[field]
    if tickers is not None:
        w = w.reindex(columns=list(tickers))
    return w.loc[pd.Timestamp(start):pd.Timestamp(end)]


def calendar(start=None, end=None, allow_held_out: bool = False) -> pd.DatetimeIndex:
    """วันทำการของตลาดสหรัฐ (ตามวันที่ SPY มีราคา)"""
    return load("close", [cfg.BENCHMARK], start, end, allow_held_out).dropna().index


def ohlcv(ticker: str, start=None, end=None, allow_held_out: bool = False) -> pd.DataFrame:
    start = start or cfg.PRICE_START
    end = end or cfg.DEFAULT_END
    check_range(start, end, allow_held_out)
    f = cfg.PRICES_DIR / f"{ticker}.parquet"
    if not f.exists():
        return pd.DataFrame(columns=list(FIELDS.values()))
    return pd.read_parquet(f).loc[pd.Timestamp(start):pd.Timestamp(end)]


def data_hash(tickers, start, end, allow_held_out: bool = False) -> str:
    """hash ของราคา (Close + Adj Close) ที่ใช้จริงใน run — ใช้ตรวจ reproducibility"""
    c = load("close", sorted(tickers), start, end, allow_held_out).round(6)
    a = load("adj", sorted(tickers), start, end, allow_held_out).round(6)
    h = hashlib.sha256()
    h.update(",".join(c.columns).encode())
    h.update(c.index.strftime("%Y-%m-%d").str.cat(sep="|").encode())
    for x in (c, a):
        h.update(np.nan_to_num(x.to_numpy(np.float64), nan=-1.0).tobytes())
    return h.hexdigest()
