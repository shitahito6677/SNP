"""I1/I2: gallery หุ้นรายตัว — เฉพาะ status ok, จำนวนข่าว manual ต่อหุ้น, flag โลโก้จาก cache ในเครื่อง (ไม่ยิง network)"""
import pytest

from sandbox.v2 import config as cfg, news, prices
from sandbox.v2.server import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_NEWS", tmp_path / "manual_news.jsonl")
    monkeypatch.setattr(cfg, "LOGOS_DIR", tmp_path / "logos")
    return create_app().test_client()


def test_gallery_lists_exactly_status_ok_stocks(client):
    j = client.get("/api/stocks/gallery").get_json()
    man = prices.manifest()["tickers"]
    want = sorted(t for t, r in man.items() if r.get("status") == "ok" and r.get("kind") == "stock")
    assert [x["t"] for x in j["tickers"]] == want and j["n"] == len(want) > 500
    assert not any(man[x["t"]]["status"] == "partial" for x in j["tickers"])
    assert all(x["sector"] and x["name"] for x in j["tickers"])
    assert not any(x["logo"] for x in j["tickers"])  # ยังไม่มี cache โลโก้ → ใช้ avatar ทุกตัว


def test_gallery_news_counts_and_logo_flag(client):
    news.add({"headline": "a", "date": "2022-06-01", "tickers": ["AAPL", "MSFT"], "label": 1})
    news.add({"headline": "b", "date": "2022-06-02", "tickers": ["AAPL"], "label": -1})
    nid = news.add({"headline": "c", "date": "2022-06-03", "tickers": ["AAPL"], "label": 0})["id"]
    news.delete(nid)  # ข่าวที่ลบแล้วไม่นับ
    cfg.LOGOS_DIR.mkdir(parents=True)
    (cfg.LOGOS_DIR / "AAPL.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    by = {x["t"]: x for x in client.get("/api/stocks/gallery").get_json()["tickers"]}
    assert by["AAPL"]["news"] == 2 and by["MSFT"]["news"] == 1 and by["NVDA"]["news"] == 0
    assert by["AAPL"]["logo"] is True and by["MSFT"]["logo"] is False
