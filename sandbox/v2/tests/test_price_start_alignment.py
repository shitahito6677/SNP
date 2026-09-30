"""J1: วันเริ่มซื้อขาย = รอบ rebalance จริงของ A1 · ราคา warm-up ก่อนหน้า 90 วันทำการ (ไม่ซื้อขาย ไม่นับในผล)
ผลการทดลองเก่า (ไม่มี warm-up) รันซ้ำได้ค่าเดิม"""
import json

import pandas as pd
import pytest

from sandbox.v2 import config as cfg, engine, experiments_store as xs, prices

A1 = "A:A1_r001_Q_LOWACC_overall"


def _a1_dates():
    s = pd.read_parquet(cfg.REPO / "model_A" / "export" / cfg.ANCHOR_A_VERSION / "signals.parquet", columns=["date"])
    return sorted(pd.to_datetime(s["date"]).unique())


@pytest.mark.parametrize("today, want", [
    ("2026-09-28", "2021-06-30"),   # วันนี้จริง: ideal 2021-09-28 → รอบล่าสุดที่ ≤ ideal
    ("2027-08-15", "2022-06-30"),
    ("2026-03-01", "2020-06-30"),
    ("2016-01-01", "2011-06-30"),   # ไม่มีรอบก่อน ideal (2011-01-01) → รอบแรกหลังจากนั้น
    ("2031-01-01", "2022-06-30"),   # ไม่เลือกรอบใน held-out (A1 ไม่มีรอบหลัง 2022-06 อยู่แล้ว)
])
def test_decision_start_is_a_real_A1_rebalance(today, want):
    d = cfg.compute_start_dates(today=today)
    assert d["decision_start"] == want
    assert pd.Timestamp(d["decision_start"]) in set(_a1_dates())  # วันจริงจากไฟล์ ไม่ใช่วันกลางอากาศ


def test_held_out_rounds_are_skipped_unless_allowed():
    rs = ["2021-06-30", "2022-06-30", "2023-07-03", "2024-06-28"]  # 2023-07-03 อยู่ใน held-out (≥ 2023-07-01)
    assert cfg.compute_start_dates(today="2029-08-01", rebalance_dates=rs)["decision_start"] == "2022-06-30"
    assert cfg.compute_start_dates(today="2029-08-01", rebalance_dates=rs, allow_held_out=True)["decision_start"] == "2024-06-28"


def test_price_start_is_exactly_90_trading_days_before():
    d = cfg.compute_start_dates(today="2026-09-28")
    cal = prices.calendar(prices.data_start(), "2023-06-30")
    i = cal.get_loc(pd.Timestamp(d["decision_start"]))
    assert d["warmup_exact"] and pd.Timestamp(d["price_start"]) == cal[i - 90]
    assert cfg.PRICE_START == d["price_start"] and cfg.DECISION_START == d["decision_start"]  # ค่าที่ระบบใช้จริง
    assert prices.data_start() <= pd.Timestamp(cfg.PRICE_START)  # มีราคา warm-up ครบในเครื่อง


def test_default_run_starts_at_rebalance_with_warmup():
    conf, w = engine.normalize_config({"stages": {"A": {"mode": "on", "version": A1}}, "condition": {"id": "equal_weight_A"}})
    assert conf["start"] == cfg.DECISION_START
    assert conf["warmup"] == {"days": 90, "requested": 90, "start": cfg.PRICE_START,
                              "end": str(prices.calendar(cfg.PRICE_START, cfg.DECISION_START)[-2].date())}
    assert not any(x.startswith("WARMUP") for x in w)
    conf, w = engine.normalize_config({"start": str(prices.data_start().date()), "condition": {"id": "equal_weight_A"}})
    assert conf["warmup"]["days"] == 0 and any(x.startswith("WARMUP") for x in w)  # ไม่มีราคาก่อนหน้า → เตือน ไม่พัง


INDICATOR_CHECK = '''NAME = "indicator check"
DESCRIPTION = "วันแรกต้องคำนวณ SMA50/EMA20/RSI14 ได้"
import pandas as pd
def decide(ctx):
    if "first" not in ctx.state:
        ctx.state["first"] = ctx.date
        for t in ["SPY"] + sorted(ctx.universe)[:5]:
            h = ctx.history(t, 90)
            assert len(h.dropna()) >= 60, (t, ctx.date, len(h.dropna()))
            sma50 = h.rolling(50).mean().iloc[-1]
            ema20 = h.ewm(span=20, adjust=False).mean().iloc[-20:].iloc[-1]
            d = h.diff(); up = d.clip(lower=0).rolling(14).mean().iloc[-1]; dn = (-d.clip(upper=0)).rolling(14).mean().iloc[-1]
            rsi = 100 - 100 / (1 + up / dn)
            assert pd.notna(sma50) and pd.notna(ema20) and pd.notna(rsi), (t, sma50, ema20, rsi)
        ctx.note("SPY", "indicators ok")
    names = sorted(ctx.universe)
    return {t: 1 / len(names) for t in names} if names else {}
'''


def test_indicators_ready_on_decision_start_and_no_avoidable_cash_gap(tmp_path):
    conf, _ = engine.normalize_config({"stages": {"A": {"mode": "on", "version": A1}}, "condition": {"source": INDICATOR_CHECK}})
    engine.run(conf, tmp_path / "all", log=lambda m: None)  # condition assert ใน process แยก — ไม่ผ่าน = run ล้ม
    tr = pd.read_parquet(tmp_path / "all" / "trades.parquet")
    eq = pd.read_parquet(tmp_path / "all" / "equity.parquet")
    cal = prices.calendar(conf["start"], conf["end"])
    assert str(eq["date"].iloc[0].date()) == cfg.DECISION_START  # warm-up ไม่อยู่ใน equity/metrics
    assert tr["date"].min() == cal[1] and tr["decision_date"].min() == cfg.DECISION_START  # ซื้อวันทำการถัดจากรอบ rebalance ทันที
    prov = json.loads((tmp_path / "all" / "provenance.json").read_text())
    assert prov["warmup_data_hash"]


def test_meta_gap_is_the_models_choice_not_the_start_date(tmp_path):
    """scope META: A1 ไม่เลือก META ในรอบ 2021-06-30 (not_selected) → ถือเงินสดจนรอบ 2022-06-30 ที่เลือก — ซื้อวันทำการถัดไปทันที"""
    s = pd.read_parquet(cfg.REPO / "model_A" / "export" / cfg.ANCHOR_A_VERSION / "signals.parquet")
    meta = s[s["ticker"] == "META"].set_index("date")["class"]
    assert meta[pd.Timestamp("2021-06-30")] == "not_selected" and meta[pd.Timestamp("2022-06-30")] == "selected"
    conf, _ = engine.normalize_config({"stages": {"A": {"mode": "on", "version": A1}}, "scope": {"mode": "tickers", "tickers": ["META"]},
                                       "condition": {"id": "equal_weight_A"}})
    engine.run(conf, tmp_path / "meta", log=lambda m: None)
    tr = pd.read_parquet(tmp_path / "meta" / "trades.parquet")
    assert tr["decision_date"].min() == "2022-06-30" and str(tr["date"].min().date()) == "2022-07-01"


@pytest.mark.parametrize("exp_id", [e["id"] for e in xs.list_all()])
def test_saved_experiments_rerun_identically(exp_id, tmp_path):
    """ผลที่บันทึกก่อน J1 (ไม่มี warm-up, วันเริ่มแบบเดิม): รันซ้ำด้วยเส้นทางเดียวกับปุ่ม Re-run → metrics + equity ตรงเดิมทุกค่า"""
    d = xs.path(exp_id)
    conf = json.loads((d / "config.json").read_text())
    if (conf.get("warmup") or {}).get("days"):
        pytest.skip("ผลหลัง J1 (มี warm-up)")
    conf.setdefault("warmup", {"days": 0})
    conf["condition"] = {"id": conf["condition"].get("id"), "source": (d / "condition_snapshot.py").read_text(encoding="utf-8")}
    try:
        c2, _ = engine.normalize_config(conf)
    except engine.LegacyConfigError:
        pytest.skip("config แบบกล่องเดิมที่ต้องยืนยันก่อนรันซ้ำ (G1)")
    engine.run(c2, tmp_path / "rerun", log=lambda m: None)
    diff = xs.diff_runs(d, tmp_path / "rerun")
    assert diff["identical"], diff
