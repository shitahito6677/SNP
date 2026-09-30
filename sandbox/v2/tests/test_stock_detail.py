"""F2: หน้าหุ้นรายตัวต้องไม่ 500 ทุกกรณี — META, AAPL, ticker partial/missing, ช่วง held-out, วันที่ผิด, เปิดจากการทดลองที่ไม่มี trade"""
import json

import pandas as pd
import pytest

from sandbox.v2 import config as cfg, prices, stock_view
from sandbox.v2.server import create_app

UI_DEFAULT = "A=A%3AA1_r001_Q_LOWACC_overall&C=C%3Arulebase-exp03"  # query เดียวกับที่ stock.js ส่งเมื่อไม่ได้เลือกการทดลอง


@pytest.fixture()
def client():
    return create_app().test_client()


def _status(ticker):
    return prices.manifest()["tickers"][ticker]["status"]


@pytest.mark.parametrize("ticker", ["META", "AAPL"])
def test_known_tickers_open(client, ticker):
    r = client.get(f"/api/stock/{ticker}?{UI_DEFAULT}")
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()
    assert d["ticker"] == ticker and len(d["bars"]) > 400 and d["trades"] == []
    assert d["layers"]["A"] and d["layers"]["C"]  # ดูหุ้นเฉย ๆ (ไม่มี trade) ก็มี layer ของ A1 + C


def test_lowercase_and_mention_style_ticker(client):
    assert client.get("/api/stock/meta").status_code == 200
    assert client.get("/api/stock/brk.b").get_json()["ticker"] == "BRK-B"


def test_partial_ticker(client):
    t = next(t for t, r in prices.manifest()["tickers"].items() if r.get("status") == "partial" and r.get("kind") == "stock")
    r = client.get(f"/api/stock/{t}?{UI_DEFAULT}")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "partial" and any("ราคาไม่ครบช่วง" in n for n in d["notices"])


def test_missing_ticker_gives_readable_error(client, monkeypatch):
    """manifest ปัจจุบันไม่มี status missing (ok 564 / partial 11) → จำลองรายการ missing 1 ตัว"""
    man = json.loads(json.dumps(prices.manifest()))
    man["tickers"]["ZZMISS"] = {"name": "Missing Corp", "kind": "stock", "status": "missing", "reason": "Yahoo ไม่มีข้อมูล"}
    monkeypatch.setattr(prices, "manifest", lambda: man)
    r = client.get(f"/api/stock/ZZMISS?{UI_DEFAULT}")
    assert r.status_code == 404 and r.is_json
    e = r.get_json()["error"]
    assert "ไม่มีข้อมูลราคาของ ZZMISS" in e and "missing" in e and "Yahoo ไม่มีข้อมูล" in e


def test_unknown_ticker_gives_readable_error(client):
    r = client.get("/api/stock/NOTATICKER")
    assert r.status_code == 404 and r.is_json and "ไม่พบ NOTATICKER" in r.get_json()["error"]


def test_held_out_window_is_empty_not_500(client):
    """root cause ที่ reproduce ได้: ช่วงที่เริ่มหลัง DEFAULT_END (เช่น mini chart ของข่าวปี 2026) → เคย start > end → 500"""
    for q in ("start=2026-08-14&end=2026-11-12", "start=2027-01-01&end=2027-03-01", "start=2023-08-20&end=2023-10-01"):
        r = client.get(f"/api/stock/META?{q}")
        assert r.status_code == 200, (q, r.get_data(as_text=True)[:200])
        d = r.get_json()
        assert d["bars"] == [] and any("held-out" in n for n in d["notices"])
    d = client.get("/api/stock/META?start=2023-05-01&end=2023-09-01").get_json()  # คร่อม → ตัดที่ DEFAULT_END
    assert d["bars"] and d["bars"][-1]["time"] <= cfg.DEFAULT_END


@pytest.mark.parametrize("q", ["start=abc&end=def", "start=2023-02-01&end=2022-01-01", "kind=exp&id=nope",
                               "kind=run&id=does-not-exist", "kind=weird&id=x", "A=A%3Anot-a-version"])
def test_bad_params_are_readable(client, q):
    r = client.get(f"/api/stock/META?{q}")
    assert r.status_code in (200, 400, 404) and r.is_json, r.get_data(as_text=True)[:200]
    if r.status_code != 200:
        assert r.get_json()["error"] and "Traceback" not in r.get_json()["error"]


def test_opened_from_experiment_without_trades_for_ticker(client, tmp_path, monkeypatch):
    """เปิด META จากช่องค้นหาขณะอยู่ในบริบทการทดลองที่ไม่เคยซื้อ META → ต้องแสดงราคา+สัญญาณ ไม่ error"""
    d = tmp_path / "exp"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"start": "2021-09-27", "end": "2023-06-30", "held_out": {"touched": False},
                                               "stages": {"A": {"mode": "filter", "version": "A:A1_r001_Q_LOWACC_overall"},
                                                          "B": {"mode": "off"}, "C": {"mode": "off"}}}))
    pd.DataFrame({"date": [pd.Timestamp("2022-06-02")], "ticker": ["AAPL"], "side": ["buy"], "reasons": [["x"]]}).to_parquet(d / "trades.parquet")
    monkeypatch.setattr(stock_view, "_result_dir", lambda kind, rid: d)
    r = client.get("/api/stock/META?kind=exp&id=whatever")
    assert r.status_code == 200
    j = r.get_json()
    assert j["trades"] == [] and j["layers"]["A"] and any("ไม่มีการซื้อขาย" in n for n in j["notices"])
    (d / "trades.parquet").unlink()  # การทดลองที่ clone มาไม่มี parquet
    j = client.get("/api/stock/META?kind=exp&id=whatever").get_json()
    assert j["bars"] and any("ไม่มีไฟล์ trade" in n for n in j["notices"])


def test_broken_layer_does_not_break_page(client, monkeypatch):
    from sandbox.v2 import registry

    def boom(vid):
        raise RuntimeError("corrupt signal file")
    monkeypatch.setattr(registry, "signals", boom)
    r = client.get(f"/api/stock/META?{UI_DEFAULT}")
    assert r.status_code == 200
    d = r.get_json()
    assert d["bars"] and any("โหลด layer A" in n for n in d["notices"])


def test_unexpected_error_is_json_with_error_id(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(stock_view, "build", boom)
    r = client.get("/api/stock/META")
    assert r.status_code == 500 and r.is_json
    j = r.get_json()
    assert "โหลดหน้าหุ้น META ไม่สำเร็จ" in j["error"] and j["error_id"]


def test_every_ticker_in_universe_opens():
    """ทุก ticker ที่ status ok/partial เปิดหน้าหุ้นได้ (ค่าตั้งต้นของ UI) — ไม่ใช่แค่ META"""
    fails = []
    for t, r in prices.manifest()["tickers"].items():
        if r.get("status") not in ("ok", "partial"):
            continue
        try:
            stock_view.build(t, versions={"A": "A:A1_r001_Q_LOWACC_overall", "C": "C:rulebase-exp03"})
        except Exception as e:  # noqa: BLE001
            fails.append((t, repr(e)))
    assert fails == []
