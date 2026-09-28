"""G1: กล่อง A/B/C = เปิด/ปิด + version เท่านั้น — เกณฑ์กรองทั้งหมดย้ายไป condition
- ไม่มี field เกณฑ์กรองเหลือในหน้าเว็บ / config / API
- A เปิด = class selected + applicable ของ version ตรง ๆ · B/C ไม่ตัดหุ้น · ไม่มีข่าว = applicable False
- template exclude_negative_B / a_score_threshold ให้ผลตรงตามชื่อ
- config เก่า (กรองในกล่อง) เปิดดูได้, Re-run ต้องยืนยัน"""
import json
import re
import shutil

import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, experiments_store as xs, prices, registry
from sandbox.v2.server import create_app
from sandbox.v2.signals import AsOf

A1 = "A:A1_r001_Q_LOWACC_overall"
REMOVED = ["onlySelected", "minScore", "exNeg", "exNeu", "เฉพาะที่กฎเลือก", "ตัด negative", "ตัด neutral", "ไม่มีสัญญาณ →",
           "score ≥ <input", "'score-only'", "criteria", "exclude_classes", "min_score", "class_in"]


@pytest.fixture()
def client():
    return create_app().test_client()


def test_web_page_has_no_box_filter_fields():
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    js = (cfg.V2 / "static" / "pipeline.js").read_text(encoding="utf-8")
    for w in REMOVED:
        assert w not in html, w
        assert w not in js, w
    assert "x-for=\"mode in ['off','on']\"" in html  # กล่อง A/B/C มีแค่ ปิด/เปิด


def test_config_and_api_have_no_filter_fields(client):
    conf, _ = engine.normalize_config({"stages": {"A": {"mode": "on", "version": A1}, "B": {"mode": "on", "version": "B:stub"},
                                                  "C": {"mode": "on", "version": "C:rulebase-exp03"}}, "condition": {"id": "equal_weight_A"}})
    assert all(set(v) == {"mode", "version"} for v in conf["stages"].values())
    r = client.post("/api/preflight", json={"stages": {"A": {"mode": "on", "version": A1}, "B": {"mode": "on", "version": "B:stub"}},
                                            "condition": {"id": "equal_weight_A"}})
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    for w in ("criteria", "exclude_classes", "min_score", "class_in", "missing"):
        assert f'"{w}"' not in text, w
    reg = client.get("/api/registry").get_data(as_text=True)
    assert '"criteria"' not in reg


def test_box_stats_A_pass_is_selected_and_applicable(client):
    j = client.post("/api/preflight", json={"stages": {"A": {"mode": "on", "version": A1}, "B": {"mode": "on", "version": "B:stub"},
                                                       "C": {"mode": "on", "version": "C:rulebase-exp03"}},
                                            "condition": {"id": "equal_weight_A"}}).get_json()
    st = j["box_stats"]
    t = pd.Timestamp(st["date"])
    s = registry.signals(A1)
    R = max(d for d in s["date"].unique() if pd.Timestamp(d) <= t)
    adj = prices.load("adj", None, t, t).iloc[-1]
    sel = s[(s["date"] == R) & (s["class"] == "selected") & (s["applicable"])]["ticker"]
    want = sum(1 for k in sel if k in adj.index and pd.notna(adj[k]) and k in set(prices.available_tickers("stock")))
    assert st["A"]["pass"] == want > 0 and st["A"]["rebalance"] == str(pd.Timestamp(R).date())
    # B/C ไม่กรอง → ผ่านเท่ากับ A; การกระจายรวมกัน = จำนวนที่ผ่าน
    assert st["B"]["pass"] == st["C"]["pass"] == want
    assert sum(st["B"]["dist"].values()) == want and sum(st["C"]["dist"].values()) == want
    assert set(st["B"]["dist"]) == {"positive", "neutral", "negative", "none"}


def test_B_and_C_never_drop_stocks_and_missing_is_not_applicable(tmp_path):
    src = '''NAME = "t"
DESCRIPTION = "t"
def decide(ctx):
    for t in ctx.universe:
        b = ctx.b[t]  # ทุกตัวที่รอดจาก A ต้องมี record ของ B (ไม่มีข่าว = applicable False)
        if not b["applicable"]:
            assert b["score"] is None and b["class"] is None, b
        else:
            assert -2 <= b["score"] <= 2, b
    return None
'''
    conf, _ = engine.normalize_config({"start": "2022-01-03", "end": "2022-03-31",
                                       "stages": {"A": {"mode": "on", "version": A1}, "B": {"mode": "on", "version": "B:stub"},
                                                  "C": {"mode": "on", "version": "C:rulebase-exp03"}}, "condition": {"source": src}})
    engine.run(conf, tmp_path / "r", log=lambda m: None)
    f = pd.read_parquet(tmp_path / "r" / "funnel.parquet")
    assert (f["after_A"] == f["after_B"]).all() and (f["after_B"] == f["after_C"]).all() and f["after_A"].min() > 0


def _run(tmp_path, cid, stages, start="2021-09-27", end="2023-06-30"):
    conf, _ = engine.normalize_config({"start": start, "end": end, "stages": stages, "condition": {"id": cid}})
    engine.run(conf, tmp_path / cid, log=lambda m: None)
    return pd.read_parquet(tmp_path / cid / "trades.parquet"), pd.read_parquet(tmp_path / cid / "funnel.parquet")


def test_template_exclude_negative_B(tmp_path):
    tr, _ = _run(tmp_path, "exclude_negative_B", {"A": {"mode": "on", "version": A1}, "B": {"mode": "on", "version": "B:stub"}})
    b = AsOf("B:stub")
    buys = tr[tr["side"] == "buy"]
    assert len(buys) > 50
    for _, r in buys.iterrows():  # ซื้อได้เฉพาะตัวที่ ณ วันตัดสินใจ ไม่มีข่าว หรือข่าว score ≥ 0
        rec = b.at(r["ticker"], pd.Timestamp(r["decision_date"]))
        assert rec is None or rec["score"] >= 0, (r["ticker"], r["decision_date"], rec)
    sells_neg = [x for rs in tr["reasons"] for x in rs if "< 0 → ไม่ถือ" in x]
    assert sells_neg  # มีการตัดจริง (ขายตัวที่ข่าวติดลบ)


def test_template_a_score_threshold(tmp_path):
    tr, _ = _run(tmp_path, "a_score_threshold", {"A": {"mode": "on", "version": A1}})
    a = AsOf(A1)
    buys = tr[tr["side"] == "buy"]
    assert len(buys) > 0
    for _, r in buys.iterrows():
        rec = a.at(r["ticker"], pd.Timestamp(r["decision_date"]))
        assert rec["class"] == "selected" and rec["score"] >= 90.0, (r["ticker"], rec)
    ew, _ = _run(tmp_path, "equal_weight_A", {"A": {"mode": "on", "version": A1}})
    assert tr["ticker"].nunique() < ew["ticker"].nunique()  # คัดเข้มกว่าถือทุกตัวที่ A เลือก


@pytest.mark.parametrize("stages, legacy, modes", [
    ({"A": {"mode": "filter", "version": A1, "criteria": {"class_in": ["selected"], "min_score": None}}}, False, "on"),
    ({"A": {"mode": "filter", "version": A1}, "B": {"mode": "score-only", "version": "B:stub", "criteria": {"exclude_classes": ["negative"]}}}, False, "on"),
    ({"A": {"mode": "filter", "version": A1, "criteria": {"min_score": 50}}}, True, "on"),
    ({"A": {"mode": "score-only", "version": A1}}, True, "off"),
    ({"A": {"mode": "filter", "version": A1}, "B": {"mode": "filter", "version": "B:stub"}}, True, "on"),
])
def test_legacy_configs(stages, legacy, modes):
    body = {"stages": stages, "condition": {"id": "equal_weight_A"}}
    if legacy:
        with pytest.raises(engine.LegacyConfigError) as e:
            engine.normalize_config(body)
        assert e.value.notes
        conf, w = engine.normalize_config(body, allow_legacy=True)
        assert conf["legacy_migration"] == e.value.notes and any(x.startswith("LEGACY") for x in w)
    else:
        conf, _ = engine.normalize_config(body)
        assert "legacy_migration" not in conf
    assert conf["stages"]["A"]["mode"] == modes
    assert all(set(v) == {"mode", "version"} for v in conf["stages"].values())


def test_every_saved_experiment_still_loads():
    """ผลที่บันทึกไว้จริงในเครื่อง (ถ้ามี) เปิดได้ไม่ error — กราฟ/metrics มาจากไฟล์ ไม่ขึ้นกับ UI"""
    items = xs.list_all()
    for e in items:
        d = xs.load(e["id"])
        assert d["metrics"] and "legacy_notes" in d


def _legacy_exp(tmp_path, monkeypatch):
    """สร้างผลการทดลองแบบเดิม (กล่อง B กรอง negative) จากการรันจริงแล้วเขียน config ตามรูปแบบก่อน G1"""
    conf, _ = engine.normalize_config({"start": "2022-01-03", "end": "2022-06-30", "condition": {"id": "equal_weight_A"},
                                       "stages": {"A": {"mode": "on", "version": A1}, "B": {"mode": "on", "version": "B:stub"}}})
    root = tmp_path / "exps"
    d = root / "20260101-000000_legacy-b-filter"
    engine.run(conf, d, log=lambda m: None)
    c = json.loads((d / "config.json").read_text())
    c["stages"] = {"A": {"mode": "filter", "version": A1, "criteria": {"class_in": ["selected"], "min_score": None}},
                   "B": {"mode": "filter", "version": "B:stub", "criteria": {"exclude_classes": ["negative"], "min_score": None, "missing": "pass"}},
                   "C": {"mode": "off", "version": None, "criteria": {"exclude_classes": ["negative"], "min_score": None, "missing": "pass"}}}
    (d / "config.json").write_text(json.dumps(c))
    (d / "summary.json").write_text(json.dumps(xs._summary(d, "legacy", d.name, "2026-01-01T00:00:00")))
    monkeypatch.setattr(xs, "ROOT", root)
    return d.name


def test_legacy_experiment_opens_read_only_and_rerun_needs_confirmation(tmp_path, monkeypatch, client):
    exp = _legacy_exp(tmp_path, monkeypatch)
    r = client.get(f"/api/results/exp/{exp}")
    assert r.status_code == 200
    d = r.get_json()
    assert d["has_artifacts"] and d["metrics"]["full"] and len(d["equity"]) > 50
    assert any("B: เดิมกรองในกล่อง" in n for n in d["legacy_notes"])
    assert "B-stub (กรองในกล่อง·เดิม)" in d["chips"]
    r = client.post(f"/api/experiments/{exp}/rerun")
    assert r.status_code == 409 and r.get_json()["kind"] == "legacy" and r.get_json()["notes"]


def test_stub_badge_has_tooltip():
    js = (cfg.V2 / "static" / "app.js").read_text(encoding="utf-8")
    assert "STUB = ยังไม่มีผลวิเคราะห์จริง ระบบสุ่มค่าเพื่อทดสอบว่า pipeline เดินได้ครบเท่านั้น ห้ามใช้ตัดสินใจลงทุนจริง" in js
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    # ทุก badge ของ version/ผลลัพธ์ที่ render แบบ dynamic มี title (tooltip)
    dyn = re.findall(r'<span class="badge[^"]*"[^>]*:class="(?:b\.kind|v\.result_badge|vmeta\(m\)\.result_badge)"[^>]*>', html)
    assert dyn and all(":title=" in x for x in dyn), dyn
