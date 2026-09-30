"""Q4: เหตุการณ์ของทั้งพอร์ตบน equity curve + จำนวนหุ้นที่ถือ (อ่านจากบันทึกตอนรัน)"""
import pandas as pd

from sandbox.v2 import config as cfg, engine, experiments_store as xs, trade_causes

DEMO = (cfg.V2 / "tests" / "fixtures" / "cause_demo_condition.py").read_text(encoding="utf-8")


def test_events_and_holdings_from_demo_run(tmp_path):
    conf, _ = engine.normalize_config({"start": "2022-01-03", "end": "2022-06-30",
                                       "scope": {"mode": "tickers", "sectors": [], "tickers": ["AAPL", "MSFT", "NVDA", "KR"]},
                                       "stages": {"A": {"mode": "off", "version": None}}, "condition": {"source": DEMO}})
    d = tmp_path / "r"
    engine.run(conf, d, log=lambda m: None)
    ev = trade_causes.events(d)
    got = {(i["event"], tuple(i["tickers"])) for i in ev["items"]}
    assert ("sell_news", ("AAPL",)) in got and ("buy_receive", ("MSFT",)) in got
    assert ("buy_buyback", ("AAPL",)) in got and ("sell_pullback", ("MSFT",)) in got
    reb = [i for i in ev["items"] if i["event"] == "rebalance"]
    assert len(reb) == 1 and sorted(reb[0]["tickers"]) == ["AAPL", "KR", "MSFT", "NVDA"]
    # วันที่ของจุด = วันที่ซื้อขายจริง (close วันทำการถัดจากวันตัดสินใจ) และต้องอยู่บน equity curve
    eq = pd.read_parquet(d / "equity.parquet")
    days = set(eq["date"].dt.strftime("%Y-%m-%d"))
    assert all(i["date"] in days and i["date"] > i["decision_date"] for i in ev["items"])
    pull = next(i for i in ev["items"] if i["event"] == "sell_pullback")
    assert pull["rows"][0]["ref"] == ["AAPL"]
    assert set(ev["legend"]) == set(trade_causes.EVENT_KINDS) and ev["note"] is None
    res = xs.load_dir(d)
    assert res["events"]["items"] and {"n_holdings"} <= set(res["equity"][0])
    assert max(e["n_holdings"] for e in res["equity"]) == 4
    # ไม่รวมการปรับกลับเป้า (มีมากที่สุด — ดูได้ที่หน้าหุ้นรายตัว)
    assert "drift" not in {k for ks in trade_causes.EVENT_KINDS.values() for k in ks}


def test_result_without_decision_log_has_note(tmp_path):
    (tmp_path / "old").mkdir()
    pd.DataFrame({"date": [pd.Timestamp("2022-01-04")], "decision_date": ["2022-01-03"], "ticker": ["AAPL"], "side": ["buy"], "units": [1.0],
                  "price_adj": [1.0], "price_close": [1.0], "notional": [1.0], "cost": [0.0], "weight_before": [0.0], "weight_after": [1.0],
                  "reasons": [["condition: weight 100%"]]}).to_parquet(tmp_path / "old" / "trades.parquet")
    ev = trade_causes.events(tmp_path / "old")
    assert ev["items"] == [] and "Re-run" in ev["note"]
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="equity-journey"' in html and 'id="event-legend"' in html and 'id="event-detail"' in html
