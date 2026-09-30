"""
สาเหตุของ trade แต่ละรายการ (Q0/Q1) — อ่านจากบันทึกตอนรัน (trades.parquet + decisions.parquet + funnel.parquet) ไม่คำนวณใหม่

engine ของ sandbox: เมื่อเป้าน้ำหนัก "ตัวใดตัวหนึ่ง" เปลี่ยน → วันถัดไปซื้อขาย "ทุกตัว" กลับไปที่เป้า (หุ้นที่เป้าเท่าเดิมแต่ราคาขยับ
ก็ถูกตัด/เติมด้วย) — Q0 พบว่านี่คือสาเหตุหลักของ SELL/BUY บนหุ้นที่ไม่มีข่าวร้าย (ดู DECISIONS #30)

ลำดับการตัดสิน (ต่อ trade):
  1. system (delist → เงินสด)
  2. tag ที่ condition แนบกับ ctx.note(..., kind=, ref=) วันนั้น (Q1) — ถ้าไม่มี tag (ผลก่อน Q1) ใช้ข้อความ note ของ condition_fixed
  3. วัน rebalance ของ A (รายชื่อใหม่) → rebalance
  4. เป้าของหุ้นตัวนี้เท่าเดิม → drift (ปรับกลับเป้าเพราะเป้าตัวอื่นเปลี่ยน; ref = หุ้นที่เป้าเปลี่ยนวันนั้น)
  5. เป้าลดลงวันเดียวกับที่หุ้นอื่นซื้อคืน (ผลก่อน Q1) → ถูกดึงเงินคืน
  6. อื่น ๆ = condition เปลี่ยนเป้าเอง (ไม่มี tag)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# ชนิด → (ป้ายสั้นบนกราฟ, คำอธิบายใน legend, สี) — ใช้ร่วมกันทั้งกราฟหุ้นรายตัว (Q1) และ equity curve (Q4)
KINDS = {
    "sell_news": ("SELL ข่าวร้าย", "ขายเพราะข่าวร้ายของหุ้นตัวนี้เอง (ข่าว -2 หรือ -1 ที่ราคายืนยันแล้ว)", "#F43F5E"),
    "sell_pullback": ("SELL → คืนให้", "ขายเพราะถูกดึงเงินคืน: หุ้นอื่นที่เคยขายครึ่งราคาลง ≥ 15% จึงดึงเงินที่เคยย้ายมาไว้ตัวนี้กลับไปซื้อคืน", "#FB923C"),
    "sell_rebalance": ("SELL รอบปี", "ขายตอน rebalance ประจำปีของ A (หลุดรายชื่อ หรือปรับกลับให้เท่ากันทุกตัว)", "#94A3B8"),
    "sell_condition": ("SELL เงื่อนไข", "condition ลดเป้าของหุ้นตัวนี้ (ไม่มีป้ายสาเหตุจาก condition)", "#F87171"),
    "sell_delist": ("SELL delist", "ระบบขายเป็นเงินสดเพราะหุ้นไม่มีราคาแล้ว (delist/หยุดเทรด)", "#64748B"),
    "buy_rebalance": ("BUY รอบปี", "ซื้อตอน rebalance ประจำปีของ A (เข้ารายชื่อใหม่ หรือปรับกลับให้เท่ากันทุกตัว)", "#34D399"),
    "buy_receive": ("BUY ← รับเงินจาก", "ซื้อเพราะรับเงินที่พักจากการขายครึ่งของหุ้นอื่น (หุ้นตัวนี้มีข่าว +2)", "#A78BFA"),
    "buy_buyback": ("BUY ซื้อคืน", "ซื้อคืนเต็มจำนวน: ราคาลง ≥ 15% จากจุดที่เคยขายครึ่ง (ดึงเงินกลับจากหุ้นที่เคยรับไป)", "#22D3EE"),
    "buy_condition": ("BUY เงื่อนไข", "condition เพิ่มเป้าของหุ้นตัวนี้ (ไม่มีป้ายสาเหตุจาก condition)", "#4ADE80"),
    "drift": ("ปรับกลับเป้า", "เป้าของหุ้นตัวนี้เท่าเดิม — ระบบซื้อ/ขายเล็กน้อยให้กลับไปที่เป้า เพราะวันนั้นเป้าของหุ้นตัวอื่นเปลี่ยน (engine ปรับทั้งพอร์ตพร้อมกัน)", "#8B8FB0"),
    "unknown": ("SELL/BUY", "ไม่ทราบสาเหตุ — ผลนี้รันก่อนมีบันทึกรายวัน (N5) กด Re-run เพื่อดูสาเหตุ", "#CBD5E1"),
}
# tag ที่ condition ส่งได้ผ่าน ctx.note(ticker, text, kind=..., ref=[...])
NOTE_KINDS = ("news_sell", "pullback", "buyback", "receive")
# ข้อความ note ของ condition_fixed (ผลที่รันก่อน Q1 ไม่มี tag) — จับทั้งวลีเพื่อไม่ชนกับ note อื่น
_LEGACY = (("news_sell", ("ข่าว -2 → ขายครึ่งทันที", "ยืนยันแล้ว: ราคา")), ("buyback", ("ดึงเงินกลับมาซื้อคืนเต็มจำนวน",)),
           ("receive", ("→ รับเงินที่พักจากการขายครึ่ง",)))


def _tags(row) -> list:
    raw = row.get("tags_json") if hasattr(row, "get") else None
    if isinstance(raw, str) and raw:
        return json.loads(raw)
    out = []
    for n in list(row.get("notes") if row.get("notes") is not None else []):
        for kind, pats in _LEGACY:
            if any(p in n for p in pats):
                out.append({"kind": kind, "ref": [], "legacy": True})
    return out


def _moved(raw, tk) -> float:
    try:
        cut = (json.loads(raw) if isinstance(raw, str) else {}).get("cut") or {}
    except ValueError:
        return 0.0
    return float((cut.get("moved") or {}).get(tk, 0.0)) if isinstance(cut, dict) else 0.0


def _legacy_sources(full, d, tk) -> list:
    """ผลก่อน Q1 (ไม่มี ref): หุ้นต้นทาง = หุ้นที่ state.cut.moved[tk] เพิ่มขึ้นวันนี้เทียบกับบันทึกก่อนหน้า (condition_fixed)"""
    if full is None or "state_json" not in full:
        return []
    out = []
    today = full[full["date"] == d]
    for src, raw in zip(today["ticker"], today["state_json"]):
        now = _moved(raw, tk)
        if now <= 0:
            continue
        prev = full[(full["ticker"] == src) & (full["date"] < d)]
        before = _moved(prev["state_json"].iloc[-1], tk) if len(prev) else 0.0
        if now > before + 1e-12:
            out.append(src)
    return sorted(out)


def classify(trades: pd.DataFrame, decisions: pd.DataFrame | None, funnel: pd.DataFrame | None = None) -> list:
    """คืน list ของ dict ต่อ trade (ลำดับเดียวกับ trades): kind, label, ref (ticker ที่เกี่ยวข้อง), detail"""
    if decisions is None or decisions.empty:
        out = [{"kind": "sell_delist" if any(str(x).startswith("system:") for x in r.reasons) else "unknown", "ref": [], "detail": "", "tags": []}
               for r in trades.itertuples()]
        for x in out:
            x["label"] = KINDS[x["kind"]][0]
        return out
    dec = decisions.copy()
    dec["date"] = dec["date"].astype(str)
    full = dec.sort_values("date", kind="stable")
    dec = dec[dec["date"].isin(set(trades["decision_date"].astype(str)))]  # ใช้แค่วันที่มีการตัดสินใจซื้อขาย (ไฟล์ใหญ่ไม่ช้า)
    by_day = {d: g.set_index("ticker") for d, g in dec.groupby("date")}
    rebal = set()
    if funnel is not None and "a_rebalance" in funnel and funnel["a_rebalance"].notna().any():
        f = funnel[["date", "a_rebalance"]].copy()
        f["date"] = pd.to_datetime(f["date"]).dt.strftime("%Y-%m-%d")
        prev = None
        for d, r in zip(f["date"], f["a_rebalance"]):
            if r is not None and r == r and r != prev:
                rebal.add(d)
            prev = r
    first = min(by_day) if by_day else None
    if first:
        rebal.add(first)
    tags_day = {}
    for d, g in by_day.items():
        tags_day[d] = {tk: _tags(r) for tk, r in g.iterrows()}
    out = []
    for r in trades.itertuples():
        d, tk, side = str(r.decision_date), r.ticker, r.side
        if any(str(x).startswith("system:") for x in r.reasons):
            out.append({"kind": "sell_delist", "ref": [], "detail": "", "tags": []})
            continue
        g = by_day.get(d)
        me = g.loc[tk] if g is not None and tk in g.index else None
        tb = float(me["target_before"]) if me is not None else None
        ta = float(me["target_after"]) if me is not None else None
        tags = tags_day.get(d, {}).get(tk, [])
        kinds = {}
        for t in tags:  # หลาย tag ชนิดเดียวกันในวันเดียว (เช่น รับเงินจาก 4 หุ้น) → รวม ref ทั้งหมด
            kinds.setdefault(t["kind"], set()).update(t.get("ref") or [])
        refs = lambda k: sorted(kinds[k])  # noqa: E731
        changed = [] if g is None else sorted(x for x, rr in g.iterrows()
                                              if x != tk and abs(float(rr["target_after"]) - float(rr["target_before"])) > 1e-9)
        if side == "sell" and "news_sell" in kinds:
            res = {"kind": "sell_news", "ref": []}
        elif side == "sell" and "pullback" in kinds:
            res = {"kind": "sell_pullback", "ref": refs("pullback")}
        elif side == "buy" and "buyback" in kinds:
            res = {"kind": "buy_buyback", "ref": refs("buyback")}
        elif side == "buy" and "receive" in kinds:
            res = {"kind": "buy_receive", "ref": refs("receive")}
            if not res["ref"] and any(t.get("legacy") for t in tags):
                res.update(ref=_legacy_sources(full, d, tk), ref_inferred=True)
        elif d in rebal:
            res = {"kind": f"{side}_rebalance", "ref": []}
        elif tb is not None and abs(ta - tb) < 1e-9:
            res = {"kind": "drift", "ref": changed}
        elif side == "sell" and tb is not None and ta < tb:
            bb = [x for x, tg in tags_day.get(d, {}).items() if x != tk and any(t["kind"] == "buyback" for t in tg)]
            res = {"kind": "sell_pullback", "ref": bb, "ref_inferred": True} if bb else {"kind": "sell_condition", "ref": []}
        else:
            res = {"kind": f"{side}_condition", "ref": []}
        res["tags"] = sorted({t["kind"] for t in tags})  # ทุกเหตุการณ์ของหุ้นนี้วันนั้น (เช่น ถูกดึงเงินคืน + รับเงิน ในวันเดียวกัน → สุทธิเป็นซื้อ)
        if tb is not None:
            res["detail"] = f"เป้า {100 * tb:.2f}% → {100 * ta:.2f}% · น้ำหนักจริงก่อนซื้อขาย {100 * r.weight_before:.2f}%"
        else:
            res["detail"] = ""
        out.append(res)
    for x in out:
        x["label"] = KINDS[x["kind"]][0]
    return out


_CACHE: dict = {}


def classify_dir(d: Path) -> pd.DataFrame:
    """trades ของผลหนึ่งชุด + คอลัมน์ kind/label/ref/detail/tags (cache ต่อไฟล์ — ผลที่บันทึกแล้วไม่เปลี่ยน)"""
    d = Path(d)
    key = (str(d), (d / "trades.parquet").stat().st_mtime_ns)
    if key not in _CACHE:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = _classify_dir(d)
    return _CACHE[key].copy()


def _classify_dir(d: Path) -> pd.DataFrame:
    tr = pd.read_parquet(d / "trades.parquet")
    dec = pd.read_parquet(d / "decisions.parquet") if (d / "decisions.parquet").exists() else None
    fun = pd.read_parquet(d / "funnel.parquet") if (d / "funnel.parquet").exists() else None
    c = classify(tr, dec, fun)
    tr = tr.copy()
    for k in ("kind", "label", "ref", "detail", "tags"):
        tr[k] = [x.get(k, []) for x in c]
    tr["ref_inferred"] = [bool(x.get("ref_inferred")) for x in c]
    return tr
