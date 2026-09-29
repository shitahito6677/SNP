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


# ------------------------------------------------------------------ N2 regression (จากสาเหตุจริงที่พบใน N0)

def test_regression_scope_entirely_outside_global_selection(tmp_path):
    """รอบ 2021-06-30: bmf20 ทั้งตลาดเลือกหุ้น XLK 0 ตัว → Top-N 20 ใน XLK ต้องได้ 20 ตัวทุกวันของรอบนั้น"""
    sig = registry.signals(BMFW)
    mem = set(engine.scope_members(XLK))
    g = sig[(pd.to_datetime(sig["date"]) == pd.Timestamp("2021-06-30")) & sig["ticker"].isin(mem)]
    assert int((g["class"] == "selected").sum()) == 0 and int(g["applicable"].sum()) >= 20
    for ranking, want in ((None, 0), ("scoped_fixed_n", 20)):
        a = {"mode": "on", "version": BMFW, **({"ranking": ranking, "n": 20} if ranking else {})}
        conf, _ = engine.normalize_config({"start": "2021-06-30", "end": "2022-06-29", "stages": {"A": a}, "scope": XLK,
                                           "condition": {"id": "equal_weight_A"}})
        engine.run(conf, tmp_path / str(ranking), log=lambda m: None)
        f = pd.read_parquet(tmp_path / str(ranking) / "funnel.parquet")
        assert set(f["after_A"]) == {want}, (ranking, f["after_A"].value_counts().to_dict())


def test_regression_picks_ignore_global_class():
    """ทุกตัวใน scope มีคะแนนต่ำกว่า cutoff ของทั้งตลาด (กฎเลือก top 4%) → ยังได้ N ตัวดีที่สุดใน scope; เปลี่ยน class ทั้งหมดแบบสุ่มแล้วผลต้องเหมือนเดิม"""
    import random
    snap = {f"T{i:03d}": {"score": 100 - i, "applicable": True, "class": "selected" if i < 4 else "not_selected"} for i in range(100)}
    snap["X_NA"] = {"score": 99.5, "applicable": False, "class": "not_applicable"}
    scope = {f"T{i:03d}" for i in range(50, 80)} | {"X_NA"}
    picks, info = engine.scoped_select(snap, scope, 10)
    assert picks == [f"T{i:03d}" for i in range(50, 60)] and info["k"] == 10
    rnd = random.Random(0)
    shuffled = {k: dict(v, **{"class": rnd.choice(["selected", "not_selected"])}) if v["applicable"] else v for k, v in snap.items()}
    assert engine.scoped_select(shuffled, scope, 10)[0] == picks


def test_stale_page_is_blocked_and_page_not_cached():
    from sandbox.v2.server import app_version, create_app
    c = create_app().test_client()
    r = c.get("/")
    assert r.headers["Cache-Control"] == "no-store" and f'window.APP_VERSION = "{app_version()}"' in r.get_data(as_text=True)
    body = {"stages": {"A": {"mode": "on", "version": BMFW, "ranking": "scoped_fixed_n", "n": 20}}, "scope": XLK, "condition": {"id": "equal_weight_A"}}
    old = c.post("/api/preflight", json=body, headers={"X-App-Version": "old-page"})
    assert old.status_code == 409 and old.get_json()["kind"] == "stale_page"
    assert c.post("/api/jobs", json=body, headers={"X-App-Version": "old-page"}).status_code == 409
    ok = c.post("/api/preflight", json=body, headers={"X-App-Version": app_version()}).get_json()
    assert ok["effective"]["ranking"] == "scoped_fixed_n" and ok["effective"]["n"] == 20  # สิ่งที่ server จะรันจริง
    assert c.post("/api/preflight", json=body).status_code == 200  # script/test ที่ไม่ส่ง header ยังใช้ได้
