"""Q0/Q1: ชนิดของ trade (สาเหตุ) — จาก tag ของ ctx.note และสำรองจากข้อความ note สำหรับผลเก่า"""
import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, trade_causes

DEMO = (cfg.V2 / "tests" / "fixtures" / "cause_demo_condition.py").read_text(encoding="utf-8")
SCOPE = {"mode": "tickers", "sectors": [], "tickers": ["AAPL", "MSFT", "NVDA", "KR"]}


def _run(tmp_path, src=DEMO, name="r"):
    conf, _ = engine.normalize_config({"start": "2022-01-03", "end": "2022-06-30", "scope": SCOPE,
                                       "stages": {"A": {"mode": "off", "version": None}}, "condition": {"source": src}})
    engine.run(conf, tmp_path / name, log=lambda m: None)
    return tmp_path / name


def test_demo_condition_gives_every_kind(tmp_path):
    tr = trade_causes.classify_dir(_run(tmp_path))
    got = {(r.decision_date, r.ticker): (r.kind, list(r.ref)) for r in tr.itertuples()}
    assert got[("2022-03-01", "AAPL")] == ("sell_news", [])
    assert got[("2022-03-15", "MSFT")] == ("buy_receive", ["AAPL"])
    assert got[("2022-04-01", "MSFT")] == ("sell_pullback", ["AAPL"])
    assert got[("2022-04-01", "AAPL")] == ("buy_buyback", ["MSFT"])
    first = tr["decision_date"].min()
    assert set(tr[tr["decision_date"] == first]["kind"]) == {"buy_rebalance"}
    # หุ้นที่เป้าเท่าเดิมแต่ถูกซื้อขายวันที่ AAPL ขายครึ่ง = ปรับกลับเป้า และบอกว่าเป้าของใครเปลี่ยน
    drift = tr[(tr["decision_date"] == "2022-03-01") & (tr["ticker"] != "AAPL")]
    assert len(drift) and set(drift["kind"]) == {"drift"} and all(list(r) == ["AAPL"] for r in drift["ref"])
    assert not tr["ref_inferred"].any()


def test_legacy_results_fall_back_to_note_text(tmp_path):
    """ผลก่อน Q1 ไม่มี tags_json → ใช้ข้อความ note ของ condition_fixed"""
    d = _run(tmp_path)
    dec = pd.read_parquet(d / "decisions.parquet").drop(columns=["tags_json"])
    dec.loc[(dec["ticker"] == "AAPL") & (dec["date"] == "2022-03-01"), "notes"] = pd.Series(
        [["ข่าว -2 → ขายครึ่งทันที (เงินพักเป็นเงินสด รอหุ้นข่าว +2)"]], index=dec[(dec["ticker"] == "AAPL") & (dec["date"] == "2022-03-01")].index)
    tr = pd.read_parquet(d / "trades.parquet")
    c = trade_causes.classify(tr, dec, pd.read_parquet(d / "funnel.parquet"))
    kinds = {(r.decision_date, r.ticker): x["kind"] for r, x in zip(tr.itertuples(), c)}
    assert kinds[("2022-03-01", "AAPL")] == "sell_news"
    # ข้อความ "…เพื่อซื้อคืนเต็ม" (ข้ามการตรวจข่าว) ต้องไม่ถูกนับเป็นซื้อคืน (Q0: เคยชนคำ)
    assert trade_causes._tags({"notes": ["ข้ามการตรวจข่าว: อยู่ในสถานะขายครึ่งค้างอยู่ — รอราคาลงอีก 15% จากจุดขายเพื่อซื้อคืนเต็ม"]}) == []
    assert trade_causes._tags({"notes": ["ข่าว +2 → รับเงินที่พักจากการขายครึ่งของ MU 2.50% ของพอร์ต"]})[0]["kind"] == "receive"
    assert trade_causes.classify(tr, None)[0]["kind"] == "unknown"  # ผลก่อน N5


def test_note_kind_is_validated(tmp_path):
    bad = "NAME = 'x'\nDESCRIPTION = 'x'\ndef decide(ctx):\n    ctx.note('AAPL', 'x', kind='whatever')\n    return {'AAPL': 1.0}\n"
    with pytest.raises(engine.ConditionError, match="kind="):
        _run(tmp_path, bad, "bad")


def test_kinds_cover_spec_and_ui():
    for k in ("sell_news", "sell_pullback", "buy_rebalance", "buy_receive", "drift"):
        assert k in trade_causes.KINDS
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="trade-legend"' in html and 'id="explain-trades"' in html
