"""M2: โหมดทดสอบ "Top-N คงที่ภายใน scope" — N ตัวบนสุดตาม score เดิมเฉพาะหุ้น applicable ใน scope (ไม่พอ = เท่าที่มี)"""
import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, experiments_store as xs, registry
from sandbox.v2.signals import AsOf

BMFW = "A:bmf20-weighted"  # กฎ BM60/Fscore40 top-20 (trial 127 ของ Model A — round 013)
FIXED_WARN = ("โหมดทดสอบ: บังคับจำนวนหุ้นตายตัวภายในขอบเขตที่เลือก — ไม่ใช่พฤติกรรมจริงของกฎที่ผ่านการทดสอบ "
              "ผลจากโหมดนี้ใช้ดูกลไกระบบเท่านั้น ห้ามอ้างเป็นผลการทดสอบของ Model A")
XLK = {"mode": "sectors", "sectors": ["XLK"], "tickers": []}


def _body(n, scope, version=BMFW, **kw):
    a = {"mode": "on", "version": version, "ranking": "scoped_fixed_n"}
    if n is not None:
        a["n"] = n
    return dict({"stages": {"A": a}, "scope": scope, "condition": {"id": "equal_weight_A"}}, **kw)


def test_xlk_top20_exactly(tmp_path):
    conf, w = engine.normalize_config(_body(20, XLK))
    assert conf["stages"]["A"] == {"mode": "on", "version": BMFW, "ranking": "scoped_fixed_n", "n": 20}
    assert any(FIXED_WARN in x for x in w)
    engine.run(conf, tmp_path / "r", log=lambda m: None)
    res = xs.load_dir(tmp_path / "r")
    members = set(engine.scope_members(XLK))
    sig = registry.signals(BMFW)
    for R in ("2021-06-30", "2022-06-30"):
        g = sig[(pd.to_datetime(sig["date"]) == pd.Timestamp(R)) & sig["applicable"] & sig["ticker"].isin(members)]
        want = g.sort_values(["score", "ticker"], ascending=[False, True])["ticker"].tolist()[:20]
        assert len(g) >= 20
        picks, info = engine.scoped_select(AsOf(BMFW).snapshot(pd.Timestamp(R)), members, 20)
        assert picks == want and info["k"] == 20
    prov = res["provenance"]
    assert prov["a_ranking_mode"] == "scoped_fixed_n"
    assert prov["a_ranking_n"]["requested"] == 20 and set(prov["a_ranking_n"]["per_rebalance"].values()) == {20}
    assert res["badges"][0] == {"kind": "scoped_fixed_n", "text": "A โหมดทดสอบ (Top-N คงที่ N=20)"}
    f = pd.DataFrame(res["funnel"])
    assert f["after_A"].max() <= 20 and f["after_A"].median() == 20  # วันที่หุ้นบางตัวไม่มีราคาอาจน้อยกว่า 20
    tr = xs.trades(tmp_path / "r", limit=3)["rows"]
    assert any("โหมดทดสอบ Top-N คงที่ อันดับ" in c for c in tr[0]["reasons"])


def test_n_larger_than_scope_takes_all_applicable():
    R = pd.Timestamp("2022-06-30")
    snap = AsOf(BMFW).snapshot(R)
    appl = sorted(k for k, r in snap.items() if r["applicable"])[:10]
    na = sorted(k for k, r in snap.items() if not r["applicable"])[:3]
    picks, info = engine.scoped_select(snap, set(appl) | set(na), 100)
    assert sorted(picks) == appl and info["k"] == 10  # ได้ 10 ไม่ error ไม่ปัดเพิ่ม · applicable False ไม่ถูกนับ
    conf, _ = engine.normalize_config(_body(100, {"mode": "tickers", "tickers": appl}))
    assert conf["stages"]["A"]["n"] == 100


def test_default_n_is_rules_real_count_and_validation():
    assert engine.default_fixed_n(BMFW) == 20
    assert engine.default_fixed_n("A:A1_r001_Q_LOWACC_overall") == round(registry.get("A:A1_r001_Q_LOWACC_overall")["coverage"]["avg_selected"])
    conf, _ = engine.normalize_config(_body(None, XLK))
    assert conf["stages"]["A"]["n"] == 20
    for bad in (0, -3, "abc", 99999):
        with pytest.raises(engine.ConfigError):
            engine.normalize_config(_body(bad, XLK))
    conf, _ = engine.normalize_config({"stages": {"A": {"mode": "on", "version": BMFW}}, "condition": {"id": "equal_weight_A"}})
    assert "ranking" not in conf["stages"]["A"] and "n" not in conf["stages"]["A"]  # ไม่ใช่ค่าเริ่มต้น


def test_warning_texts_in_ui():
    js = (cfg.V2 / "static" / "app.js").read_text(encoding="utf-8")
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    assert engine.FIXED_N_WARNING == FIXED_WARN and FIXED_WARN in js
    for x in ('value="scoped_fixed_n"', 'id="a-fixed-n"', "rankingWarning(stages.A.ranking)", "scopedText()", "rankingWarning(d.a_ranking)"):
        assert x in html, x
