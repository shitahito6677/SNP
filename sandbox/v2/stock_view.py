"""
ข้อมูลหน้าหุ้นรายตัว: OHLCV + trade ของการทดลอง + layer (ช่วงที่ A เลือก, จุด B, เหตุการณ์ C ของ sector, ข่าว manual)
held-out: ไม่ส่งราคาหลัง DEFAULT_END เว้นแต่การทดลองนั้นแตะ held-out แล้ว
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg, experiments_store as xs, jobs, prices, registry

log = logging.getLogger("sandbox.v2.server")


class StockError(Exception):
    """ข้อความภาษาไทยที่ตั้งใจให้ผู้ใช้เห็น (server คืนเป็น JSON พร้อม status ที่ระบุ)"""

    def __init__(self, message, status=404, kind="stock"):
        super().__init__(message)
        self.status, self.kind = status, kind


def _result_dir(kind, rid):
    if kind == "exp":
        try:
            return xs.path(rid)
        except KeyError as e:
            raise StockError(f"ไม่พบการทดลอง {rid} (อาจถูกลบไปแล้ว) — {str(e).strip(chr(39))}", 404, "context") from None
    if kind != "run":
        raise StockError(f"kind ต้องเป็น run หรือ exp (ได้ {kind!r})", 400, "context")
    d = jobs.get(rid, with_logs=False)
    if d is None or d["status"] != "done":
        raise StockError(f"ไม่พบผลการรัน {rid} (ยังรันไม่เสร็จ หรือถูกล้างไปแล้ว) — เปิดหน้าหุ้นโดยไม่อ้างการทดลองได้", 404, "context")
    return Path(d["result_dir"])


def _date(x, what):
    if not x:
        return None
    try:
        return pd.Timestamp(x).normalize()
    except (ValueError, TypeError, OverflowError):
        raise StockError(f"วัน{what}ไม่ถูกต้อง: {x!r} (ใช้รูปแบบ YYYY-MM-DD)", 400, "date") from None


def _reasons(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return []
    return [str(r) for r in (x if isinstance(x, (list, tuple, np.ndarray)) else [x])]


def build(ticker: str, kind=None, rid=None, start=None, end=None, versions=None) -> dict:
    tickers = prices.manifest()["tickers"]
    man = tickers.get(ticker)
    if man is None:
        raise StockError(f"ไม่พบ {ticker} ใน universe ของ sandbox (S&P 500 ปัจจุบัน ∪ หุ้นใน export ของ Model A) — ตรวจตัวสะกด ticker", 404, "unknown")
    if man.get("status") not in ("ok", "partial"):
        why = man.get("reason") or "ดึงราคาจาก Yahoo ไม่ได้"
        raise StockError(f"ไม่มีข้อมูลราคาของ {ticker} ({man.get('name') or ticker}) — status: {man.get('status') or 'ไม่ทราบ'} · {why}", 404, "no_price")
    notices = []
    if man.get("status") == "partial":
        notices.append(f"ราคาไม่ครบช่วง: {man.get('reason') or ('มีราคา ' + str(man.get('start')) + ' → ' + str(man.get('end')))}")
    versions = dict(versions or {})
    allow = False
    trades = []
    start, end = _date(start, "เริ่ม"), _date(end, "จบ")
    if kind and rid:
        d = _result_dir(kind, rid)
        conf = json.loads((d / "config.json").read_text())
        allow = bool(conf["held_out"].get("touched"))
        start, end = start or pd.Timestamp(conf["start"]), end or pd.Timestamp(conf["end"])
        for m in "ABC":
            if conf["stages"][m]["mode"] != "off":
                versions.setdefault(m, conf["stages"][m]["version"])
        if (d / "trades.parquet").exists():
            tr = pd.read_parquet(d / "trades.parquet")
            trades = xs._records(tr[tr["ticker"] == ticker])
            if not trades:
                notices.append(f"{ticker} ไม่มีการซื้อขายในการทดลองนี้ — แสดงราคาและสัญญาณอย่างเดียว")
        else:
            notices.append("ไม่มีไฟล์ trade ของการทดลองนี้ในเครื่อง (parquet ไม่อยู่ใน git) — กด Re-run เพื่อสร้างใหม่")
    start = start or pd.Timestamp(cfg.PRICE_START)  # หน้าหุ้นแสดงราคาตั้งแต่ช่วง warm-up (ดูราคาได้ ไม่ใช่ช่วงซื้อขาย)
    end = end or pd.Timestamp(cfg.DEFAULT_END)
    if start > end:
        raise StockError(f"วันเริ่ม {start.date()} อยู่หลังวันจบ {end.date()}", 400, "date")
    if not allow and end >= pd.Timestamp(cfg.HELD_OUT_START):
        end = pd.Timestamp(cfg.DEFAULT_END)
        notices.append(f"ราคาตั้งแต่ {cfg.HELD_OUT_START} เป็นช่วง held-out — ล็อกไว้ (เปิดได้จากการทดลองที่ยืนยัน held-out แล้วเท่านั้น)")
    if start > end:  # ช่วงที่ขออยู่ใน held-out ทั้งหมด → ไม่มีราคาให้ดู (ไม่ใช่ error)
        bars = []
    else:
        px = prices.ohlcv(ticker, start, end, allow)
        bars = [{"time": str(i.date()), "open": _f(r["Open"]), "high": _f(r["High"]), "low": _f(r["Low"]),
                 "close": _f(r["Close"]), "adj": _f(r["Adj Close"]), "volume": _f(r["Volume"])}
                for i, r in px.iterrows() if not np.isnan(r["Close"])]
    if not bars:
        notices.append(f"ไม่มีราคาของ {ticker} ในช่วง {start.date()} → {end.date()}")
    sector = man.get("sector") or "Unknown"
    etf = cfg.SECTOR_ETFS.get(sector)
    layers = {"A": [], "B": [], "C": [], "manual": []}
    labels = {}
    for m, vid in versions.items():
        if m not in "ABC" or not vid:
            continue
        try:
            meta = registry.get(vid)
        except KeyError:
            notices.append(f"ไม่พบ version {vid} ใน registry — ไม่แสดง layer {m}")
            continue
        labels[m] = {"id": vid, "short_label": meta["short_label"], "badge": meta["result_badge"]}
        try:
            layers[m] = _layer(m, vid, meta, ticker, etf, start, end)
        except Exception as e:  # noqa: BLE001 — layer เดียวพังไม่ให้ทั้งหน้าพัง
            log.exception("stock %s: layer %s (%s) failed", ticker, m, vid)
            notices.append(f"โหลด layer {m} ({meta['short_label']}) ไม่สำเร็จ: {type(e).__name__} — ดู server log")
    manual_unknown = 0  # ข่าว label_method = unknown ของหุ้น/sector นี้ (โชว์บนกราฟ แต่ไม่อยู่ใน B manual-labels)
    try:
        layers["manual"] = _manual(ticker, etf, start, end)
        from sandbox.v2.news import unknown_count
        manual_unknown = unknown_count([ticker], [etf] if etf else [])
    except Exception as e:  # noqa: BLE001
        log.exception("stock %s: manual news layer failed", ticker)
        notices.append(f"โหลดข่าว manual ไม่สำเร็จ: {type(e).__name__} — ดู server log")
    return {"ticker": ticker, "name": man.get("name") or ticker, "sector": sector, "etf": etf,
            "status": man.get("status"), "start": str(start.date()), "end": str(end.date()), "held_out_visible": allow,
            "bars": bars, "trades": trades, "layers": layers, "labels": labels, "notices": notices,
            "manual_unknown": manual_unknown,
            "price_note": "แท่งเทียน = ราคาดิบ (ปรับ split แล้ว ไม่ปรับปันผล); simulator ใช้ Adj Close (รวมปันผล)"}


def _layer(m, vid, meta, ticker, etf, start, end) -> list:
    s = registry.signals(vid)
    out = []
    if m == "A":
        Rs = sorted(s["date"].unique())
        vt = pd.Timestamp(meta["coverage"].get("valid_through") or s["date"].max())
        mine = s[s["ticker"] == ticker].drop_duplicates("date", keep="last").set_index("date")
        for k, R in enumerate(Rs):
            R = pd.Timestamp(R)
            nxt = pd.Timestamp(Rs[k + 1]) if k + 1 < len(Rs) else vt
            if nxt < start or R > end or R not in mine.index:
                continue
            r = mine.loc[R]
            out.append({"from": str(max(R, start).date()), "to": str(min(nxt, end).date()),
                        "rebalance": str(R.date()), "class": r["class"], "score": _f(r["score"]),
                        "reasons": _reasons(r["reasons"])})
        return out
    key = ticker if m == "B" else etf
    if key is None:
        return out
    ev = s[(s[registry.KEY_OF[m]] == key) & (s["date"] >= start) & (s["date"] <= end)]
    return [{"time": str(pd.Timestamp(r["date"]).date()), "class": r["class"], "score": _f(r["score"]),
             "reasons": _reasons(r["reasons"])} for _, r in ev.iterrows()]


def _manual(ticker, etf, start, end) -> list:
    from sandbox.v2.news import LABELS, label_method_of, label_of

    out = []
    if not cfg.MANUAL_NEWS.exists():
        return out
    for line in cfg.MANUAL_NEWS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            n = json.loads(line)
            dt = pd.Timestamp(n["effective_date"])
        except (ValueError, KeyError, TypeError):
            log.warning("manual_news.jsonl: ข้ามบรรทัดที่อ่านไม่ได้: %s", line[:200])
            continue
        if n.get("deleted"):
            continue
        if (ticker in (n.get("tickers") or []) or (etf and etf in (n.get("sectors") or []))) and start <= dt <= end:
            lab = label_of(n)
            out.append({"time": n["effective_date"], "headline": n.get("headline", ""), "label": lab,
                        "label_text": LABELS[lab], "label_method": label_method_of(n), "id": n.get("id")})
    return out


def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else x
