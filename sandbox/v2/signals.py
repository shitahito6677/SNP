"""
As-of access ของ signal — ห้ามคืนข้อมูลที่ date > t เด็ดขาด

- rebalance (annual_june / monthly / daily): ใช้ "รอบล่าสุด" R* = max(R ≤ t) ทั้งก้อน (ticker ที่ไม่อยู่ในรอบ R* = ไม่มีสัญญาณ
  ไม่ย้อนไปหยิบรอบเก่า) และถ้า t > coverage.valid_through → ไม่มีข้อมูล
- event: ต่อ key ใช้แถวล่าสุดที่ date ≤ t และอายุ ≤ asof.max_age_days วัน (ไม่มีข่าวใหม่ = ไม่มีสัญญาณ)
"""

from __future__ import annotations

import bisect
import json

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg
from sandbox.v2 import registry

FIELDS = ("class", "score", "applicable", "reasons", "weight", "rank", "sector", "source")


def _clean(v):
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.ndarray):
        return [str(x) for x in v.tolist()]
    return v


class LookAheadError(RuntimeError):
    pass


class AsOf:
    def __init__(self, vid: str, manual: list | None = None):
        self.m = registry.get(vid)
        self.vid = vid
        self.key = self.m["key"]
        self.kind = "event" if self.m["rebalance"] == "event" else "rebalance"
        self.max_age = pd.Timedelta(days=(self.m.get("asof") or {}).get("max_age_days") or 3650)
        vt = self.m["coverage"].get("valid_through")
        self.valid_through = pd.Timestamp(vt) if vt else None
        df = registry.signals(vid)
        if manual:
            df = pd.concat([df, pd.DataFrame(manual)], ignore_index=True)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values(["date", self.key]).drop_duplicates(["date", self.key], keep="last")
        cols = [c for c in FIELDS if c in df.columns]
        self.records = [{k: _clean(v) for k, v in zip(cols, row)} for row in df[cols].itertuples(index=False, name=None)]
        dates = df["date"].to_numpy()
        for r, d in zip(self.records, dates):
            r["date"] = str(pd.Timestamp(d).date())
        keys = df[self.key].astype(str).to_numpy()
        if self.kind == "rebalance":
            self.R = sorted(pd.to_datetime(df["date"].unique()))
            self.by_R = {}
            for i, (d, k) in enumerate(zip(dates, keys)):
                self.by_R.setdefault(pd.Timestamp(d), {})[k] = i
        else:
            self.by_key = {}
            for i, (d, k) in enumerate(zip(dates, keys)):
                self.by_key.setdefault(k, ([], []))
                self.by_key[k][0].append(pd.Timestamp(d))
                self.by_key[k][1].append(i)

    def rebalance_date(self, t: pd.Timestamp):
        if self.kind != "rebalance":
            return None
        if self.valid_through is not None and t > self.valid_through:
            return None
        j = bisect.bisect_right(self.R, t) - 1
        return self.R[j] if j >= 0 else None

    def snapshot(self, t: pd.Timestamp) -> dict:
        """rebalance: {key: record} ของรอบ R* ≤ t (ว่างถ้าไม่มีข้อมูล)"""
        R = self.rebalance_date(t)
        if R is None:
            return {}
        out = {k: self.records[i] for k, i in self.by_R[R].items()}
        for r in out.values():
            if pd.Timestamp(r["date"]) > t:
                raise LookAheadError(f"{self.vid}: record {r['date']} > {t.date()}")
        return out

    def at(self, key: str, t: pd.Timestamp):
        if self.kind == "rebalance":
            R = self.rebalance_date(t)
            i = self.by_R.get(R, {}).get(key) if R is not None else None
            return None if i is None else self.records[i]
        v = self.by_key.get(key)
        if not v:
            return None
        j = bisect.bisect_right(v[0], t) - 1
        if j < 0 or t - v[0][j] > self.max_age:
            return None
        rec = self.records[v[1][j]]
        if pd.Timestamp(rec["date"]) > t:
            raise LookAheadError(f"{self.vid}: record {rec['date']} > {t.date()}")
        return rec

    def coverage_warnings(self, start: pd.Timestamp, end: pd.Timestamp) -> list:
        w = []
        cs, ce = pd.Timestamp(self.m["coverage"]["start"]), pd.Timestamp(self.m["coverage"]["end"])
        label = self.m["short_label"]
        if self.kind == "rebalance":
            if cs > start:
                w.append(f"{label}: รอบแรกของสัญญาณคือ {cs.date()} — ช่วง {start.date()} → {(cs - pd.Timedelta(days=1)).date()} ไม่มีข้อมูล {self.m['model']}")
            if self.valid_through is not None and end > self.valid_through:
                w.append(f"{label}: สัญญาณใช้ได้ถึง {self.valid_through.date()} — ช่วง {(self.valid_through + pd.Timedelta(days=1)).date()} → {end.date()} ไม่มีข้อมูล {self.m['model']} (held-out ของโมเดลยังล็อก)")
        else:
            if cs > start:
                w.append(f"{label}: เหตุการณ์แรก {cs.date()} (หลังวันเริ่มรัน {start.date()})")
            if ce < end:
                w.append(f"{label}: เหตุการณ์สุดท้าย {ce.date()} (ก่อนวันจบรัน {end.date()}) — หลังจากนั้นไม่มีสัญญาณ")
        return w


def load_manual_news(kind: str) -> list:
    """ข่าว manual (source="manual") ที่ผู้ใช้เพิ่มเอง → record แบบ signal (kind 'b' = รายหุ้น, 'c' = ราย sector)
    ไม่ใช่ output ของโมเดลและไม่ถูกใช้เป็น training data"""
    if not cfg.MANUAL_NEWS.exists():
        return []
    out = []
    for line in cfg.MANUAL_NEWS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        n = json.loads(line)
        if n.get("deleted"):
            continue
        targets = n.get("tickers", []) if kind == "b" else n.get("sectors", [])
        if kind == "b" and n.get("kind") != "company" and not n.get("tickers"):
            continue
        if kind == "c" and not n.get("sectors"):
            continue
        for k in targets:
            out.append({"date": n["effective_date"], ("ticker" if kind == "b" else "sector"): k,
                        "class": n.get("sentiment", "neutral"), "score": n.get("score", 0.0), "applicable": True,
                        "reasons": [f"MANUAL {n['effective_date']}: {n['headline'][:140]}"],
                        "model_version": "manual", "is_stub": False, "source": "manual"})
    return out
