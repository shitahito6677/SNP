"""
บันทึก/เปิดผลการทดลองของ sandbox v2 — `sandbox/v2/experiments/<exp_id>/`

    config.json            ทุกกล่อง/วันที่/capital/cost/held-out + ชื่อที่ผู้ใช้ตั้ง          (commit ได้)
    condition_snapshot.py  ข้อความเงื่อนไขเต็ม ณ เวลารัน                                (commit ได้)
    metrics.json           metrics ทั้งหมด                                              (commit ได้)
    provenance.json        git hash, data_hash, manifest ของทุก version, held_out_touched (commit ได้)
    summary.json           การ์ด gallery + sparkline (เล็ก)                              (commit ได้)
    equity/positions/trades/funnel.parquet, round_trips.json                           (gitignored)

เปิดผลเก่า = อ่านไฟล์ ไม่รันใหม่ → ตัวเลขเหมือนเดิมทุกหลัก
"""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from sandbox.v2 import config as cfg

ROOT = cfg.EXPERIMENTS_DIR
ARTIFACTS = ["config.json", "condition_snapshot.py", "metrics.json", "provenance.json", "equity.parquet",
             "positions.parquet", "trades.parquet", "funnel.parquet", "round_trips.json"]
ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}_[a-z0-9-]{0,40}$")


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:40]


def _dir(exp_id) -> Path:
    if not ID_RE.match(exp_id or ""):
        raise KeyError(f"exp_id ไม่ถูกต้อง: {exp_id!r}")
    d = ROOT / exp_id
    if not (d / "config.json").exists():
        raise KeyError(f"ไม่พบการทดลอง {exp_id}")
    return d


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def badges(conf, prov) -> list:
    out = []
    if prov.get("held_out_touched"):
        out.append({"kind": "held_out", "text": "HELD-OUT"})
    if conf["stages"]["A"].get("ranking") == "scoped" or prov.get("a_ranking_mode") == "scoped":
        out.insert(0, {"kind": "scoped_a", "text": "A โหมดทดสอบ (จัดอันดับใน scope)"})
    if prov.get("contains_oracle_signal") or any(v.get("result_badge") == "oracle" for v in (prov.get("versions") or {}).values()):
        out.insert(0, {"kind": "oracle", "text": "ORACLE"})
    for m, v in (prov.get("versions") or {}).items():
        if v.get("result_badge") == "stub":
            out.append({"kind": "stub", "text": f"{m} STUB"})
        elif v.get("result_badge") == "negative":
            out.append({"kind": "negative", "text": f"{m} NEGATIVE"})
        elif v.get("result_badge") == "manual":
            out.append({"kind": "manual_labels", "text": f"{m} MANUAL"})
    if conf["stages"]["A"]["mode"] not in ("on", "filter"):  # "filter" = config ก่อน G1
        out.append({"kind": "survivorship", "text": "SURVIVORSHIP"})
    if conf.get("include_manual"):
        out.append({"kind": "manual", "text": "MANUAL NEWS"})
    return out


def chips(conf, prov) -> list:
    out = []
    for m in "ABC":
        s = conf["stages"][m]
        if s["mode"] == "off":
            out.append(f"{m} off")
        else:
            lab = (prov.get("versions") or {}).get(m, {}).get("short_label", s["version"])
            out.append(f"{lab}{' (กรองในกล่อง·เดิม)' if s['mode'] == 'filter' and m != 'A' else ''}"
                       f"{' (จัดอันดับใน scope·ทดสอบ)' if m == 'A' and s.get('ranking') == 'scoped' else ''}")
    out.append(f"cond: {conf['condition'].get('id') or conf['condition'].get('name')}")
    sc = conf.get("scope") or {}
    if sc.get("mode") == "sectors":
        out.insert(0, "scope: " + " ".join(sc["sectors"]))
    elif sc.get("mode") == "tickers":
        out.insert(0, "scope: " + " ".join(sc["tickers"][:4]) + (f" +{len(sc['tickers']) - 4}" if len(sc["tickers"]) > 4 else ""))
    return out


def _legacy(conf) -> list:
    """ผลที่บันทึกด้วยกล่องแบบเดิม (ก่อน G1): เปิดดูได้ตามเดิม (ข้อมูลอยู่ในไฟล์) แต่ Re-run จะได้ความหมายใหม่"""
    from sandbox.v2 import engine
    try:
        return engine.legacy_notes(conf.get("stages"))[1]
    except Exception as e:  # noqa: BLE001
        return [f"อ่าน config กล่องเดิมไม่ได้: {e}"]


def empty_reason(conf, met) -> str | None:
    """พอร์ตไม่เคยถือหุ้นเลย → บอกว่าหุ้นหายไปที่ขั้นไหนของ funnel (แทนกราฟเปล่าเงียบ ๆ)"""
    f = met.get("funnel_avg") or {}
    if (met.get("full") or {}).get("strategy", {}).get("avg_holdings", 1) or f.get("held", 1):
        return None
    sc = conf.get("scope") or {}
    who = "หุ้นที่เลือก" if sc.get("mode") == "tickers" else ("หุ้นใน sector ที่เลือก" if sc.get("mode") == "sectors" else "หุ้นใน universe")
    if not f.get("universe"):
        return f"{who}ไม่มีราคาในช่วงเวลานี้ — พอร์ตว่างตลอดการทดลอง"
    for m, name in (("A", "A"), ("B", "B"), ("C", "C")):
        st = conf["stages"][m]
        filters = st["mode"] in ("on", "filter") if m == "A" else st["mode"] == "filter"  # B/C กรองได้เฉพาะ config เดิม
        if filters and not f.get(f"after_{m}"):
            return f"{who}ไม่ผ่านเกณฑ์ {name} ในช่วงเวลานี้ — กล่อง {name} กรองออกหมด พอร์ตจึงว่างตลอดการทดลอง"
    return "มีหุ้นผ่านทุกกล่อง แต่เงื่อนไข (condition) ไม่ได้ให้น้ำหนักหุ้นตัวใดเลย — พอร์ตว่างตลอดการทดลอง"


def _summary(d: Path, name: str, exp_id: str | None, saved_at: str | None) -> dict:
    conf, met, prov = _json(d / "config.json"), _json(d / "metrics.json"), _json(d / "provenance.json")
    eq = pd.read_parquet(d / "equity.parquet")
    step = max(1, len(eq) // 120)
    s = met["full"]["strategy"]
    return {
        "id": exp_id, "name": name, "saved_at": saved_at, "created_at": prov.get("created_at"),
        "start": conf["start"], "end": conf["end"],
        "metrics": {k: s.get(k) for k in ("total_return", "cagr", "sharpe", "max_dd", "n_trades", "win_rate")},
        "spy_total_return": met["full"]["spy"].get("total_return"),
        "ew_total_return": met["full"]["ew"].get("total_return"),
        "sparkline": [round(float(x), 2) for x in eq["strategy"].iloc[::step].tolist() + [eq["strategy"].iloc[-1]]],
        "chips": chips(conf, prov), "badges": badges(conf, prov),
        "held_out_touched": bool(prov.get("held_out_touched")),
    }


def save(run_dir: Path, name: str) -> str:
    run_dir = Path(run_dir)
    if not (run_dir / "metrics.json").exists():
        raise FileNotFoundError("run นี้ยังไม่เสร็จหรือไม่มีผล")
    now = datetime.now()
    exp_id = f"{now:%Y%m%d-%H%M%S}_{_slug(name)}"
    d = ROOT / exp_id
    d.mkdir(parents=True, exist_ok=False)
    for f in ARTIFACTS:
        shutil.copy2(run_dir / f, d / f)
    conf = _json(d / "config.json")
    conf["name"] = (name or "").strip()[:120] or conf.get("name") or exp_id
    (d / "config.json").write_text(json.dumps(conf, ensure_ascii=False, indent=1))
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summ = _summary(d, conf["name"], exp_id, saved_at)
    summ["source_run"] = run_dir.name
    (d / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1))
    return exp_id


def list_all() -> list:
    if not ROOT.exists():
        return []
    out = []
    for d in sorted(ROOT.iterdir(), reverse=True):
        if (d / "summary.json").exists():
            s = _json(d / "summary.json")
            s["has_artifacts"] = (d / "equity.parquet").exists()
            out.append(s)
    return out


def _records(df: pd.DataFrame) -> list:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
    recs = df.to_dict("records")
    for r in recs:
        for k, v in r.items():
            if isinstance(v, np.ndarray):
                r[k] = v.tolist()
            elif isinstance(v, float) and not np.isfinite(v):
                r[k] = None
    return recs


def load_dir(d: Path, exp_id: str | None = None) -> dict:
    """ผลเต็ม (ไม่รวม trades — ใช้ trades() แยกเพราะอาจเป็นหมื่นแถว)"""
    from sandbox.v2 import prices

    conf, met, prov = _json(d / "config.json"), _json(d / "metrics.json"), _json(d / "provenance.json")
    src = (d / "condition_snapshot.py").read_text(encoding="utf-8")
    out = {"id": exp_id, "config": conf, "metrics": met, "provenance": prov, "condition_source": src,
           "badges": badges(conf, prov), "chips": chips(conf, prov), "has_artifacts": (d / "equity.parquet").exists(),
           "empty_reason": empty_reason(conf, met), "legacy_notes": _legacy(conf)}
    if not out["has_artifacts"]:
        return out
    eq = pd.read_parquet(d / "equity.parquet")
    for c in ("strategy", "spy", "ew"):
        eq[f"dd_{c}"] = eq[c] / eq[c].cummax() - 1
    out["equity"] = _records(eq)
    fun = pd.read_parquet(d / "funnel.parquet")
    out["funnel"] = _records(fun.drop(columns=[c for c in ("a_rebalance",) if c in fun]))
    pos = pd.read_parquet(d / "positions.parquet")
    if len(pos):
        pos["sector"] = pos["ticker"].map(prices.sector_of)
        sec = pos.groupby(["date", "sector"])["weight"].sum().unstack(fill_value=0.0)
        out["sector_exposure"] = {"dates": [str(x.date()) for x in sec.index], "series": {k: sec[k].round(5).tolist() for k in sec}}
        last = pos[pos["date"] == pos["date"].max()].sort_values("weight", ascending=False)
        out["holdings_last"] = _records(last)
    else:
        out["sector_exposure"], out["holdings_last"] = {"dates": [], "series": {}}, []
    rt = json.loads((d / "round_trips.json").read_text()) if (d / "round_trips.json").exists() else []
    by = {}
    for r in rt:
        by[r["ticker"]] = by.get(r["ticker"], 0.0) + r["pnl"]
    ranked = sorted(by.items(), key=lambda x: x[1])
    out["winners"] = [{"ticker": t, "pnl": p} for t, p in ranked[::-1][:10] if p > 0]
    out["losers"] = [{"ticker": t, "pnl": p} for t, p in ranked[:10] if p < 0]
    tr = pd.read_parquet(d / "trades.parquet", columns=["ticker"])
    out["n_trades"] = int(len(tr))
    out["traded_tickers"] = sorted(tr["ticker"].unique().tolist())
    return out


def trades(d: Path, q: str = "", side: str = "", ticker: str = "", offset: int = 0, limit: int = 200) -> dict:
    tr = pd.read_parquet(d / "trades.parquet")
    if ticker:
        tr = tr[tr["ticker"] == ticker.upper()]
    if side in ("buy", "sell"):
        tr = tr[tr["side"] == side]
    if q:
        ql = q.lower()
        mask = tr["ticker"].str.lower().str.contains(ql, regex=False) | tr["reasons"].map(
            lambda rs: any(ql in str(x).lower() for x in rs))
        tr = tr[mask]
    total = len(tr)
    tr = tr.sort_values(["date", "ticker"], ascending=[False, True]).iloc[offset:offset + limit]
    return {"total": total, "offset": offset, "rows": _records(tr)}


def load(exp_id) -> dict:
    d = _dir(exp_id)
    out = load_dir(d, exp_id)
    s = _json(d / "summary.json")
    out["name"], out["saved_at"] = s["name"], s["saved_at"]
    return out


def path(exp_id) -> Path:
    return _dir(exp_id)


def delete(exp_id, confirm: str):
    d = _dir(exp_id)
    if confirm != exp_id:
        raise PermissionError("ต้องยืนยันด้วย exp_id ให้ตรงก่อนลบ")
    shutil.rmtree(d)


def bundle(exp_id) -> bytes:
    d = _dir(exp_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(d.iterdir()):
            z.write(f, f"{exp_id}/{f.name}")
    return buf.getvalue()


def _flatten(x, pre=""):
    out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            out.update(_flatten(v, f"{pre}.{k}" if pre else str(k)))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            out.update(_flatten(v, f"{pre}[{i}]"))
    else:
        out[pre] = x
    return out


def diff_runs(saved_dir: Path, new_dir: Path) -> dict:
    """เทียบ metrics.json + equity ของผลที่บันทึกกับการรันซ้ำ — บอกสาเหตุที่เป็นไปได้ถ้าต่าง"""
    a, b = _flatten(_json(saved_dir / "metrics.json")), _flatten(_json(new_dir / "metrics.json"))
    diffs = [{"key": k, "saved": a.get(k), "rerun": b.get(k)} for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    eq_same = None
    if (saved_dir / "equity.parquet").exists():
        ea, eb = pd.read_parquet(saved_dir / "equity.parquet"), pd.read_parquet(new_dir / "equity.parquet")
        eq_same = ea.equals(eb)
    pa, pb = _json(saved_dir / "provenance.json"), _json(new_dir / "provenance.json")
    causes = []
    if pa.get("data_hash") != pb.get("data_hash"):
        causes.append("data_hash ต่าง — ข้อมูลราคาเปลี่ยน (เช่น รัน update_prices ใหม่ แล้ว Yahoo ปรับ Adj Close ย้อนหลังจากปันผล)")
    if (pa.get("git") or {}).get("commit") != (pb.get("git") or {}).get("commit"):
        causes.append(f"git commit ต่าง ({str((pa.get('git') or {}).get('commit'))[:8]} → {str((pb.get('git') or {}).get('commit'))[:8]}) — โค้ด engine/โมเดลอาจเปลี่ยน")
    if (pb.get("git") or {}).get("dirty"):
        causes.append("working tree มีไฟล์ที่ยังไม่ commit ตอนรันซ้ำ")
    for m in set(pa.get("versions") or {}) | set(pb.get("versions") or {}):
        va, vb = (pa.get("versions") or {}).get(m, {}), (pb.get("versions") or {}).get(m, {})
        if va.get("created_at") != vb.get("created_at"):
            causes.append(f"signal ของ {m} ถูกสร้างใหม่ ({va.get('created_at')} → {vb.get('created_at')})")
    if pa.get("condition_sha256") != pb.get("condition_sha256"):
        causes.append("ข้อความเงื่อนไขต่างจาก snapshot (ไม่ควรเกิด — แจ้งบั๊ก)")
    return {"identical": not diffs and eq_same is not False, "n_diffs": len(diffs), "diffs": diffs[:200],
            "equity_identical": eq_same, "possible_causes": causes,
            "saved_data_hash": pa.get("data_hash"), "rerun_data_hash": pb.get("data_hash")}


def compare(ids: list) -> dict:
    out = []
    for i in ids[:3]:
        d = _dir(i)
        s = _json(d / "summary.json")
        met = _json(d / "metrics.json")
        eq = pd.read_parquet(d / "equity.parquet") if (d / "equity.parquet").exists() else None
        out.append({"id": i, "name": s["name"], "chips": s["chips"], "badges": s["badges"],
                    "metrics": met["full"]["strategy"], "spy": met["full"]["spy"], "ew": met["full"]["ew"],
                    "equity": None if eq is None else {"dates": eq["date"].dt.strftime("%Y-%m-%d").tolist(),
                                                       "values": (eq["strategy"] / eq["strategy"].iloc[0]).round(6).tolist()}})
    return {"experiments": out}
