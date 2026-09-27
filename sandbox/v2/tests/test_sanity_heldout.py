"""sanity (hold_SPY = SPY buy & hold − cost) + held-out guard"""
import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, prices


def test_hold_spy_equals_buy_and_hold_minus_cost(tmp_path):
    conf, _ = engine.normalize_config({"condition": {"id": "hold_SPY"}})
    engine.run(conf, tmp_path / "run", log=lambda m: None)
    eq = pd.read_parquet(tmp_path / "run" / "equity.parquet").set_index("date")["strategy"]
    # คำนวณอิสระจากไฟล์ราคาโดยตรง (ไม่ใช้โค้ด benchmark ของ engine): ตัดสินใจวันแรก → ซื้อ close วันที่สอง
    spy = pd.read_parquet(cfg.PRICES_DIR / "SPY.parquet")["Adj Close"].loc[conf["start"]:conf["end"]]
    spy = spy.reindex(eq.index)
    expected = conf["capital"] / (1 + conf["cost"]) * spy / spy.iloc[1]
    expected.iloc[0] = conf["capital"]
    rel = (eq / expected - 1).abs().max()
    assert rel < 1e-4, f"ต่างจาก SPY buy&hold − cost {rel:.2e} (เกณฑ์ < 0.01%)"
    trades = pd.read_parquet(tmp_path / "run" / "trades.parquet")
    assert len(trades) == 1 and trades.iloc[0]["ticker"] == "SPY" and trades.iloc[0]["side"] == "buy"
    assert pd.Timestamp(trades.iloc[0]["date"]) == eq.index[1]  # next_close


def test_held_out_requires_toggle_and_text():
    body = {"condition": {"id": "hold_SPY"}, "end": "2023-12-29"}
    with pytest.raises(prices.HeldOutError):
        engine.normalize_config(body)
    with pytest.raises(prices.HeldOutError):
        engine.normalize_config({**body, "held_out": {"enabled": True, "confirm": "yes"}})
    with pytest.raises(prices.HeldOutError):
        engine.normalize_config({**body, "held_out": {"enabled": False, "confirm": cfg.HELD_OUT_CONFIRM_TEXT}})
    conf, _ = engine.normalize_config({**body, "held_out": {"enabled": True, "confirm": cfg.HELD_OUT_CONFIRM_TEXT}})
    assert conf["held_out"]["touched"] is True


def test_default_end_is_not_held_out():
    conf, _ = engine.normalize_config({"condition": {"id": "hold_SPY"}})
    assert conf["end"] == cfg.DEFAULT_END and conf["held_out"]["touched"] is False


def test_price_loader_guard():
    with pytest.raises(prices.HeldOutError):
        prices.load("adj", ["SPY"], "2023-01-03", cfg.HELD_OUT_START)
    assert prices.load("adj", ["SPY"], "2023-01-03", cfg.DEFAULT_END).index.max() <= pd.Timestamp(cfg.DEFAULT_END)


def test_held_out_run_is_flagged(tmp_path):
    conf, _ = engine.normalize_config({"condition": {"id": "hold_SPY"}, "start": "2023-05-01", "end": "2023-08-31",
                                       "held_out": {"enabled": True, "confirm": cfg.HELD_OUT_CONFIRM_TEXT}})
    out = engine.run(conf, tmp_path / "run", log=lambda m: None)
    assert out["provenance"]["held_out_touched"] is True
    assert out["metrics"]["pre_held_out"] and out["metrics"]["held_out"]
