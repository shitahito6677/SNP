"""G2: B version จากข่าว manual — score = label -2..+2 เฉพาะวันที่มีข่าวจริง (point-in-time), วันอื่น applicable False"""
import csv

import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, news, registry
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
    rows = [dict(r, **extra) for r in prev["rows"]]
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


def test_manual_labels_version_matches_file_point_in_time(client, tmp_path):
    _import(client, FIXTURE)
    vid = "B:manual-labels"
    m = registry.get(vid)
    exp = _expected(FIXTURE)
    assert m["result_badge"] == "manual" and not m["is_stub"] and m["asof"]["max_age_days"] == 0
    assert m["coverage"]["start"] == min(exp) and m["coverage"]["end"] == max(exp) and m["coverage"]["tickers"] == ["META"]
    assert "point-in-time" in m["notes"]
    s = registry.signals(vid)
    assert dict(zip(s["date"].dt.strftime("%Y-%m-%d"), s["score"].astype(int))) == exp
    _, _, tr = run_check(tmp_path, vid, exp)  # condition assert ทุกวัน — ผิดวันเดียว run จะล้ม
    assert len(tr) > 0


def test_rebuild_follows_news_changes(client):
    _import(client, FIXTURE)
    n0 = registry.get("B:manual-labels")["coverage"]["n_rows"]
    nid = news._load()[0]["id"]
    assert client.delete(f"/api/news/{nid}").status_code == 200
    assert registry.get("B:manual-labels")["coverage"]["n_rows"] == n0 - 1
    r = client.post("/api/news", json={"headline": "extra", "date": "2022-06-01", "tickers": ["AAPL"], "label": -2})
    assert r.status_code == 201
    s = registry.signals("B:manual-labels")
    assert s[(s["ticker"] == "AAPL")]["score"].tolist() == [-2.0]


def test_same_day_news_are_averaged_not_guessed(client):
    for lab in (2, 1):
        client.post("/api/news", json={"headline": f"x{lab}", "date": "2022-06-01", "tickers": ["AAPL"], "label": lab})
    s = registry.signals("B:manual-labels")
    r = s[s["ticker"] == "AAPL"].iloc[0]
    assert r["score"] == 2.0 and r["n_news"] == 2 and len(r["reasons"]) == 3  # 1.5 → ปัดครึ่งออกจาก 0 = 2 + บันทึกเหตุผล


def test_empty_news_gives_empty_but_valid_version(client):
    m = registry.get("B:manual-labels")
    assert m["coverage"]["n_rows"] == 0 and m["coverage"]["start"] is None
    assert any("ยังไม่มีข่าว" in w for w in m["warnings"])
