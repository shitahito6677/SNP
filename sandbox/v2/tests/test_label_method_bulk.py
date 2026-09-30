"""L1: ข่าวที่ไม่ได้ระบุ label_method (unknown) ไม่อยู่ใน B manual-labels ใด ๆ → แก้แบบ bulk แล้วสัญญาณ B สะท้อนทันที + มีคำเตือน"""
import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, news, registry, stock_view
from sandbox.v2.server import create_app

REALTIME = "B:manual-labels-realtime"
BAD_DAY = "2022-06-15"  # วันพุธ (วันทำการ)

SELL_ON_BAD_NEWS = '''NAME = "ขายเมื่อเจอข่าวร้าย"
DESCRIPTION = "ถือ MU เต็มพอร์ต · ข่าว score ≤ -1 → ขายทั้งหมด"
EXPECT_SIGNAL = {expect}
def decide(ctx):
    b = ctx.b.get("MU")
    if ctx.date == "{day}":
        if EXPECT_SIGNAL:
            assert b["applicable"] is True and b["score"] == -2 and b["label"] == -2, b
        else:
            assert b["applicable"] is False and b["score"] is None, b  # bug เดิม: มีข่าวแต่ ctx.b ไม่เห็น
    if b and b.get("applicable") and b["score"] <= -1:
        ctx.state["sold"] = True
    return {{}} if ctx.state.get("sold") else {{"MU": 1.0}}
'''


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_NEWS", tmp_path / "manual_news.jsonl")
    yield create_app().test_client()
    registry.scan()


def _run(tmp_path, name, expect):
    conf, w = engine.normalize_config({"start": "2022-06-01", "end": "2022-07-29", "stages": {"B": {"mode": "on", "version": REALTIME}},
                                       "scope": {"mode": "tickers", "tickers": ["MU"]},
                                       "condition": {"source": SELL_ON_BAD_NEWS.format(expect=expect, day=BAD_DAY)}})
    w += engine.coverage_warnings(conf)
    engine.run(conf, tmp_path / name, log=lambda m: None)
    return pd.read_parquet(tmp_path / name / "trades.parquet"), w


def test_unknown_news_invisible_until_bulk_set_then_sell_happens(client, tmp_path):
    for d, lab, h in (("2022-06-02", 1, "Micron guides higher"), (BAD_DAY, -2, "Micron warns of sharp demand drop")):
        assert client.post("/api/news", json={"headline": h, "date": d, "tickers": ["MU"], "label": lab}).status_code == 201  # ไม่ระบุวิธี → unknown
    assert news.unknown_count(["MU"]) == 2
    assert stock_view.build("MU")["manual_unknown"] == 2  # หน้าหุ้นเตือน
    assert any(len(m["time"]) == 10 for m in stock_view.build("MU")["layers"]["manual"])  # ข่าวยังโชว์บนกราฟ

    tr, w = _run(tmp_path, "before", expect=False)  # ยืนยัน bug เดิม: ctx.b["MU"] วันนั้น applicable False → ไม่ขาย
    assert (tr["side"] == "sell").sum() == 0
    assert any(x.startswith("MANUAL: มีข่าว 2 รายการที่ยังไม่ได้ระบุ") for x in w)

    # เครื่องมือ bulk: ตัวกรอง "ยังไม่ระบุ" + ticker MU → ตั้งเป็น real_time ทั้งหมดที่กรองอยู่
    lst = client.get("/api/news?method=unknown&ticker=MU").get_json()
    assert lst["total"] == 2 and {r["label_method"] for r in lst["rows"]} == {"unknown"}
    r = client.post("/api/news/label_method", json={"filter": {"method": "unknown", "ticker": "MU"}, "method": "real_time"}).get_json()
    assert r == {"updated": 2, "matched": 2}
    s = registry.signals(REALTIME)  # สัญญาณสร้างใหม่ทันที (ไม่ค้างค่าเก่า)
    assert s[s["ticker"] == "MU"].set_index(s["date"].dt.strftime("%Y-%m-%d"))["score"].to_dict() == {"2022-06-02": 1.0, BAD_DAY: -2.0}
    assert news.unknown_count() == 0 and stock_view.build("MU")["manual_unknown"] == 0

    tr, w = _run(tmp_path, "after", expect=True)
    sells = tr[tr["side"] == "sell"]
    assert len(sells) == 1 and str(sells["decision_date"].iloc[0]) == BAD_DAY  # ขายจริงตามข่าวร้าย
    assert any("label -2 negative แรงมาก" in c for c in sells["reasons"].iloc[0])
    assert not any(x.startswith("MANUAL: มีข่าว") for x in w)


def test_filters_and_select_by_ids(client):
    rows = [("2022-01-10", ["AAPL"], "a"), ("2022-03-10", ["MSFT"], "b"), ("2022-05-10", ["XOM"], "c"), ("2022-07-10", ["AAPL"], "d")]
    ids = [client.post("/api/news", json={"headline": h, "date": d, "tickers": t, "label": 0}).get_json()["id"] for d, t, h in rows]
    q = lambda s: client.get("/api/news?" + s).get_json()  # noqa: E731
    assert q("ticker=aapl")["total"] == 2
    assert q("sector=XLK")["total"] == 3 and q("sector=XLE")["total"] == 1  # AAPL/MSFT = Information Technology
    assert q("date_from=2022-03-01&date_to=2022-06-30")["total"] == 2
    assert q("method=unknown")["total"] == 4
    assert client.post("/api/news/label_method", json={"ids": ids[:1], "method": "hindsight"}).get_json()["updated"] == 1
    assert q("method=unknown")["total"] == 3 and q("method=hindsight")["total"] == 1
    assert isinstance(client.get("/api/news").get_json(), list)  # ไม่มีตัวกรอง = รูปแบบเดิม
    assert client.post("/api/news/label_method", json={"filter": {}, "method": "bogus"}).status_code == 400


def test_page_has_bulk_tools():
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    for x in ('id="news-filter"', 'id="nf-unknown"', 'id="sel-filtered"', 'id="bulk-method"', 'id="bulk-apply"',
              'class="news-sel"', 'id="unknown-news-warn"', "#/news?method=unknown"):
        assert x in html, x
