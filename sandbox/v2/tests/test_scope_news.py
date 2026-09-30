"""N4: เตือนเมื่อข่าว manual เป็นของหุ้นนอกขอบเขตที่เลือกทดสอบ (sector จริง GICS)"""
import pytest

from sandbox.v2 import config as cfg, engine, news, prices, registry
from sandbox.v2.server import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_NEWS", tmp_path / "manual_news.jsonl")
    c = create_app().test_client()
    for i, (t, d) in enumerate([("META", "2022-02-02"), ("META", "2022-04-27"), ("NFLX", "2022-04-19"), ("GOOGL", "2022-10-25"),
                                ("NVDA", "2022-08-24"), ("TXN", "2022-07-26"), ("TRMB", "2022-08-03")]):
        assert c.post("/api/news", json={"headline": f"h{i}", "date": d, "tickers": [t], "label": -1, "label_method": "real_time"}).status_code == 201
    yield c
    registry.scan()


def test_sectors_are_real_gics():
    man = prices.manifest()["tickers"]
    assert [man[t]["sector"] for t in ("META", "NFLX", "GOOGL")] == ["Communication Services"] * 3
    assert [man[t]["sector"] for t in ("NVDA", "TXN", "TRMB")] == ["Information Technology"] * 3


def test_scope_check_and_preflight_warning(client):
    j = client.post("/api/news/scope_check", json={"scope": {"mode": "sectors", "sectors": ["XLK"]}}).get_json()
    assert j["n_outside"] == 4 and j["n_inside"] == 3 and j["label"] == "sector XLK"
    assert {x["ticker"]: x["etf"] for x in j["outside"]} == {"META": "XLC", "NFLX": "XLC", "GOOGL": "XLC"}
    assert client.post("/api/news/scope_check", json={"scope": {"mode": "sectors", "sectors": ["XLK", "XLC"]}}).get_json()["n_outside"] == 0
    body = {"stages": {"A": {"mode": "on", "version": "A:bmf20-weighted"}, "B": {"mode": "on", "version": "B:manual-labels-realtime"}},
            "scope": {"mode": "sectors", "sectors": ["XLK"]}, "condition": {"id": "equal_weight_A"}}
    w = client.post("/api/preflight", json=body).get_json()["warnings"]
    msg = [x for x in w if x.startswith("SCOPE-NEWS")]
    assert msg and "มีข่าว 4 รายการเป็นของหุ้นนอกขอบเขต" in msg[0] and "META (Communication Services)" in msg[0]
    body["scope"] = {"mode": "sectors", "sectors": ["XLK", "XLC"]}  # เลือกหลาย sector พร้อมกันได้
    assert not any(x.startswith("SCOPE-NEWS") for x in client.post("/api/preflight", json=body).get_json()["warnings"])
    body["stages"]["B"] = {"mode": "off"}
    body["scope"] = {"mode": "sectors", "sectors": ["XLK"]}
    assert not any(x.startswith("SCOPE-NEWS") for x in client.post("/api/preflight", json=body).get_json()["warnings"])  # ไม่ได้ใช้ข่าว


def test_list_by_tickers_link(client):
    j = client.get("/api/news?tickers=META,NFLX,GOOGL").get_json()
    assert j["total"] == 4 and {t for r in j["rows"] for t in r["tickers"]} == {"META", "NFLX", "GOOGL"}


def test_page_shows_warning_and_sectors():
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    for x in ('id="scope-news-warn"', 'id="news-scope-warn"', "outsideLink()", "ticker-sector"):
        assert x in html, x
