"""
Pipeline engine + simulator ของ sandbox v2

ลำดับต่อวันทำการ t (ตาม config.EXECUTION = "next_close"):
    1. execute คำสั่งที่ตัดสินใจเมื่อวาน ที่ราคา close ของวัน t (Adj Close = total return)
    2. หุ้นที่ถืออยู่แต่ไม่มีราคาหลังวันสุดท้ายของมัน (delist/หยุดเทรด) → แปลงเป็นเงินสดที่ราคาล่าสุด
    3. mark-to-market ที่ close วัน t
    4. pipeline A → B → C (as-of ≤ t) → ส่ง ctx ให้ condition (process แยก) → เป้าน้ำหนักใหม่
    5. เป้าเปลี่ยน → คำสั่งรอ execute ที่ close วัน t+1 · เป้าเดิม/None → ไม่ซื้อขาย (ปล่อย drift)

เว็บไม่คำนวณโมเดลเอง — อ่าน signal ที่ precomputed ผ่าน registry เท่านั้น
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from sandbox.v2 import condition_registry, config as cfg, metrics, prices, registry
from sandbox.v2.signals import AsOf, load_manual_news

STAGES = ["load", "A", "B", "C", "condition", "simulate", "metrics", "save"]
MODES = ("off", "on")  # กล่องโมเดล = แหล่งสัญญาณ: เปิด/ปิด + เลือก version เท่านั้น (เกณฑ์กรองทั้งหมดอยู่ใน condition)
LEGACY_MODES = ("filter", "score-only")  # config ก่อน G1 — ดู legacy_notes()
SCOPE_MODES = ("all", "sectors", "tickers")
ALLOWED_ETFS = [cfg.BENCHMARK] + list(cfg.SECTOR_ETFS.values())


class ConfigError(ValueError):
    pass


class ConditionError(RuntimeError):
    def __init__(self, message, tb=""):
        super().__init__(message)
        self.tb = tb


class Cancelled(RuntimeError):
    pass


# ---------------------------------------------------------------- config

# เกณฑ์ของ config เดิม (ก่อน G1) — ใช้แค่ตรวจว่า config เก่าเทียบเท่าระบบใหม่หรือไม่
LEGACY_DEFAULT_CRITERIA = {
    "A": {"class_in": ["selected"], "min_score": None},
    "B": {"exclude_classes": ["negative"], "min_score": None, "missing": "pass"},
    "C": {"exclude_classes": ["negative"], "min_score": None, "missing": "pass"},
}


class LegacyConfigError(ConfigError):
    """config ใช้เกณฑ์กรองในกล่องแบบเดิม (ก่อน G1) ที่ระบบใหม่ทำแบบเดิมไม่ได้ — รันได้เมื่อผู้ใช้ยืนยันเท่านั้น"""

    def __init__(self, notes):
        super().__init__("config นี้ใช้เกณฑ์กรองในกล่องแบบเดิม ซึ่งย้ายไปอยู่ใน condition แล้ว: " + " · ".join(notes))
        self.notes = notes


def legacy_notes(stages_in: dict) -> tuple:
    """แปลงกล่องแบบเดิม → (mode ใหม่ต่อกล่อง, รายการสิ่งที่ระบบใหม่ทำต่างไป)
    เทียบเท่าพอดี: A filter + เกณฑ์ default (selected), B/C score-only, off  → ไม่มี note (รันซ้ำได้ผลเดิม)
    ทำแบบเดิมไม่ได้: A score-only / A เกณฑ์อื่น, B/C filter → มี note"""
    modes, notes = {}, []
    for m in "ABC":
        s = dict((stages_in or {}).get(m) or {})
        mode = s.get("mode", "off")
        crit = dict(LEGACY_DEFAULT_CRITERIA[m])
        crit.update(s.get("criteria") or {})
        if mode in MODES:
            modes[m] = mode
        elif mode == "filter" and m == "A":
            modes[m] = "on"
            if list(crit.get("class_in") or []) != ["selected"]:
                notes.append(f"A: เดิมรับ class {crit.get('class_in')} — ตอนนี้ A เปิด = เฉพาะ selected + applicable")
            if crit.get("min_score") is not None:
                notes.append(f"A: เดิมกรอง score ≥ {crit['min_score']} ในกล่อง — ตอนนี้ต้องใช้ condition (template a_score_threshold)")
        elif mode == "score-only" and m == "A":
            modes[m] = "off"
            notes.append("A: เดิม 'แนบคะแนน' (ไม่กรอง) — ระบบใหม่ไม่มีโหมดนี้ จะรันเป็น A ปิด (universe เท่าเดิม แต่ ctx.a ว่าง)")
        elif mode == "filter":
            modes[m] = "on"
            ex = crit.get("exclude_classes") or []
            what = [f"ตัด {'/'.join(ex)}"] if ex else []
            if crit.get("min_score") is not None:
                what.append(f"score ≥ {crit['min_score']}")
            what.append("ไม่มีสัญญาณ → " + ("ผ่าน" if crit.get("missing", "pass") == "pass" else "ตัด"))
            notes.append(f"{m}: เดิมกรองในกล่อง ({', '.join(what)}) — ตอนนี้ {m} แค่แนบคะแนน ไม่ตัดหุ้น "
                         f"(ทำแบบเดิมได้ด้วย condition เช่น template exclude_negative_B)")
        elif mode == "score-only":
            modes[m] = "on"
        else:
            raise ConfigError(f"กล่อง {m}: mode ต้องเป็น {MODES} (ได้ {mode!r})")
    return modes, notes


def normalize_scope(raw) -> dict:
    """ขอบเขตการลงทุน: all = ทั้ง universe (S&P 500) · sectors = GICS sector ETF ที่เลือก · tickers = หุ้นที่ระบุเอง"""
    raw = raw or {}
    mode = raw.get("mode") or "all"
    if mode not in SCOPE_MODES:
        raise ConfigError(f"ขอบเขต: mode ต้องเป็น {SCOPE_MODES} (ได้ {mode!r})")
    if mode == "sectors":
        valid = list(cfg.SECTOR_ETFS.values())
        secs = sorted({str(x).strip().upper() for x in raw.get("sectors") or [] if str(x).strip()})
        bad = [x for x in secs if x not in valid]
        if bad:
            raise ConfigError(f"ขอบเขต: ไม่รู้จัก sector {bad} (ใช้ได้: {' '.join(valid)})")
        if not secs:
            raise ConfigError("ขอบเขต: ยังไม่ได้เลือก sector")
        return {"mode": mode, "sectors": secs, "tickers": []}
    if mode == "tickers":
        tks = sorted({str(x).strip().lstrip("@$").upper().replace(".", "-") for x in raw.get("tickers") or [] if str(x).strip()})
        stocks = set(prices.available_tickers("stock"))
        bad = [x for x in tks if x not in stocks]
        if bad:
            raise ConfigError(f"ขอบเขต: ไม่พบหุ้น {bad} ในระบบ (หรือไม่มีราคา)")
        if not tks:
            raise ConfigError("ขอบเขต: ยังไม่ได้เลือกหุ้น")
        return {"mode": mode, "sectors": [], "tickers": tks}
    return {"mode": "all", "sectors": [], "tickers": []}


def scope_members(scope: dict | None):
    """None = ทั้ง universe; list = หุ้นใน scope (ตาม manifest — ยังไม่ดูว่ามีราคาช่วงไหน)"""
    scope = scope or {"mode": "all"}
    if scope["mode"] == "all":
        return None
    stocks = prices.available_tickers("stock")
    if scope["mode"] == "sectors":
        want = set(scope["sectors"])
        return [t for t in stocks if cfg.SECTOR_ETFS.get(prices.sector_of(t)) in want]
    ok = set(stocks)
    return [t for t in scope["tickers"] if t in ok]


def scope_label(scope: dict | None) -> str:
    scope = scope or {"mode": "all"}
    if scope["mode"] == "sectors":
        return "sector " + " ".join(scope["sectors"])
    if scope["mode"] == "tickers":
        tk = scope["tickers"]
        return "หุ้น " + " ".join(tk[:6]) + (f" +{len(tk) - 6}" if len(tk) > 6 else "")
    return "ทั้งตลาด (S&P 500)"


def normalize_config(c: dict, allow_legacy: bool = False) -> tuple:
    """ตรวจ + เติมค่า default → (config, warnings) ; ผิด = ConfigError"""
    c = json.loads(json.dumps(c))  # deep copy
    warnings = []
    start = pd.Timestamp(c.get("start") or cfg.PRICE_START)
    end = pd.Timestamp(c.get("end") or cfg.DEFAULT_END)
    if start < pd.Timestamp(cfg.PRICE_START):
        raise ConfigError(f"วันเริ่ม {start.date()} ก่อนข้อมูลราคา ({cfg.PRICE_START}) — เปลี่ยน PRICE_START ใน config.py แล้วรัน update_prices")
    if end <= start:
        raise ConfigError("วันจบต้องหลังวันเริ่ม")
    ho = c.get("held_out") or {}
    touched = end >= pd.Timestamp(cfg.HELD_OUT_START)
    if touched and not (ho.get("enabled") and (ho.get("confirm") or "").strip() == cfg.HELD_OUT_CONFIRM_TEXT):
        raise prices.HeldOutError(
            f"ช่วงวันที่ถึง {end.date()} เข้า held-out (≥ {cfg.HELD_OUT_START}) — ต้องเปิด toggle และพิมพ์ "
            f"'{cfg.HELD_OUT_CONFIRM_TEXT}' ก่อน (ผลจะติดธง held_out_touched ถาวร)")
    scope = normalize_scope(c.get("scope"))
    members = scope_members(scope)
    if members is not None:
        if not members:
            raise ConfigError(f"ขอบเขต: {scope_label(scope)} ไม่มีหุ้นใน universe เลย — เลือก sector/หุ้นใหม่")
        has = prices.load("adj", members, start, end, touched).notna().any()
        if not has.any():
            raise ConfigError(f"ขอบเขต: หุ้นใน {scope_label(scope)} ไม่มีราคาในช่วง {start.date()} → {end.date()} เลย")
        nopx = sorted(has.index[~has])
        scope["members"] = members
        warnings.append(f"SCOPE: ทดลองเฉพาะ {scope_label(scope)} ({len(members)} ตัว) — สัญญาณ A ยังจัดอันดับจากทั้ง universe "
                        "แล้วค่อยกรองเหลือเฉพาะ scope (ไม่จัดอันดับใหม่) · EW benchmark = EW ของหุ้นใน scope · SPY = ตลาดรวมเหมือนเดิม")
        if nopx:
            warnings.append(f"SCOPE: {len(nopx)} ตัวใน scope ไม่มีราคาในช่วงนี้: {' '.join(nopx[:10])}" + (" …" if len(nopx) > 10 else ""))
    stages = {}
    modes, legacy = legacy_notes(c.get("stages"))
    if legacy and not allow_legacy:
        raise LegacyConfigError(legacy)
    for m in "ABC":
        s = dict((c.get("stages") or {}).get(m) or {})
        mode = modes[m]
        vid = s.get("version")
        if mode != "off":
            if not vid:
                raise ConfigError(f"กล่อง {m}: ยังไม่ได้เลือก version")
            try:
                registry.get(vid)
            except KeyError as e:
                raise ConfigError(str(e)) from None
            if not vid.startswith(m + ":"):
                raise ConfigError(f"กล่อง {m}: version {vid} ไม่ใช่ของ Model {m}")
        stages[m] = {"mode": mode, "version": vid if mode != "off" else None}
    if legacy:
        warnings.append("LEGACY: รันด้วยความหมายของระบบใหม่ ผลจะต่างจากผลเดิม — " + " · ".join(legacy))
    if stages["A"]["mode"] != "on":
        warnings.append("SURVIVORSHIP: กล่อง A ปิด → universe = หุ้น S&P 500 ปัจจุบัน ∪ หุ้นที่เคยอยู่ใน export ของ A "
                        "(หุ้นที่ล้ม/ถูกถอดก่อนปัจจุบันส่วนใหญ่ไม่อยู่ในนี้) — ผลจะดีเกินจริง")
    cond = dict(c.get("condition") or {})
    if cond.get("source") is None:
        if not cond.get("id"):
            raise ConfigError("ยังไม่ได้เลือก condition")
        cond["source"] = condition_registry.source(cond["id"])
    chk = condition_registry.static_check(cond["source"])
    if not chk["ok"]:
        raise ConfigError("condition ไม่ผ่านการตรวจ: " + "; ".join(chk["errors"]))
    cond["name"] = chk["name"]
    out = {
        "name": (c.get("name") or "").strip()[:120],
        "start": str(start.date()), "end": str(end.date()),
        "capital": float(c.get("capital") or cfg.INITIAL_CAPITAL),
        "cost": float(c.get("cost") if c.get("cost") is not None else cfg.TRANSACTION_COST),
        "execution": cfg.EXECUTION,
        "held_out": {"enabled": bool(ho.get("enabled")), "touched": bool(touched)},
        "scope": scope,
        "stages": stages,
        **({"legacy_migration": legacy} if legacy else {}),
        "include_manual": bool(c.get("include_manual")),
        "condition": {"id": cond.get("id"), "name": cond["name"], "source": cond["source"]},
    }
    if out["cost"] < 0 or out["cost"] > 0.05:
        raise ConfigError("cost ต่อขาต้องอยู่ระหว่าง 0 ถึง 5%")
    if out["capital"] <= 0:
        raise ConfigError("capital ต้องมากกว่า 0")
    return out, warnings


def coverage_warnings(conf: dict) -> list:
    start, end = pd.Timestamp(conf["start"]), pd.Timestamp(conf["end"])
    out = []
    if conf.get("include_manual"):
        from collections import Counter
        c = Counter(r.get("label_method") or "unknown" for m in "bc" for r in load_manual_news(m))
        if c.get("hindsight"):
            out.append(f"ORACLE: ข่าว manual ที่รวมเข้ามา (toggle) มี label แบบ hindsight (รู้ผลราคาแล้ว) {c['hindsight']} รายการ "
                       "→ ผลนี้จะติดธง Oracle test — ไม่ใช่ผลตอบแทนที่ทำได้จริง")
        if c.get("unknown"):
            out.append(f"MANUAL: ข่าว manual ที่รวมเข้ามา {c['unknown']} รายการยังไม่ระบุวิธี label (unknown) — ไม่ควรใช้แปลผลจนกว่าจะระบุ")
    for m in "ABC":
        s = conf["stages"][m]
        if s["mode"] == "off":
            continue
        a = AsOf(s["version"])
        out += a.coverage_warnings(start, end)
        man = registry.get(s["version"])
        for w in man.get("warnings") or []:
            out.append(f"{man['short_label']}: {w}")
        if m == "A" and (conf.get("scope") or {}).get("mode", "all") != "all":
            out += _scope_vs_A(conf, a, start, end)
    return out


def _scope_vs_A(conf, a, start, end) -> list:
    """เตือนก่อนรัน: หุ้นใน scope ไม่ผ่านเกณฑ์ A เลยทุกรอบของช่วงนี้ → พอร์ตจะว่างตลอด"""
    members = conf["scope"].get("members") or scope_members(conf["scope"])
    Rs = [R for R in getattr(a, "R", []) if start <= R <= end]
    R0 = a.rebalance_date(start)
    Rs = sorted(set(Rs + ([R0] if R0 is not None else [])))
    if not Rs:
        return []
    ever = sorted({k for R in Rs for k in members if _crit_A(a.at(k, R))})
    if not ever:
        return [f"SCOPE: หุ้นใน scope ไม่ผ่านเกณฑ์ A ในทุกรอบของช่วงนี้ ({len(Rs)} รอบ) → กล่อง A กรองออกหมด พอร์ตจะว่างตลอดการทดลอง"]
    if len(ever) < len(members):
        return [f"SCOPE: ผ่านเกณฑ์ A อย่างน้อย 1 รอบ {len(ever)}/{len(members)} ตัว"]
    return []


# ---------------------------------------------------------------- condition process

class ConditionRunner:
    """คุม process ของ condition — timeout ต่อ decide(), kill ได้ทุกเมื่อ"""

    def __init__(self, source, columns, sector_of, timeout=cfg.DECIDE_TIMEOUT_SEC):
        os.environ["PYTHONHASHSEED"] = "0"  # ลำดับของ set/dict ในโค้ดผู้ใช้ต้องเหมือนเดิมทุกครั้งที่รัน
        ctx = mp.get_context("spawn")
        self.parent, child = ctx.Pipe()
        from sandbox.v2 import condition_worker
        self.proc = ctx.Process(target=condition_worker.main, args=(child,), daemon=True)
        self.proc.start()
        child.close()  # ให้ parent เห็น EOF ทันทีถ้า process ของ condition ตาย
        self.timeout = timeout
        self.stdout = []
        self._call("init", {"source": source, "columns": columns, "fields": ["adj", "close", "volume"],
                            "sector_of": sector_of, "gics_to_etf": cfg.SECTOR_ETFS}, timeout=max(timeout, 30))

    def _call(self, msg, payload, timeout=None):
        limit = timeout or self.timeout
        try:
            self.parent.send((msg, payload))
        except (BrokenPipeError, OSError):
            raise ConditionError(f"process ของ condition ตายแล้ว (exit code {self.proc.exitcode})") from None
        t0 = time.time()
        while not self.parent.poll(0.2):
            if not self.proc.is_alive():
                raise ConditionError(f"process ของ condition ตายระหว่างทำงาน (exit code {self.proc.exitcode})")
            if time.time() - t0 > limit:
                self.close(kill=True)
                raise ConditionError(f"condition ไม่ตอบภายใน {limit} วินาที ({msg}) — "
                                     "อาจวนลูปไม่จบหรือคำนวณหนักเกินไป (process ถูก kill แล้ว)")
        try:
            kind, data = self.parent.recv()
        except EOFError:
            raise ConditionError(f"process ของ condition ตายระหว่างทำงาน (exit code {self.proc.exitcode})") from None
        if data.get("stdout"):
            self.stdout.append(data["stdout"])
        if kind == "error":
            raise ConditionError(f"{data['type']}: {data['message']}", data.get("traceback", ""))
        return data

    def day(self, payload):
        return self._call("day", payload)

    def prices_only(self, payload):
        return self._call("prices", payload)

    def close(self, kill=False):
        try:
            if kill:
                self.proc.kill()
            else:
                self.parent.send(("stop", None))
                self.proc.join(2)
                if self.proc.is_alive():
                    self.proc.kill()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- helpers

def _git():
    def run(*a):
        try:
            return subprocess.run(["git", *a], cwd=cfg.REPO, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001
            return None
    return {"commit": run("rev-parse", "HEAD"), "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(run("status", "--porcelain", "--untracked-files=no"))}


def _crit_A(rec):
    """A เปิด = ใช้ผลเลือกหุ้นของ version นั้นตรง ๆ (class == selected และ applicable) — ไม่มีเกณฑ์เพิ่มจากเว็บ"""
    return rec is not None and bool(rec.get("applicable")) and rec.get("class") == "selected"


def not_applicable(model: str, date) -> dict:
    """ไม่มีสัญญาณของ key นี้ ณ วันนี้ → record ชัดเจนว่า "ไม่มีข้อมูล" (ห้ามเดาค่าให้)"""
    return {"class": None, "score": None, "applicable": False, "reasons": ["ไม่มีข้อมูล"], "date": None, "model": model}


def _chip(model, label, rec, extra=""):
    if rec is None or rec.get("applicable") is False:
        return f"{model}: {label} ไม่มีสัญญาณ"
    sc = rec.get("score")
    s = f" (score {sc:.1f})" if isinstance(sc, float) and model == "A" else (f" ({sc:+.2f})" if isinstance(sc, float) else "")
    src = " [MANUAL]" if rec.get("source") == "manual" else ""
    if rec.get("label") is not None:  # ข่าว manual: แสดงความแรง -2..+2 ไม่ใช่แค่ 3 คลาส
        from sandbox.v2.news import label_tag
        return f"{model}: {label} {extra}label {label_tag(int(rec['label']))} · {rec.get('date')}{src}"
    return f"{model}: {label} {extra}{rec.get('class')}{s} · {rec.get('date')}{src}"


# ---------------------------------------------------------------- main run

def run(conf: dict, out_dir: Path, progress=lambda *a, **k: None, cancelled=lambda: False, log=print) -> dict:
    t_start = time.time()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    allow = conf["held_out"]["touched"]
    start, end = pd.Timestamp(conf["start"]), pd.Timestamp(conf["end"])
    cost = conf["cost"]

    # ---- load
    progress("load", 1, None, "โหลดราคา")
    cal = prices.calendar(start, end, allow)
    if len(cal) < 3:
        raise ConfigError("ช่วงวันที่สั้นเกินไป (ต้องมีวันทำการ ≥ 3 วัน)")
    adj_all = prices.load("adj", None, start, end, allow).reindex(cal)
    close_all = prices.load("close", None, start, end, allow).reindex(cal)
    vol_all = prices.load("volume", None, start, end, allow).reindex(cal)
    stocks = [t for t in prices.available_tickers("stock") if t in adj_all.columns and adj_all[t].notna().any()]
    columns = stocks + [t for t in ALLOWED_ETFS if t in adj_all.columns]
    adj, close, vol = adj_all[columns], close_all[columns], vol_all[columns]
    last_valid = {t: adj[t].last_valid_index() for t in columns}
    sector_of = {t: prices.sector_of(t) for t in columns}
    irx = prices.load("close", [cfg.RISK_FREE], start, end, allow)[cfg.RISK_FREE].reindex(cal).ffill()
    rf_daily = (irx.shift(1) / 100 / 252).fillna(0.0)
    log(f"ราคา {len(cal)} วันทำการ {cal[0].date()} → {cal[-1].date()}, หุ้น {len(stocks)} ตัว + ETF {len(columns) - len(stocks)}")
    # ขอบเขต: ไม่ตัด universe ของราคา/สัญญาณ — A ยังอ่าน ranking ที่คำนวณจากทั้ง universe; กรองเหลือ scope ใน stage_day
    members = scope_members(conf.get("scope"))
    scope = None if members is None else set(members) & set(stocks)
    scope_stocks = stocks if scope is None else [t for t in stocks if t in scope]
    if scope is not None:
        if not scope_stocks:
            raise ConfigError(f"ขอบเขต: หุ้นใน {scope_label(conf['scope'])} ไม่มีราคาในช่วงนี้")
        log(f"ขอบเขต: {scope_label(conf['scope'])} → {len(scope_stocks)} ตัวที่มีราคา (จาก {len(members)} ตัวใน scope)")
    progress("load", 5, None, None)

    # ---- stages
    st = conf["stages"]
    asof = {}
    manual_methods = {}
    for i, m in enumerate("ABC"):
        progress(m, 6 + 3 * i, None, f"เตรียมสัญญาณ {m}")
        if st[m]["mode"] == "off":
            log(f"{m}: ปิด (bypass)")
            continue
        manual = None
        if conf["include_manual"] and m in "BC":
            manual = load_manual_news(m.lower())
            for r in manual:
                manual_methods[r.get("label_method") or "unknown"] = manual_methods.get(r.get("label_method") or "unknown", 0) + 1
            log(f"{m}: รวมข่าว manual {len(manual)} รายการ")
        asof[m] = AsOf(st[m]["version"], manual)
        log(f"{m}: {st[m]['version']} ({st[m]['mode']})")
    label = {m: registry.get(st[m]["version"])["short_label"] for m in asof}

    # ---- condition
    progress("condition", 14, None, "เริ่ม process ของ condition")
    runner = ConditionRunner(conf["condition"]["source"], columns, sector_of)
    log(f"condition: {conf['condition']['name']}")

    # ---- simulate
    n = len(cal)
    cash = conf["capital"]
    units = {}                      # ticker -> units (หน่วย Adj Close)
    last_px = {}
    pos = {}                        # round-trip tracking
    round_trips = []
    target = None                   # dict ที่ condition คืนครั้งล่าสุด (เป้าปัจจุบัน)
    pending = None
    trades, eq_rows, pos_rows, funnel_rows = [], [], [], []
    held_for_delist = set()
    sim_t0 = time.time()

    def value_at(i):
        v = cash
        for t, u in units.items():
            p = adj.iat[i, adj.columns.get_loc(t)]
            if np.isnan(p):
                p = last_px.get(t, 0.0)
            v += u * p
        return v

    def record_trade(i, t, side, u, px, notional, c, w_before, w_after, reasons, decision_date):
        trades.append({"date": cal[i], "decision_date": decision_date, "ticker": t, "side": side,
                       "units": float(u), "price_adj": float(px),
                       "price_close": float(close.iat[i, close.columns.get_loc(t)]) if not np.isnan(close.iat[i, close.columns.get_loc(t)]) else float(px),
                       "notional": float(notional), "cost": float(c), "weight_before": float(w_before),
                       "weight_after": float(w_after), "reasons": list(reasons)})
        p = pos.setdefault(t, {"units": 0.0, "basis": 0.0, "open": cal[i], "realized": 0.0})
        if side == "buy":
            if p["units"] <= 1e-12:
                p.update(open=cal[i], realized=0.0, basis=0.0, units=0.0)
            p["units"] += u
            p["basis"] += notional + c
        else:
            frac = min(1.0, u / p["units"]) if p["units"] > 0 else 1.0
            b = p["basis"] * frac
            p["realized"] += notional - c - b
            p["basis"] -= b
            p["units"] -= u
            if p["units"] <= 1e-9 * max(1.0, u):
                round_trips.append({"ticker": t, "open": str(p["open"].date()), "close": str(cal[i].date()),
                                    "holding_days": int((cal[i] - p["open"]).days), "pnl": float(p["realized"]),
                                    "closed": True})
                pos.pop(t)

    def execute(i, order):
        nonlocal cash
        w = order["weights"]
        pxrow = adj.iloc[i]
        V = value_at(i)
        names = sorted(set(w) | set(units))  # เรียงเสมอ → ลำดับการบวกเลขเหมือนเดิมทุก process (reproducible)
        tradable = [t for t in names if not np.isnan(pxrow.get(t, np.nan))]
        frozen = [t for t in names if t not in set(tradable)]
        for t in frozen:
            if abs(w.get(t, 0) - (units.get(t, 0) * last_px.get(t, 0)) / V) > 1e-9:
                log(f"{cal[i].date()} {t}: ไม่มีราคาวันนี้ — ข้ามการซื้อขายตัวนี้")
        cur = {t: units.get(t, 0.0) * pxrow[t] for t in tradable}
        c_tot = 0.0
        for _ in range(4):
            Vp = V - c_tot
            desired = {t: w.get(t, 0.0) * Vp for t in tradable}
            c_new = cost * sum(abs(desired[t] - cur[t]) for t in tradable)
            if abs(c_new - c_tot) < 1e-10 * V:
                break
            c_tot = c_new
        Vp = V - c_tot
        spent = 0.0
        for t in sorted(tradable, key=lambda x: (desired[x] - cur[x], x)):  # ขายก่อนซื้อ
            d = desired[t] - cur[t]
            if abs(d) < 1e-7 * V:
                continue
            px = pxrow[t]
            du = d / px
            c = cost * abs(d)
            side = "buy" if d > 0 else "sell"
            reasons = list(order["reasons"].get(t, []))
            if side == "sell" and w.get(t, 0.0) == 0:
                reasons.append("condition: weight 0% → ขายทั้งหมด")
            else:
                reasons.append(f"condition: weight {100 * w.get(t, 0.0):.2f}%")
            reasons += [f"condition: {x}" for x in order["notes"].get(t, [])]
            if side == "sell":
                du = -min(-du, units.get(t, 0.0))
            record_trade(i, t, side, abs(du), px, abs(d), c, cur[t] / V, desired[t] / Vp if Vp else 0.0,
                         reasons, order["decision_date"])
            units[t] = units.get(t, 0.0) + du
            if units[t] <= 1e-12:
                units.pop(t, None)
            spent += d + c
            last_px[t] = px
        cash -= spent
        if cash < -1e-6 * V:
            log(f"⚠️ {cal[i].date()} เงินสดติดลบ {cash:.2f} (ปัดเศษ) — ตั้งเป็น 0")
        cash = max(cash, 0.0) if cash > -1e-6 * V else cash

    try:
        for i, t in enumerate(cal):
            if cancelled():
                raise Cancelled("ผู้ใช้ยกเลิก")
            if time.time() - t_start > cfg.JOB_TIMEOUT_SEC:
                raise ConditionError(f"job เกินเวลารวม {cfg.JOB_TIMEOUT_SEC // 60} นาที")
            # 1) execute
            if pending is not None:
                execute(i, pending)
                pending = None
            # 2) delist → cash
            pxrow = adj.iloc[i]
            for tk in list(units):
                p = pxrow[tk]
                if not np.isnan(p):
                    last_px[tk] = p
                elif last_valid.get(tk) is None or t > last_valid[tk]:
                    lp = last_px.get(tk, 0.0)
                    notional = units[tk] * lp
                    c = cost * notional
                    record_trade(i, tk, "sell", units[tk], lp, notional, c, notional / max(value_at(i), 1e-9), 0.0,
                                 [f"system: ไม่มีราคาหลัง {last_valid[tk].date() if last_valid.get(tk) is not None else '?'} "
                                  "(delist/หยุดเทรด) → แปลงเป็นเงินสดที่ราคาล่าสุด"], str(t.date()))
                    cash += notional - c
                    units.pop(tk)
                    held_for_delist.add(tk)
                    log(f"{t.date()} {tk}: ไม่มีราคาแล้ว → ขายเป็นเงินสดที่ {lp:.4f}")
            # 3) mark to market
            V = value_at(i)
            invested = V - cash
            eq_rows.append({"date": t, "strategy": V, "cash": cash, "n_holdings": len(units), "invested": invested})
            weights_now = {}
            for tk, u in units.items():
                p = pxrow[tk] if not np.isnan(pxrow[tk]) else last_px.get(tk, 0.0)
                weights_now[tk] = u * p / V if V else 0.0
                pos_rows.append({"date": t, "ticker": tk, "weight": weights_now[tk], "value": u * p})

            # 4) pipeline + decide (ไม่ต้องตัดสินใจวันสุดท้าย เพราะไม่มีวัน t+1 ให้ execute)
            price_payload = {"date": str(t.date()), "prices": _price_row(adj, close, vol, i)}
            held = sorted(units)
            universe, a_recs, b_recs, c_recs, fun = stage_day(t, pxrow, stocks, held, asof, st, sector_of, scope)

            if i < n - 1:
                payload = dict(price_payload, universe=universe, a=a_recs, b=b_recs, c=c_recs,
                               portfolio={"value": V, "cash": cash, "cash_weight": cash / V if V else 1.0,
                                          "weights": weights_now, "units": dict(units)},
                               stage_enabled={m: st[m]["mode"] != "off" for m in "ABC"})
                res = runner.day(payload)
                w = res["weights"]
                if w is not None:
                    w = _validate_weights(w, set(universe) | set(ALLOWED_ETFS) | set(units), t)
                    same = target is not None and set(w) == set(target) and all(abs(w[k] - target[k]) < 1e-9 for k in w)
                    if not same:
                        reasons = {}
                        for tk in sorted(set(w) | set(units)):
                            rs = []
                            if "A" in asof:
                                rs.append(_chip("A", label["A"], a_recs.get(tk) or asof["A"].at(tk, t)))
                            if "B" in asof:
                                rs.append(_chip("B", label["B"], b_recs.get(tk)))
                            if "C" in asof:
                                e = cfg.SECTOR_ETFS.get(sector_of.get(tk, ""), None)
                                rs.append(_chip("C", label["C"], c_recs.get(e) if e else None, f"{e} " if e else ""))
                            reasons[tk] = rs
                        pending = {"weights": w, "reasons": reasons, "notes": res.get("notes") or {},
                                   "decision_date": str(t.date())}
                        target = w
                fun["held"] = sum(1 for v in (target or {}).values() if v > 0)
            else:
                fun["held"] = len(units)
            funnel_rows.append(fun)

            if i % 5 == 0 or i == n - 1:
                done = i + 1
                el = time.time() - sim_t0
                thr = done / el if el > 0 else None
                eta = (n - done) / thr + 3 if thr else None
                progress("simulate", 15 + 80 * done / n, eta, f"{t.date()} ({done}/{n} วัน)")
    finally:
        runner.close()

    # ---- benchmarks + metrics
    progress("metrics", 96, 3, "คำนวณ metrics")
    equity = pd.DataFrame(eq_rows).set_index("date")
    equity["spy"] = _bench_spy(adj, conf["capital"], cost)
    equity["ew"] = _bench_ew(adj[scope_stocks], conf["capital"], cost)  # EW ของหุ้นใน scope (ทั้ง universe ถ้า scope = all)
    trades_df = pd.DataFrame(trades, columns=["date", "decision_date", "ticker", "side", "units", "price_adj", "price_close",
                                              "notional", "cost", "weight_before", "weight_after", "reasons"])
    for tk, p in pos.items():
        lp = last_px.get(tk, 0.0)
        round_trips.append({"ticker": tk, "open": str(p["open"].date()), "close": None,
                            "holding_days": int((cal[-1] - p["open"]).days),
                            "pnl": float(p["realized"] + p["units"] * lp - p["basis"]), "closed": False})
    met = metrics.compute(equity, rf_daily, trades_df, round_trips, cfg.HELD_OUT_START)
    funnel = pd.DataFrame(funnel_rows)
    met["funnel_avg"] = {k: float(funnel[k].mean()) for k in ("market", "universe", "after_A", "after_B", "after_C", "held") if k in funnel}
    if scope is not None:  # เฉพาะเมื่อจำกัดขอบเขต — ผลของ scope = all ต้องตรงกับที่บันทึกไว้ก่อนมีฟีเจอร์นี้ทุกหลัก
        met["scope"] = {"mode": conf["scope"]["mode"], "label": scope_label(conf["scope"]), "n_members": len(members),
                        "n_priced": len(scope_stocks), "ew_names": len(scope_stocks)}
    met["dropped_no_price_avg"] = float(funnel["dropped_no_price"].mean()) if "dropped_no_price" in funnel else 0.0
    met["delisted_to_cash"] = sorted(held_for_delist)

    # ---- save artifacts
    progress("save", 99, 1, "บันทึกผล")
    equity.reset_index().to_parquet(out_dir / "equity.parquet", index=False)
    pd.DataFrame(pos_rows, columns=["date", "ticker", "weight", "value"]).to_parquet(out_dir / "positions.parquet", index=False)
    trades_df.to_parquet(out_dir / "trades.parquet", index=False)
    funnel.to_parquet(out_dir / "funnel.parquet", index=False)
    (out_dir / "round_trips.json").write_text(json.dumps(round_trips, ensure_ascii=False))
    (out_dir / "metrics.json").write_text(json.dumps(met, ensure_ascii=False, indent=1))
    conf_out = {k: v for k, v in conf.items() if k != "condition"}
    conf_out["condition"] = {k: v for k, v in conf["condition"].items() if k != "source"}
    (out_dir / "config.json").write_text(json.dumps(conf_out, ensure_ascii=False, indent=1))
    (out_dir / "condition_snapshot.py").write_text(conf["condition"]["source"], encoding="utf-8")
    used = columns + [cfg.RISK_FREE]
    prov = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": _git(),
        "data_hash": prices.data_hash(used, start, end, allow),
        "universe_manifest_hash": prices.manifest().get("data_hash"),
        "price_start_config": cfg.PRICE_START,
        "n_tickers_priced": len(used),
        "held_out_touched": bool(conf["held_out"]["touched"]),
        "versions": {m: registry.get(st[m]["version"]) for m in asof},
        # มีการรู้ผลล่วงหน้าปนอยู่ไหม: B/C version แบบ ORACLE หรือข่าว manual (toggle) ที่ label แบบ hindsight
        "contains_oracle_signal": bool(any(registry.get(st[m]["version"])["result_badge"] == "oracle" for m in asof)
                                       or manual_methods.get("hindsight")),
        "manual_label_methods": dict(sorted(manual_methods.items())),
        "condition_sha256": hashlib.sha256(conf["condition"]["source"].encode()).hexdigest(),
        "execution": cfg.EXECUTION,
        "runtime_sec": round(time.time() - t_start, 2),
        "python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
        "condition_stdout_tail": "".join(runner.stdout)[-4000:],
    }
    (out_dir / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1, default=str))
    progress("save", 100, 0, "เสร็จ")
    log(f"เสร็จใน {prov['runtime_sec']} วินาที · trades {len(trades_df)}")
    return {"metrics": met, "provenance": prov}


def stage_day(t, pxrow, stocks, held, asof, st, sector_of, scope=None):
    """pipeline ของวันเดียว: ขอบเขต (หุ้นใน scope ที่มีราคา ณ t) → A → B → C — ใช้ร่วมกันระหว่าง run() และ dry_run()
    scope = None (ทั้ง universe) หรือ set ของ ticker — **กรองหลังอ่านสัญญาณ A**: record ของ A (class/score/rank)
    มาจากการจัดอันดับทั้ง universe ใน export เสมอ ไม่มีการจัดอันดับใหม่เฉพาะหุ้นใน scope
    คืน (universe, a_recs, b_recs, c_recs, funnel_row) ; ทุก record มี date ≤ t (AsOf บังคับ)"""
    has_px = [tk for tk in stocks if not np.isnan(pxrow[tk])]
    fun = {"date": t}
    if scope is not None:
        fun["market"] = len(has_px)
        has_px = [tk for tk in has_px if tk in scope]
    fun["universe"] = len(has_px)
    a_recs, b_recs = {}, {}
    if "A" in asof:
        snap = asof["A"].snapshot(t)
        fun["a_rebalance"] = asof["A"].rebalance_date(t)
        passed = [k for k, r in snap.items() if _crit_A(r) and (scope is None or k in scope)]
        hp = set(has_px)
        fun["dropped_no_price"] = sum(1 for k in passed if k not in hp)
        fun["a_signal_empty"] = not snap
        passA = sorted(k for k in passed if k in hp)
        a_recs = {k: snap.get(k) for k in sorted(set(passA) | set(held)) if snap.get(k) is not None}
    else:
        passA = has_px
    fun["after_A"] = len(passA)
    if "B" in asof:  # B ไม่กรอง — แนบคะแนนให้หุ้นที่รอดจาก A (+ ที่ถืออยู่); ไม่มีข่าว = applicable False
        for k in sorted(set(passA) | set(held)):
            b_recs[k] = asof["B"].at(k, t) or not_applicable("B", t)
    passB = passA
    fun["after_B"] = len(passB)
    c_recs = {}
    if "C" in asof:
        for e in cfg.SECTOR_ETFS.values():
            r = asof["C"].at(e, t)
            if r is not None:
                c_recs[e] = dict(r, sector=e)
    passC = passB  # C ไม่กรอง — แนบสัญญาณราย sector (ctx.c / ctx.c_for) ให้ condition ตัดสินใจ
    fun["after_C"] = len(passC)
    return passC, a_recs, b_recs, c_recs, fun


_asof_cache: dict = {}


def _asof(vid: str, manual=None):
    """AsOf ของ version (cache ตาม created_at ของ manifest — rebuild แล้ว cache เก่าไม่ถูกใช้)"""
    if manual:
        return AsOf(vid, manual)
    key = (vid, registry.get(vid).get("created_at"))
    if key not in _asof_cache:
        _asof_cache.clear() if len(_asof_cache) > 16 else None
        _asof_cache[key] = AsOf(vid)
    return _asof_cache[key]


def box_stats(conf: dict) -> dict:
    """ตัวเลขบนกล่อง A/B/C ในหน้า Pipeline ก่อนรัน — ณ วันทำการสุดท้ายของช่วงที่เลือก (ไม่ใช่ปุ่ม แค่ให้เห็นภาพ)
    A: ผ่านกี่ตัว (class == selected และ applicable) · B/C: การกระจาย class ของหุ้นที่รอดจาก A (B/C ไม่กรอง)"""
    from collections import Counter

    allow = conf["held_out"]["touched"]
    cal = prices.calendar(conf["start"], conf["end"], allow)
    if not len(cal):
        return {}
    t = cal[-1]
    adj = prices.load("adj", None, t, t, allow)
    stocks = [x for x in prices.available_tickers("stock") if x in adj.columns]
    st = conf["stages"]
    asof = {m: _asof(st[m]["version"], load_manual_news(m.lower()) if conf["include_manual"] and m in "BC" else None)
            for m in "ABC" if st[m]["mode"] != "off"}
    members = scope_members(conf.get("scope"))
    sector_of = {x: prices.sector_of(x) for x in stocks}
    universe, a_recs, b_recs, c_recs, fun = stage_day(t, adj.iloc[-1], stocks, [], asof, st, sector_of,
                                                     None if members is None else set(members))
    out = {"date": str(t.date()), "universe": fun["universe"], "pass": len(universe)}
    if "A" in asof:
        R = fun.get("a_rebalance")
        out["A"] = {"pass": fun["after_A"], "rebalance": str(pd.Timestamp(R).date()) if R is not None else None}
    order = ["positive", "neutral", "negative", "none"]
    if "B" in asof:
        c = Counter((b_recs.get(k) or {}).get("class") if (b_recs.get(k) or {}).get("applicable") else "none" for k in universe)
        out["B"] = {"pass": len(universe), "dist": {k: c.get(k, 0) for k in order}}
    if "C" in asof:
        c = Counter((c_recs.get(cfg.SECTOR_ETFS.get(sector_of.get(k), "")) or {}).get("class") or "none" for k in universe)
        out["C"] = {"pass": len(universe), "dist": {k: c.get(k, 0) for k in order},
                    "sectors": {e: r.get("class") for e, r in sorted(c_recs.items())}}
    return out


def dry_run(conf: dict, date=None, history_days: int = 260) -> dict:
    """Validate ใน editor: รัน pipeline + decide() วันเดียว (พอร์ตว่าง) — ไม่ซื้อขาย ไม่บันทึกอะไร"""
    allow = conf["held_out"]["touched"]
    end = pd.Timestamp(date or conf["end"])
    cal_all = prices.calendar(conf["start"], conf["end"], allow)
    cal_all = cal_all[cal_all <= end]
    if not len(cal_all):
        raise ConfigError("ไม่มีวันทำการในช่วงที่เลือก")
    t = cal_all[-1]
    hstart = max(pd.Timestamp(cfg.PRICE_START), t - pd.Timedelta(days=int(history_days * 1.5)))
    cal = prices.calendar(hstart, t, allow)
    adj = prices.load("adj", None, hstart, t, allow).reindex(cal)
    close = prices.load("close", None, hstart, t, allow).reindex(cal)
    vol = prices.load("volume", None, hstart, t, allow).reindex(cal)
    stocks = [x for x in prices.available_tickers("stock") if x in adj.columns and adj[x].notna().any()]
    columns = stocks + [x for x in ALLOWED_ETFS if x in adj.columns]
    adj, close, vol = adj[columns], close[columns], vol[columns]
    sector_of = {x: prices.sector_of(x) for x in columns}
    st = conf["stages"]
    asof = {m: AsOf(st[m]["version"], load_manual_news(m.lower()) if conf["include_manual"] and m in "BC" else None)
            for m in "ABC" if st[m]["mode"] != "off"}
    members = scope_members(conf.get("scope"))
    scope = None if members is None else set(members)
    universe, a_recs, b_recs, c_recs, fun = stage_day(t, adj.iloc[-1], stocks, [], asof, st, sector_of, scope)
    runner = ConditionRunner(conf["condition"]["source"], columns, sector_of)
    try:
        for i in range(len(cal) - 1):
            runner.prices_only({"date": str(cal[i].date()), "prices": _price_row(adj, close, vol, i)})
        res = runner.day({"date": str(t.date()), "prices": _price_row(adj, close, vol, len(cal) - 1),
                          "universe": universe, "a": a_recs, "b": b_recs, "c": c_recs,
                          "portfolio": {"value": conf["capital"], "cash": conf["capital"], "cash_weight": 1.0,
                                        "weights": {}, "units": {}},
                          "stage_enabled": {m: st[m]["mode"] != "off" for m in "ABC"}})
    finally:
        runner.close()
    w = res["weights"]
    if w is not None:
        w = _validate_weights(w, set(universe) | set(ALLOWED_ETFS), t)
    fun = {k: (str(v.date()) if isinstance(v, pd.Timestamp) else v) for k, v in fun.items()}
    return {"date": str(t.date()), "funnel": fun, "universe_size": len(universe), "weights": w,
            "weight_sum": None if w is None else float(sum(w.values())), "notes": res.get("notes") or {},
            "stdout": "".join(runner.stdout)[-4000:]}


def _price_row(adj, close, vol, i):
    f = lambda row: [None if np.isnan(x) else float(x) for x in row.to_numpy()]  # noqa: E731
    return {"adj": f(adj.iloc[i]), "close": f(close.iloc[i]), "volume": f(vol.iloc[i])}


def _validate_weights(w, allowed, t):
    if not isinstance(w, dict):
        raise ConditionError(f"decide() ต้องคืน dict {{ticker: weight}} หรือ None (ได้ {type(w).__name__})")
    out = {}
    bad = []
    for k, v in w.items():
        if not isinstance(k, str):
            raise ConditionError(f"ticker ต้องเป็น str (ได้ {k!r})")
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ConditionError(f"น้ำหนักของ {k} ไม่ใช่ตัวเลข ({v!r})") from None
        if not np.isfinite(v) or v < 0:
            raise ConditionError(f"น้ำหนักของ {k} = {v} (ต้อง ≥ 0 และเป็นตัวเลขจริง — sandbox เป็น long-only)")
        if k not in allowed:
            bad.append(k)
        if v > 0:
            out[k] = v
    if bad:
        raise ConditionError(f"{t.date()}: ticker ไม่อยู่ใน universe/ETF ที่อนุญาต/พอร์ตที่ถืออยู่: {bad[:8]}"
                             + (f" (+{len(bad) - 8})" if len(bad) > 8 else ""))
    s = sum(out.values())
    if s > 1 + 1e-6:
        raise ConditionError(f"{t.date()}: ผลรวมน้ำหนัก = {s:.6f} > 1.0 (ห้ามใช้ leverage)")
    return out


def _bench_spy(adj, capital, cost):
    s = adj[cfg.BENCHMARK]
    out = pd.Series(capital, index=adj.index, dtype=float)
    u = capital / (1 + cost) / s.iloc[1]
    out.iloc[1:] = u * s.iloc[1:]
    return out


def _bench_ew(adj, capital, cost):
    """Equal-weight ของหุ้นทุกตัวใน universe ราคาที่มีราคา ณ วัน rebalance — rebalance วันทำการแรกของเดือน
    (เริ่มวันที่ 2 ของช่วง เหมือน SPY), cost ต่อขาเท่ากับ strategy, หุ้นที่ไม่มีราคาหลังจากนั้น = ถือราคาล่าสุด (เท่ากับเงินสด)"""
    idx = adj.index
    out = pd.Series(capital, index=idx, dtype=float)
    firsts = [1] + [i for i in range(2, len(idx)) if idx[i].month != idx[i - 1].month]
    V, w_old = capital, None
    px = adj.ffill()
    for k, i0 in enumerate(firsts):
        i1 = firsts[k + 1] if k + 1 < len(firsts) else len(idx) - 1
        row = adj.iloc[i0]
        names = row.index[row.notna()]
        if not len(names):  # scope เล็ก (เช่นหุ้น IPO ตัวเดียว) ยังไม่มีราคา → ถือเงินสดรอบนี้
            out.iloc[i0:i1 + 1] = V
            w_old = None
            continue
        w = pd.Series(1.0 / len(names), index=names)
        if w_old is None:
            turn = 1.0
        else:
            turn = (w.reindex(w_old.index.union(w.index), fill_value=0) - w_old.reindex(w_old.index.union(w.index), fill_value=0)).abs().sum()
        V *= (1 - cost * turn)
        rel = px.iloc[i0:i1 + 1][names] / px.iloc[i0][names]
        path = V * (rel * w).sum(axis=1)
        out.iloc[i0:i1 + 1] = path.to_numpy()
        end_rel = rel.iloc[-1]
        w_old = end_rel * w / (end_rel * w).sum()
        V = float(path.iloc[-1])
    return out
