"""G2/G2b: B version จากข่าว manual — score = label -2..+2 เฉพาะวันที่มีข่าวจริง (point-in-time), วันอื่น applicable False
แยก 2 version ตามวิธีตั้ง label: manual-labels-oracle (hindsight, badge ORACLE) / manual-labels-realtime (real_time, badge MANUAL)"""
import csv

import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, experiments_store as xs, news, registry
from sandbox.v2.server import create_app

FIXTURE = cfg.V2 / "tests" / "fixtures" / "manual_news_sample.csv"
LABEL_COL = "label จาก Claude (-2..+2)"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_NEWS", tmp_path / "manual_news.jsonl")
    yield create_app().test_client()
    registry.scan()  # ล้าง version ที่ build จากข่าวชั่วคราวของ test


def _import(client, path, **extra):
    prev = client.post("/api/news/csv/preview", json={"text": path.read_text(encoding="utf-8")}).get_json()
    rows = [dict(r, **dict({"label_method": "real_time"}, **extra)) for r in prev["rows"]]  # import ต้องระบุวิธี label เสมอ (N3)
    res = client.post("/api/news/csv/commit", json={"rows": rows}).get_json()
    assert res["errors"] == [], res
    return res


def _expected(path, ticker="META"):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["ticker"] == ticker]
    return {news.trading_day_info(r["วันที่ข่าวออก (publish_date)"])["next_trading_day"]: int(r[LABEL_COL]) for r in rows}


def _check_src(expected, vid):
    return f'''NAME = "check manual labels"
DESCRIPTION = "ตรวจ ctx.b ทุกวัน"
EXPECTED = {expected!r}
def decide(ctx):
    b = ctx.b.get("META")
    assert b is not None, "META ต้องมี record ของ B ทุกวัน (ไม่มีข่าว = applicable False)"
    if ctx.date in EXPECTED:
        assert b["applicable"] is True and b["score"] == EXPECTED[ctx.date] and b["label"] == EXPECTED[ctx.date], (ctx.date, b)
        assert b["date"] == ctx.date and b["reasons"][0].startswith("MANUAL " + ctx.date), b
        ctx.state["hit"] = ctx.state.get("hit", 0) + 1
    else:
        assert b["applicable"] is False and b["score"] is None, (ctx.date, b)
    return {{"META": 1.0}} if b["applicable"] and b["score"] > 0 else None
'''


def run_check(tmp_path, vid, expected):
    conf, w = engine.normalize_config({"stages": {"B": {"mode": "on", "version": vid}},
                                       "scope": {"mode": "tickers", "tickers": ["META"]},
                                       "condition": {"source": _check_src(expected, vid)}})
    engine.run(conf, tmp_path / "run", log=lambda m: None)
    return conf, w, pd.read_parquet(tmp_path / "run" / "trades.parquet")


ORACLE, REALTIME = "B:manual-labels-oracle", "B:manual-labels-realtime"


def test_manual_labels_version_matches_file_point_in_time(client, tmp_path):
    _import(client, FIXTURE, label_method="hindsight")
    vid = ORACLE
    m = registry.get(vid)
    exp = _expected(FIXTURE)
    assert m["result_badge"] == "oracle" and not m["is_stub"] and m["asof"]["max_age_days"] == 0
    assert m["coverage"]["start"] == min(exp) and m["coverage"]["end"] == max(exp) and m["coverage"]["tickers"] == ["META"]
    assert "point-in-time" in m["notes"]
    s = registry.signals(vid)
    assert dict(zip(s["date"].dt.strftime("%Y-%m-%d"), s["score"].astype(int))) == exp
    _, _, tr = run_check(tmp_path, vid, exp)  # condition assert ทุกวัน — ผิดวันเดียว run จะล้ม
    assert len(tr) > 0


def test_rebuild_follows_news_changes(client):
    _import(client, FIXTURE, label_method="hindsight")
    n0 = registry.get(ORACLE)["coverage"]["n_rows"]
    nid = news._load()[0]["id"]
    assert client.delete(f"/api/news/{nid}").status_code == 200
    assert registry.get(ORACLE)["coverage"]["n_rows"] == n0 - 1
    r = client.post("/api/news", json={"headline": "extra", "date": "2022-06-01", "tickers": ["AAPL"], "label": -2, "label_method": "hindsight"})
    assert r.status_code == 201
    s = registry.signals(ORACLE)
    assert s[(s["ticker"] == "AAPL")]["score"].tolist() == [-2.0]


def test_same_day_news_are_averaged_not_guessed(client):
    for lab in (2, 1):
        client.post("/api/news", json={"headline": f"x{lab}", "date": "2022-06-01", "tickers": ["AAPL"], "label": lab, "label_method": "real_time"})
    s = registry.signals(REALTIME)
    r = s[s["ticker"] == "AAPL"].iloc[0]
    assert r["score"] == 2.0 and r["n_news"] == 2 and len(r["reasons"]) == 3  # 1.5 → ปัดครึ่งออกจาก 0 = 2 + บันทึกเหตุผล


def test_empty_news_gives_empty_but_valid_version(client):
    for vid in (ORACLE, REALTIME):
        m = registry.get(vid)
        assert m["coverage"]["n_rows"] == 0 and m["coverage"]["start"] is None
        assert any("ยังไม่มีข่าว" in w for w in m["warnings"])
    with pytest.raises(KeyError):
        registry.get("B:manual-labels")  # version รวมแบบเดิม (G2) เลิกใช้ — ไม่ปนสองประเภท


# ------------------------------------------------------------------ G2b: Oracle vs real-time

def _run_saved(tmp_path, name, stages, include_manual=False, cid="equal_weight_A", scope=None):
    body = {"stages": stages, "include_manual": include_manual, "condition": {"id": cid}}
    if scope:
        body["scope"] = scope
    conf, w = engine.normalize_config(body)
    w += engine.coverage_warnings(conf)
    d = tmp_path / name
    engine.run(conf, d, log=lambda m: None)
    return xs.load_dir(d), w


def test_oracle_and_realtime_are_separate(client, tmp_path):
    _import(client, FIXTURE, label_method="hindsight")  # META 9 ข่าว label ตอนรู้ผลแล้ว
    for d, lab in (("2022-06-01", 2), ("2022-09-01", -1), ("2023-03-01", 1)):  # ข่าวใหม่ 3 รายการ real-time
        r = client.post("/api/news", json={"headline": f"rt {d}", "date": d, "tickers": ["META"], "label": lab, "label_method": "real_time"})
        assert r.status_code == 201
    client.post("/api/news", json={"headline": "no method", "date": "2022-07-01", "tickers": ["META"], "label": 2})  # → unknown
    o, rt = registry.signals(ORACLE), registry.signals(REALTIME)
    assert len(o) == 9 and set(o["label_method"]) == {"hindsight"}
    assert len(rt) == 3 and set(rt["label_method"]) == {"real_time"}
    assert "2022-07-01" not in set(o["date"].dt.strftime("%Y-%m-%d")) | set(rt["date"].dt.strftime("%Y-%m-%d"))  # unknown ไม่เข้าทั้งคู่
    assert registry.get(ORACLE)["result_badge"] == "oracle" and registry.get(REALTIME)["result_badge"] == "manual"
    assert news.method_summary()["counts"] == {"hindsight": 9, "real_time": 3, "unknown": 1}

    meta = {"mode": "tickers", "tickers": ["META"]}
    res, w = _run_saved(tmp_path, "oracle", {"B": {"mode": "on", "version": ORACLE}}, cid="exclude_negative_B", scope=meta)
    assert res["provenance"]["contains_oracle_signal"] is True
    assert res["badges"][0] == {"kind": "oracle", "text": "ORACLE"}
    assert any("ORACLE:" in x for x in w)

    res, w = _run_saved(tmp_path, "realtime", {"B": {"mode": "on", "version": REALTIME}}, cid="exclude_negative_B", scope=meta)
    assert res["provenance"]["contains_oracle_signal"] is False
    assert not any(b["kind"] == "oracle" for b in res["badges"]) and {"kind": "manual_labels", "text": "B MANUAL"} in res["badges"]
    assert not any("ORACLE" in x for x in w)


def test_include_manual_toggle_with_hindsight_news_is_flagged(client, tmp_path):
    _import(client, FIXTURE, label_method="hindsight")
    res, w = _run_saved(tmp_path, "toggle", {"B": {"mode": "on", "version": "B:stub"}}, include_manual=True,
                        scope={"mode": "tickers", "tickers": ["META"]})
    assert res["provenance"]["contains_oracle_signal"] is True and res["provenance"]["manual_label_methods"] == {"hindsight": 9}
    assert res["badges"][0]["kind"] == "oracle" and any(x.startswith("ORACLE:") for x in w)


def test_label_method_required_values_and_batch_update(client):
    r = client.post("/api/news", json={"headline": "x", "date": "2022-06-01", "tickers": ["AAPL"], "label": 1, "label_method": "guess"})
    assert r.status_code == 400
    # ข่าวเก่าที่ยังไม่ระบุวิธี (import ใหม่ไม่ยอมให้เกิด unknown แล้ว — N3) → สร้างผ่าน API แบบ legacy เพื่อทดสอบเครื่องมือระบุย้อนหลัง
    prev = client.post("/api/news/csv/preview", json={"text": FIXTURE.read_text(encoding="utf-8")}).get_json()
    for r in prev["rows"]:
        client.post("/api/news", json={"headline": r["headline"], "date": r["date"], "tickers": r["tickers"], "label": r["label"],
                                       "extra": r["extra"], "import_batch": "legacy-file.csv"})
    s = client.get("/api/news/methods").get_json()
    assert s["counts"]["unknown"] == 9 and len(s["unknown_batches"]) == 1 and s["unknown_batches"][0]["n"] == 9
    assert registry.get(ORACLE)["coverage"]["n_rows"] == 0 and registry.get(REALTIME)["coverage"]["n_rows"] == 0
    b = s["unknown_batches"][0]
    assert b["sample_reason"]  # แสดงตัวอย่างเหตุผลของ label ให้ผู้ใช้ตัดสินใจเอง
    r = client.post("/api/news/label_method", json={"ids": b["ids"], "method": "hindsight"}).get_json()
    assert r["updated"] == 9 and registry.get(ORACLE)["coverage"]["n_rows"] == 9
    assert client.post("/api/news/label_method", json={"ids": b["ids"], "method": "nope"}).status_code == 400
