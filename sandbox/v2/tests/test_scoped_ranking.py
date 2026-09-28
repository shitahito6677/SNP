"""L2: โหมดทดสอบ "จัดอันดับ A ใหม่เฉพาะใน scope" — แยกจากโหมดจริง (global) เด็ดขาด, คงสัดส่วนเดิมของกฎ, เตือนทุกจุด"""
import json

import numpy as np
import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, experiments_store as xs, prices, registry
from sandbox.v2.signals import AsOf

A1, BMF = "A:A1_r001_Q_LOWACC_overall", "A:bmf20-funnel"
WARN = ("โหมดทดสอบ: จัดอันดับใหม่เฉพาะในขอบเขตที่เลือก — ไม่ใช่พฤติกรรมจริงของกฎที่ผ่านการทดสอบ (backtest เดิมของ Model A "
        "ทดสอบด้วยการจัดอันดับทั้งตลาดเท่านั้น) ผลจากโหมดนี้ใช้ดูกลไกระบบเท่านั้น ห้ามอ้างเป็นผลการทดสอบของ Model A")


def _body(version, ranking, scope, **kw):
    a = {"mode": "on", "version": version}
    if ranking:
        a["ranking"] = ranking
    return dict({"stages": {"A": a}, "scope": scope, "condition": {"id": "equal_weight_A"}}, **kw)


def _run(tmp_path, name, body):
    conf, w = engine.normalize_config(body)
    engine.run(conf, tmp_path / name, log=lambda m: None)
    return conf, w, xs.load_dir(tmp_path / name)


def test_single_stock_scope_buys_in_scoped_mode_only(tmp_path):
    """META ไม่ถูก A1 เลือกในรอบ 2021-06-30 → ทั้งตลาดได้ 0 ตลอดรอบ, โหมดทดสอบได้ 1 เสมอ"""
    meta = {"mode": "tickers", "tickers": ["META"]}
    per = dict(start=cfg.DECISION_START, end="2022-06-29")
    _, wg, g = _run(tmp_path, "global", _body(A1, None, meta, **per))
    _, ws, s = _run(tmp_path, "scoped", _body(A1, "scoped", meta, **per))
    fg, fs = pd.DataFrame(g["funnel"]), pd.DataFrame(s["funnel"])
    assert fg["after_A"].max() == 0 and fs["after_A"].min() == 1
    assert g["n_trades"] == 0 and s["n_trades"] >= 1 and s["traded_tickers"] == ["META"]
    assert g["provenance"]["a_ranking_mode"] == "global" and s["provenance"]["a_ranking_mode"] == "scoped"
    assert not any(b["kind"] == "scoped_a" for b in g["badges"]) and s["badges"][0]["kind"] == "scoped_a"
    assert not any(WARN in x for x in wg) and any(WARN in x for x in ws)
    assert "ranking" not in g["config"]["stages"]["A"] and s["config"]["stages"]["A"]["ranking"] == "scoped"
    tr = json.loads(json.dumps(xs.trades(tmp_path / "scoped", limit=5)))
    assert any("โหมดทดสอบ อันดับ 1/1" in c for c in tr["rows"][0]["reasons"])  # trade reasons บอกว่ามาจากโหมดทดสอบ


def test_sector_scope_keeps_rule_fraction():
    """XLK + bmf20 (กฎเลือก 20 จาก ~344 ที่จัดอันดับ ≈ 5.8%) → เลือก round(จำนวน applicable ใน XLK × สัดส่วน) ตัวที่ score สูงสุด"""
    xlk = set(engine.scope_members({"mode": "sectors", "sectors": ["XLK"], "tickers": []}))
    sig = registry.signals(BMF)
    a = AsOf(BMF)
    for R in ("2021-06-30", "2022-06-30"):
        g = sig[pd.to_datetime(sig["date"]) == pd.Timestamp(R)]
        appl = g[g["applicable"]]
        frac = (appl["class"] == "selected").sum() / len(appl)
        mine = appl[appl["ticker"].isin(xlk)].sort_values(["score", "ticker"], ascending=[False, True])
        k = max(1, int(np.floor(len(mine) * frac + 0.5)))
        picks, info = engine.scoped_select(a.snapshot(pd.Timestamp(R)), xlk)
        assert info["k"] == k and picks == mine["ticker"].tolist()[:k], (R, info, k)
        assert 2 <= k <= 4 and k != 20  # ≈ 3 ตัว (สัดส่วนเดิม) ไม่ใช่ยก 20 ตัวมาทั้งดุ้น
        print(R, f"XLK applicable {len(mine)} × {frac:.4f} = {len(mine) * frac:.2f} → {k}: {picks}")


def test_scoped_over_whole_market_equals_global():
    t = pd.Timestamp("2021-12-01")
    adj = prices.load("adj", None, t, t)
    stocks = [x for x in prices.available_tickers("stock") if x in adj.columns]
    sec = {x: prices.sector_of(x) for x in stocks}
    for v in (A1, BMF):
        a = {"A": AsOf(v)}
        g = engine.stage_day(t, adj.iloc[-1], stocks, [], a, {"A": {"mode": "on", "version": v}}, sec)[0]
        s = engine.stage_day(t, adj.iloc[-1], stocks, [], a, {"A": {"mode": "on", "version": v, "ranking": "scoped"}}, sec)[0]
        assert g == s and g


def test_not_applicable_is_always_excluded():
    R = pd.Timestamp("2021-06-30")
    snap = AsOf(A1).snapshot(R)
    na = sorted(k for k, r in snap.items() if not r["applicable"])[:3]
    assert na
    picks, info = engine.scoped_select(snap, set(na))
    assert picks == [] and info["k"] == 0  # scope มีแต่ applicable False → ไม่เลือกใครเลย (ไม่บังคับ 1)
    ok = sorted(k for k, r in snap.items() if r["applicable"])[:1]
    picks, _ = engine.scoped_select(snap, set(na) | set(ok))
    assert picks == ok


def test_config_validation_and_default_is_global():
    conf, _ = engine.normalize_config(_body(A1, None, None))
    assert "ranking" not in conf["stages"]["A"]  # ค่าเริ่มต้น = ทั้งตลาด, config เหมือนเดิมทุกตัวอักษร
    with pytest.raises(engine.ConfigError):
        engine.normalize_config(_body(A1, "weird", None))
    conf, w = engine.normalize_config(_body("A:A3_r004_Q_LOWACC_overall_BUFFER", "scoped", None))
    assert any("BUFFER" in x for x in w)


def test_warning_everywhere_in_ui():
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    js = (cfg.V2 / "static" / "app.js").read_text(encoding="utf-8")
    assert WARN in js and engine.SCOPED_A_WARNING == WARN
    for x in ('id="a-ranking"', 'id="scoped-banner-pipeline"', 'id="scoped-banner-results"', 'id="scoped-banner-stock"', "sticky-banner"):
        assert x in html, x
