"""F3: ขอบเขตการลงทุน (ทั้งตลาด / sector / หุ้นที่ระบุ)
- ขั้นแรกของ funnel = หุ้นใน scope ที่มีราคาวันนั้นเท่านั้น
- EW benchmark = EW ของหุ้นใน scope (SPY ไม่เปลี่ยน)
- A ranking มาจากทั้ง universe แล้วค่อยกรอง scope (ห้ามจัดอันดับใหม่)
- บันทึก → restart → เปิดใหม่ scope เดิม"""
import pandas as pd
import pytest
import requests

from sandbox.v2 import config as cfg, engine, prices
from sandbox.v2.signals import AsOf
from sandbox.v2.tests.test_persistence import BASE, start_server, wait

A1 = "A:A1_r001_Q_LOWACC_overall"
CASES = {
    "all": None,
    "sector": {"mode": "sectors", "sectors": ["XLE"]},
    "ticker": {"mode": "tickers", "tickers": ["XOM"]},
}


def _body(scope, name):
    b = {"name": f"pytest scope {name}", "stages": {"A": {"mode": "filter", "version": A1}}, "condition": {"id": "equal_weight_A"}}
    if scope:
        b["scope"] = scope
    return b


def _members(scope):
    stocks = prices.available_tickers("stock")
    if scope is None:
        return stocks
    if scope["mode"] == "sectors":
        return [t for t in stocks if cfg.SECTOR_ETFS.get(prices.sector_of(t)) in scope["sectors"]]
    return scope["tickers"]


@pytest.fixture(scope="module")
def runs():
    """รัน 3 กรณีผ่าน API จริง → บันทึก → restart server → โหลดผลที่บันทึก"""
    p = start_server()
    live, exps = {}, {}
    try:
        for name, scope in CASES.items():
            r = requests.post(BASE + "/api/jobs", json=_body(scope, name), timeout=60)
            assert r.status_code == 201, r.text
            job = r.json()["id"]
            wait(job)
            live[name] = requests.get(f"{BASE}/api/results/run/{job}", timeout=60).json()
            exps[name] = requests.post(BASE + "/api/experiments", json={"job_id": job, "name": f"pytest scope {name}"}, timeout=30).json()["id"]
    finally:
        p.terminate(); p.wait(5)
    p = start_server()
    try:
        saved = {n: requests.get(f"{BASE}/api/results/exp/{e}", timeout=60).json() for n, e in exps.items()}
        yield live, saved
        for e in exps.values():
            assert requests.delete(f"{BASE}/api/experiments/{e}?confirm={e}", timeout=10).status_code == 200
    finally:
        p.terminate(); p.wait(5)


@pytest.mark.parametrize("name", list(CASES))
def test_funnel_first_step_is_scope(runs, name):
    live, _ = runs
    scope = CASES[name]
    fun = pd.DataFrame(live[name]["funnel"])
    conf = live[name]["config"]
    adj = prices.load("adj", _members(scope), conf["start"], conf["end"]).reindex(pd.to_datetime(fun["date"]))
    expected = adj.notna().sum(axis=1).to_numpy()
    assert (fun["universe"].to_numpy() == expected).all()
    if name == "ticker":
        assert set(fun["universe"]) == {1} and fun["after_A"].max() <= 1
    if name == "sector":
        assert fun["universe"].max() == len(_members(scope)) == 21 and (fun["market"] > fun["universe"]).all()
        assert (fun["after_A"] <= fun["universe"]).all()
    if name == "all":
        assert "market" not in fun and fun["universe"].min() > 500


@pytest.mark.parametrize("name", list(CASES))
def test_ew_benchmark_uses_scope_only(runs, name):
    live, _ = runs
    conf = live[name]["config"]
    eq = pd.DataFrame(live[name]["equity"])
    cal = prices.calendar(conf["start"], conf["end"])
    adj = prices.load("adj", None, conf["start"], conf["end"]).reindex(cal)
    stocks = [t for t in prices.available_tickers("stock") if t in adj.columns and adj[t].notna().any()]
    mine = [t for t in stocks if t in set(_members(CASES[name]))]
    ew_scope = engine._bench_ew(adj[mine], conf["capital"], conf["cost"])
    assert list(eq["ew"]) == list(ew_scope.to_numpy())
    spy = engine._bench_spy(adj, conf["capital"], conf["cost"])
    assert list(eq["spy"]) == list(spy.to_numpy())  # SPY ไม่ขึ้นกับ scope
    if name != "all":
        ew_all = engine._bench_ew(adj[stocks], conf["capital"], conf["cost"])
        assert abs(eq["ew"].iloc[-1] - ew_all.iloc[-1]) > 1.0  # ไม่ใช่ EW ของทั้งตลาด
        assert live[name]["metrics"]["scope"]["ew_names"] == len(mine)


@pytest.mark.parametrize("name", list(CASES))
def test_saved_result_reopens_with_same_scope(runs, name):
    live, saved = runs
    got = saved[name]
    scope = got["config"]["scope"]
    want = CASES[name] or {"mode": "all", "sectors": [], "tickers": []}
    assert scope["mode"] == want["mode"] and scope["sectors"] == want.get("sectors", []) and scope["tickers"] == want.get("tickers", [])
    assert got["metrics"] == live[name]["metrics"] and got["funnel"] == live[name]["funnel"] and got["equity"] == live[name]["equity"]
    if name == "sector":
        assert "scope: XLE" in got["chips"] and scope["members"] == _members(CASES["sector"])
    if name == "ticker":
        assert "scope: XOM" in got["chips"]
    assert got["empty_reason"] is None


def test_A_ranking_comes_from_whole_universe():
    """A record ที่ condition เห็นใน scope = record เดียวกับตอนไม่จำกัด scope (ไม่จัดอันดับใหม่) และ passA(scope) = passA(all) ∩ scope"""
    st = {"A": {"mode": "filter", "version": A1, "criteria": dict(engine.DEFAULT_CRITERIA["A"])},
          "B": {"mode": "off"}, "C": {"mode": "off"}}
    asof = {"A": AsOf(A1)}
    t = pd.Timestamp("2022-09-01")
    adj = prices.load("adj", None, t, t)
    stocks = [x for x in prices.available_tickers("stock") if x in adj.columns and adj[x].notna().any()]
    sector_of = {x: prices.sector_of(x) for x in stocks}
    scope = set(_members(CASES["sector"]))
    u_all, a_all, _, _, f_all = engine.stage_day(t, adj.iloc[0], stocks, [], asof, st, sector_of)
    u_sc, a_sc, _, _, f_sc = engine.stage_day(t, adj.iloc[0], stocks, [], asof, st, sector_of, scope)
    assert u_sc == sorted(set(u_all) & scope) and u_sc
    for k in u_sc:
        assert a_sc[k] == a_all[k]  # score/class/weight/reasons เดิมทุกตัวอักษร
    assert f_sc["universe"] == 21 and f_sc["market"] == f_all["universe"]


def test_single_ticker_failing_A_explains_empty_portfolio():
    """NVDA ไม่ถูก A1 เลือกทั้ง 2 รอบในช่วง default → เตือนก่อนรัน + หน้าผลบอกเหตุผล ไม่ใช่กราฟเปล่าเงียบ ๆ"""
    conf, w = engine.normalize_config(_body({"mode": "tickers", "tickers": ["NVDA"]}, "nvda"))
    w += engine.coverage_warnings(conf)
    assert any("ไม่ผ่านเกณฑ์ A ในทุกรอบ" in x for x in w)
    from sandbox.v2 import experiments_store as xs
    met = {"full": {"strategy": {"avg_holdings": 0.0}}, "funnel_avg": {"universe": 1.0, "after_A": 0.0, "held": 0.0}}
    assert xs.empty_reason(conf, met).startswith("หุ้นที่เลือกไม่ผ่านเกณฑ์ A ในช่วงเวลานี้")


@pytest.mark.parametrize("scope, msg", [
    ({"mode": "sectors", "sectors": []}, "ยังไม่ได้เลือก sector"),
    ({"mode": "sectors", "sectors": ["XLZ"]}, "ไม่รู้จัก sector"),
    ({"mode": "tickers", "tickers": []}, "ยังไม่ได้เลือกหุ้น"),
    ({"mode": "tickers", "tickers": ["NOPEX"]}, "ไม่พบหุ้น"),
    ({"mode": "weird"}, "mode ต้องเป็น"),
])
def test_invalid_scope_rejected_before_run(scope, msg):
    with pytest.raises(engine.ConfigError, match=msg):
        engine.normalize_config(_body(scope, "bad"))


def test_sector_with_no_members_warns_before_run(monkeypatch):
    """sector ที่ไม่มีหุ้นใน universe (ข้อมูลไม่ครบ) → preflight ปฏิเสธพร้อมข้อความ ก่อนกด RUN"""
    real = prices.sector_of
    monkeypatch.setattr(prices, "sector_of", lambda t: "Unknown" if real(t) == "Utilities" else real(t))
    from sandbox.v2.server import create_app
    r = create_app().test_client().post("/api/preflight", json=_body({"mode": "sectors", "sectors": ["XLU"]}, "xlu"))
    assert r.status_code == 400 and "ไม่มีหุ้นใน universe" in r.get_json()["error"]


def test_preflight_reports_scope_size():
    from sandbox.v2.server import create_app
    c = create_app().test_client()
    j = c.post("/api/preflight", json=_body({"mode": "sectors", "sectors": ["XLE", "XLU"]}, "x")).get_json()
    assert j["scope"]["n_members"] == len(_members({"mode": "sectors", "sectors": ["XLE", "XLU"]})) and any(w.startswith("SCOPE") for w in j["warnings"])
    j = c.post("/api/preflight", json=_body(None, "x")).get_json()
    assert j["scope"]["mode"] == "all" and j["scope"]["n_members"] is None
