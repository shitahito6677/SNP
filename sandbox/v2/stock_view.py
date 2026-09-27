"""
ข้อมูลหน้าหุ้นรายตัว: OHLCV + trade ของการทดลอง + layer (ช่วงที่ A เลือก, จุด B, เหตุการณ์ C ของ sector, ข่าว manual)
held-out: ไม่ส่งราคาหลัง DEFAULT_END เว้นแต่การทดลองนั้นแตะ held-out แล้ว
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg, experiments_store as xs, jobs, prices, registry


def _result_dir(kind, rid):
    if kind == "exp":
        return xs.path(rid)
    d = jobs.get(rid, with_logs=False)
    if d is None or d["status"] != "done":
        raise KeyError("ไม่พบผลการรัน")
    from pathlib import Path
    return Path(d["result_dir"])


def build(ticker: str, kind=None, rid=None, start=None, end=None, versions=None) -> dict:
    man = prices.manifest()["tickers"].get(ticker)
    if man is None or man.get("status") not in ("ok", "partial"):
        raise KeyError(f"ไม่มีราคาของ {ticker}")
    versions = dict(versions or {})
    allow = False
    trades = []
    if kind and rid:
        d = _result_dir(kind, rid)
        conf = json.loads((d / "config.json").read_text())
        allow = bool(conf["held_out"].get("touched"))
        start, end = start or conf["start"], end or conf["end"]
        for m in "ABC":
            if conf["stages"][m]["mode"] != "off":
                versions.setdefault(m, conf["stages"][m]["version"])
        tr = pd.read_parquet(d / "trades.parquet")
        tr = tr[tr["ticker"] == ticker]
        trades = xs._records(tr)
    start = pd.Timestamp(start or cfg.PRICE_START)
    end = pd.Timestamp(end or cfg.DEFAULT_END)
    if not allow and end >= pd.Timestamp(cfg.HELD_OUT_START):
        end = pd.Timestamp(cfg.DEFAULT_END)
    px = prices.ohlcv(ticker, start, end, allow)
    bars = [{"time": str(i.date()), "open": _f(r["Open"]), "high": _f(r["High"]), "low": _f(r["Low"]),
             "close": _f(r["Close"]), "adj": _f(r["Adj Close"]), "volume": _f(r["Volume"])}
            for i, r in px.iterrows() if not np.isnan(r["Close"])]
    sector = man.get("sector") or "Unknown"
    etf = cfg.SECTOR_ETFS.get(sector)
    layers = {"A": [], "B": [], "C": [], "manual": []}
    labels = {}
    for m, vid in versions.items():
        try:
            meta = registry.get(vid)
        except KeyError:
            continue
        labels[m] = {"id": vid, "short_label": meta["short_label"], "badge": meta["result_badge"]}
        s = registry.signals(vid)
        if m == "A":
            Rs = sorted(s["date"].unique())
            vt = pd.Timestamp(meta["coverage"].get("valid_through") or s["date"].max())
            mine = s[s["ticker"] == ticker].set_index("date")
            for k, R in enumerate(Rs):
                R = pd.Timestamp(R)
                nxt = pd.Timestamp(Rs[k + 1]) if k + 1 < len(Rs) else vt
                if nxt < start or R > end or R not in mine.index:
                    continue
                r = mine.loc[R]
                layers["A"].append({"from": str(max(R, start).date()), "to": str(min(nxt, end).date()),
                                    "rebalance": str(R.date()), "class": r["class"], "score": _f(r["score"]),
                                    "reasons": list(r["reasons"])})
        else:
            key = ticker if m == "B" else etf
            if key is None:
                continue
            ev = s[(s[registry.KEY_OF[m]] == key) & (s["date"] >= start) & (s["date"] <= end)]
            layers[m] = [{"time": str(pd.Timestamp(r["date"]).date()), "class": r["class"], "score": _f(r["score"]),
                          "reasons": list(r["reasons"])} for _, r in ev.iterrows()]
    if cfg.MANUAL_NEWS.exists():
        for line in cfg.MANUAL_NEWS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            n = json.loads(line)
            if n.get("deleted"):
                continue
            if ticker in n.get("tickers", []) or (etf and etf in n.get("sectors", [])):
                dt = pd.Timestamp(n["effective_date"])
                if start <= dt <= end:
                    layers["manual"].append({"time": n["effective_date"], "headline": n["headline"],
                                             "sentiment": n.get("sentiment"), "id": n["id"]})
    return {"ticker": ticker, "name": man.get("name") or ticker, "sector": sector, "etf": etf,
            "start": str(start.date()), "end": str(end.date()), "held_out_visible": allow,
            "bars": bars, "trades": trades, "layers": layers, "labels": labels,
            "price_note": "แท่งเทียน = ราคาดิบ (ปรับ split แล้ว ไม่ปรับปันผล); simulator ใช้ Adj Close (รวมปันผล)"}


def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else x
