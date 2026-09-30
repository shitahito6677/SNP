"""
Process แยกสำหรับรันโค้ด condition ของผู้ใช้ (exec) — ทั้งเรื่อง security และ look-ahead guard

- process นี้ **ไม่มีข้อมูลอนาคตอยู่ในหน่วยความจำเลย**: parent ส่งราคา/สัญญาณให้ทีละวัน (ข้อมูล ≤ t เท่านั้น)
  ดังนั้นต่อให้โค้ดผู้ใช้พยายามค้น object ภายใน ก็ไม่มีข้อมูลอนาคตให้เห็น
- `ctx.history(..., end=อนาคต)` → LookAheadError ทันที
- parent คุม timeout ต่อการเรียก decide() และ kill process นี้ได้เสมอ (loop ไม่จบไม่ทำให้ server ล่ม)
- ⚠️ นี่ไม่ใช่ sandbox ด้าน security ที่สมบูรณ์ — โค้ดยังเข้าถึงไฟล์/เครือข่ายได้ จึงต้อง bind 127.0.0.1 เท่านั้น
"""

from __future__ import annotations

import contextlib
import io
import json
import linecache
import traceback

import pandas as pd


class LookAheadError(RuntimeError):
    pass


class _CView(dict):
    """ctx.c — key เป็น sector ETF (XLK…) แต่ใส่ชื่อ GICS sector ก็ได้"""

    def __init__(self, data, gics_to_etf):
        super().__init__(data)
        self._g2e = gics_to_etf

    def get(self, k, default=None):
        return super().get(self._g2e.get(k, k), default)

    def __getitem__(self, k):
        return super().__getitem__(self._g2e.get(k, k))

    def __contains__(self, k):
        return super().__contains__(self._g2e.get(k, k))


class Ctx:
    def __init__(self, env):
        self._env = env
        self.state = {}
        self._notes = {}
        self._tags = {}

    # -- ตั้งค่าต่อวัน --
    def _set_day(self, p):
        self.date = p["date"]
        self.universe = list(p["universe"])
        self.a = dict(p["a"])
        self.b = dict(p["b"])
        self.c = _CView(p["c"], self._env["gics_to_etf"])
        self.portfolio = p["portfolio"]
        self.stage_enabled = dict(p["stage_enabled"])
        self.manual = list(p.get("manual", []))
        self._notes = {}
        self._tags = {}

    # -- API สำหรับผู้ใช้ --
    def sector_of(self, ticker):
        return self._env["sector_of"].get(ticker, "Unknown")

    def etf_of(self, ticker):
        return self._env["gics_to_etf"].get(self.sector_of(ticker))

    def c_for(self, ticker):
        e = self.etf_of(ticker)
        return self.c.get(e) if e else None

    def price(self, ticker, field="adj"):
        s = self._env["hist"].series(ticker, field)
        s = s.dropna()
        return float(s.iloc[-1]) if len(s) else None

    def history(self, ticker, lookback_days=60, field="adj", end=None):
        """ราคาย้อนหลัง lookback_days วันทำการ สิ้นสุดที่ ctx.date (ห้ามขอเกิน ctx.date)"""
        if end is not None and pd.Timestamp(end) > pd.Timestamp(self.date):
            raise LookAheadError(f"history(end={end}) เกินวันตัดสินใจ {self.date} — ห้ามดูข้อมูลอนาคต")
        s = self._env["hist"].series(ticker, field)
        if end is not None:
            s = s.loc[:pd.Timestamp(end)]
        return s.iloc[-int(lookback_days):] if lookback_days else s

    NOTE_KINDS = ("news_sell", "pullback", "buyback", "receive")

    def note(self, ticker, text, kind=None, ref=None):
        """เหตุผลของวันนี้ต่อหุ้น — kind (ไม่บังคับ) บอกชนิดของ trade ให้กราฟแยกป้ายได้:
        "news_sell" ขายเพราะข่าวร้ายของตัวเอง · "pullback" ถูกดึงเงินคืน (ref = หุ้นที่ซื้อคืน) ·
        "buyback" ซื้อคืน (ref = หุ้นที่ถูกดึงเงิน) · "receive" รับเงินจากหุ้นอื่น (ref = หุ้นต้นทาง)"""
        t = str(ticker)
        self._notes.setdefault(t, []).append(str(text)[:300])
        if kind is not None:
            if kind not in self.NOTE_KINDS:
                raise ValueError(f"ctx.note kind={kind!r} ไม่รู้จัก — ใช้ได้: {', '.join(self.NOTE_KINDS)}")
            refs = [ref] if isinstance(ref, str) else list(ref or [])
            self._tags.setdefault(t, []).append({"kind": kind, "ref": [str(x) for x in refs][:50]})


class _History:
    """ราคาที่ได้รับมาแล้ว (≤ วันปัจจุบัน) — เก็บแบบต่อท้ายทีละวัน"""

    def __init__(self, fields):
        self.dates, self.rows = [], {f: [] for f in fields}
        self._cache = {}

    def append(self, date, row):
        self.dates.append(pd.Timestamp(date))
        for f, vals in row.items():
            self.rows[f].append(vals)
        self._cache = {}

    def series(self, ticker, field):
        k = (ticker, field)
        if k not in self._cache:
            col = self._env_cols.get(ticker)
            vals = [r[col] if col is not None else None for r in self.rows[field]]
            self._cache[k] = pd.Series(vals, index=pd.DatetimeIndex(self.dates), dtype="float64", name=ticker)
        return self._cache[k]


def main(conn):
    decide, ctx = None, None
    while True:
        try:
            msg, payload = conn.recv()
        except EOFError:
            return
        if msg == "stop":
            return
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                if msg == "init":
                    hist = _History(payload["fields"])
                    hist._env_cols = {t: i for i, t in enumerate(payload["columns"])}
                    env = {"sector_of": payload["sector_of"], "gics_to_etf": payload["gics_to_etf"], "hist": hist}
                    ns = {"__name__": "condition"}
                    src = payload["source"]
                    linecache.cache["<condition>"] = (len(src), None, src.splitlines(True), "<condition>")
                    exec(compile(payload["source"], "<condition>", "exec"), ns)  # noqa: S102 — ดู docstring
                    ns.update(payload.get("params") or {})  # ค่าจากหน้าเว็บ (PARAMS) แทนค่าที่เขียนไว้ในไฟล์ — ก่อน decide ครั้งแรก
                    decide = ns.get("decide")
                    if not callable(decide):
                        raise TypeError("ไม่พบ def decide(ctx)")
                    ctx = Ctx(env)
                    conn.send(("ok", {"stdout": buf.getvalue()[-4000:]}))
                elif msg == "day":
                    ctx._env["hist"].append(payload["date"], payload["prices"])
                    ctx._set_day(payload)
                    out = decide(ctx)
                    conn.send(("result", {"weights": out, "notes": ctx._notes, "tags": ctx._tags, "stdout": buf.getvalue()[-4000:],
                                          "state": _state_snapshot(ctx.state)}))
                elif msg == "prices":  # วันที่ไม่ต้องตัดสินใจ แต่ต้องต่อ history ให้ครบ
                    ctx._env["hist"].append(payload["date"], payload["prices"])
                    conn.send(("ok", {}))
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            conn.send(("error", {"type": type(e).__name__, "message": str(e), "traceback": _user_tb(tb),
                                 "stdout": buf.getvalue()[-4000:]}))


def _state_snapshot(state, limit: int = 200_000):
    """สำเนา ctx.state แบบ JSON (ค่าที่ serialize ไม่ได้ → str) สำหรับบันทึกการตัดสินใจรายวัน — ใหญ่เกิน limit = ไม่ส่ง"""
    try:
        txt = json.dumps(state, default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001 — เช่น key ไม่ใช่ str
        try:
            txt = json.dumps({str(k): v for k, v in dict(state).items()}, default=str, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return None
    return json.loads(txt) if len(txt) <= limit else None


def _user_tb(tb: str) -> str:
    """ตัด frame ภายในของ worker ออก เหลือเฉพาะส่วนที่อยู่ในโค้ด condition (อ่านง่าย)"""
    lines = tb.splitlines()
    idx = next((i for i, ln in enumerate(lines) if 'File "<condition>"' in ln), None)
    return tb if idx is None else "\n".join([lines[0]] + lines[idx:])
