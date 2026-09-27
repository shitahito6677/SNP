"""
สร้าง signal ของ STUB (A/B/C) แบบ deterministic จาก sha256 → sandbox/v2/stubs/<model>/stub/{manifest.json, signals.parquet}
ไม่ใช่โมเดล — มีไว้ทดสอบระบบเท่านั้น (badge STUB เสมอ)

    python3 -m sandbox.v2.scripts.build_stubs
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

from sandbox.v2 import config as cfg
from sandbox.v2 import prices


def seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16)


def full_calendar() -> pd.DatetimeIndex:
    return pd.read_parquet(cfg.PRICES_DIR / f"{cfg.BENCHMARK}.parquet").index


def write(model: str, df: pd.DataFrame, manifest: dict) -> None:
    d = cfg.STUB_EXPORT_ROOT / model / "stub"
    d.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["date", df.columns[1]]).reset_index(drop=True)
    df.to_parquet(d / "signals.parquet", index=False)
    base = {"model": model, "version": "stub", "short_label": f"{model}-stub", "is_stub": True, "result_badge": "stub",
            "signal_files": ["signals.parquet"], "source_experiment": "none — deterministic sha256 stub",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "warnings": ["STUB: สุ่มแบบ deterministic ไม่ใช่โมเดล — ผลใด ๆ ที่ได้ไม่มีความหมายทางการลงทุน"]}
    base.update(manifest)
    base["coverage"] = {"start": str(df["date"].min().date()), "end": str(df["date"].max().date()),
                        **base.get("coverage", {})}
    (d / "manifest.json").write_text(json.dumps(base, ensure_ascii=False, indent=1))
    print(model, "stub:", len(df), "แถว", base["coverage"]["start"], "→", base["coverage"]["end"])


def build_a(cal, tickers):
    june = cal[cal.month == 6]
    dates = list(june.to_series().groupby(june.year).max())
    if cal[0].month > 6:  # ให้ช่วงแรกของราคามีสัญญาณด้วย (รอบ มิ.ย. ก่อนวันแรกของข้อมูลราคา)
        dates.insert(0, pd.Timestamp(f"{cal[0].year}-06-30"))
    rows = []
    for R in dates:
        ds = str(R.date())
        sel = [t for t in tickers if seed("A", t, ds) % 5 == 0]
        for t in tickers:
            sc = seed("A", t, ds)
            is_sel = t in sel
            rows.append({"date": R, "ticker": t, "class": "selected" if is_sel else "not_selected",
                         "score": round((sc // 7) % 10000 / 100, 2), "applicable": True,
                         "weight": 1 / len(sel) if is_sel else 0.0,
                         "reasons": [f"A stub: sha256({t}|{ds}) → {'selected' if is_sel else 'not selected'}"],
                         "model_version": "stub", "is_stub": True})
    write("A", pd.DataFrame(rows), {
        "display_name": "A stub (sha256 · รายปี มิ.ย.)", "rule_id": "stub", "key": "ticker", "rebalance": "annual_june",
        "classes": ["selected", "not_selected", "not_applicable"], "score_meaning": "สุ่ม 0–100",
        "coverage": {"n_tickers": len(tickers)}, "notes": "เลือก ~20% ต่อรอบแบบสุ่ม deterministic"})


def build_b(cal, tickers):
    rows = []
    classes = ["positive", "neutral", "negative"]
    for t in tickers:
        for d in cal:
            ds = str(d.date())
            sc = seed("B", t, ds)
            if sc % 15:
                continue
            c = classes[(sc // 15) % 3]
            rows.append({"date": d, "ticker": t, "class": c, "score": round(0.34 + 0.66 * ((sc // 45) % 1000) / 1000, 4),
                         "applicable": True, "reasons": [f"B stub: ข่าวสมมติ {ds} → {c}"],
                         "model_version": "stub", "is_stub": True})
    write("B", pd.DataFrame(rows), {
        "display_name": "B stub (ข่าวสมมติ ~1.4 ครั้ง/เดือน/หุ้น)", "rule_id": "stub", "key": "ticker", "rebalance": "event",
        "asof": {"max_age_days": 10}, "classes": classes, "score_meaning": "confidence สุ่ม [0.34, 1]",
        "coverage": {"n_tickers": len(tickers)}, "notes": "signal หมดอายุหลัง 10 วัน (ไม่มีข่าว = ไม่มีสัญญาณ)"})


def build_c(cal):
    rows = []
    classes = ["positive", "neutral", "negative"]
    etfs = list(cfg.SECTOR_ETFS.values())
    for d in cal:
        ds = str(d.date())
        if seed("C-event", ds) % 20:
            continue
        for e in etfs:
            sc = seed("C", e, ds)
            c = classes[sc % 3]
            rows.append({"date": d, "sector": e, "class": c, "score": round(((sc // 3) % 2001 - 1000) / 1000, 3),
                         "applicable": True, "reasons": [f"C stub: เหตุการณ์มหภาคสมมติ {ds} → {e} {c}"],
                         "model_version": "stub", "is_stub": True})
    write("C", pd.DataFrame(rows), {
        "display_name": "C stub (เหตุการณ์มหภาคสมมติ ~1 ครั้ง/เดือน)", "rule_id": "stub", "key": "sector",
        "rebalance": "event", "asof": {"max_age_days": 60}, "classes": classes, "score_meaning": "สุ่ม [-1, 1]",
        "coverage": {"n_sectors": len(etfs), "sectors": etfs}, "notes": "ใช้ได้จนถึงเหตุการณ์ถัดไป (สูงสุด 60 วัน)"})


def main():
    cal = full_calendar()
    tickers = prices.available_tickers("stock")
    build_a(cal, tickers)
    build_b(cal, tickers)
    build_c(cal)


if __name__ == "__main__":
    main()
