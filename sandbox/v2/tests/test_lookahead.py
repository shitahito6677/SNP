"""look-ahead guard: condition/signal ห้ามเห็นข้อมูลที่วันที่ > t"""
import numpy as np
import pandas as pd
import pytest

from sandbox.v2 import engine, registry
from sandbox.v2.signals import AsOf

WIN = {"start": "2022-01-03", "end": "2022-03-31"}
A1 = "A:A1_r001_Q_LOWACC_overall"
ALL_ON = {"A": {"mode": "on", "version": A1}, "B": {"mode": "on", "version": "B:stub"},
          "C": {"mode": "on", "version": "C:rulebase-exp03"}}


def run_src(tmp_path, src, stages=None, **kw):
    conf, _ = engine.normalize_config({**WIN, **kw, "stages": stages or {}, "condition": {"source": src}})
    return engine.run(conf, tmp_path / "run", log=lambda m: None)


HEADER = 'NAME = "t"\nDESCRIPTION = "t"\nimport pandas as pd\n'


def test_history_future_end_is_blocked(tmp_path):
    src = HEADER + "def decide(ctx):\n    ctx.history('SPY', 5, end=pd.Timestamp(ctx.date) + pd.Timedelta(days=10))\n    return {}\n"
    with pytest.raises(engine.ConditionError, match="LookAheadError"):
        run_src(tmp_path, src)


def test_history_never_past_decision_date(tmp_path):
    src = HEADER + (
        "def decide(ctx):\n"
        "    for t in ['SPY', 'AAPL', 'NVDA']:\n"
        "        h = ctx.history(t, 0)\n"
        "        assert h.index.max() <= pd.Timestamp(ctx.date), (t, h.index.max(), ctx.date)\n"
        "    assert max(ctx._env['hist'].dates) <= pd.Timestamp(ctx.date)\n"  # แม้แอบดู object ภายใน ก็ไม่มีอนาคต
        "    return {}\n")
    run_src(tmp_path, src)


def test_signals_passed_to_condition_are_not_future(tmp_path):
    src = HEADER + (
        "def decide(ctx):\n"
        "    d = pd.Timestamp(ctx.date)\n"
        "    for box in (ctx.a, ctx.b, dict(ctx.c)):\n"
        "        for k, r in box.items():\n"
        "            if r.get('date') is None:  # B ไม่มีข่าว ณ วันนี้ = record 'ไม่มีข้อมูล' (ไม่มีวันที่ ไม่ใช่สัญญาณ)\n"
        "                assert r['applicable'] is False and r['score'] is None, r\n"
        "                continue\n"
        "            assert pd.Timestamp(r['date']) <= d, ('future signal', k, r['date'], ctx.date)\n"
        "    return {}\n")
    run_src(tmp_path, src, stages=ALL_ON)


@pytest.mark.parametrize("vid", [A1, "A:A5_r004_C_SHYQMOM_overall_W_CAP", "B:stub", "C:rulebase-exp03", "C:stub"])
def test_asof_never_returns_future(vid):
    a = AsOf(vid)
    key = registry.get(vid)["key"]
    keys = registry.signals(vid)[key].astype(str).unique()[:40]
    rng = np.random.default_rng(0)
    for t in pd.to_datetime(rng.integers(pd.Timestamp("2012-01-01").value, pd.Timestamp("2026-06-01").value, 60)):
        for k in keys:
            r = a.at(k, t)
            assert r is None or pd.Timestamp(r["date"]) <= t
        if a.kind == "rebalance":
            assert all(pd.Timestamp(r["date"]) <= t for r in a.snapshot(t).values())


def test_model_a_has_no_signal_after_valid_through():
    a = AsOf(A1)
    assert a.snapshot(pd.Timestamp("2023-06-30"))  # วันสุดท้ายก่อน held-out ยังมี
    assert a.snapshot(pd.Timestamp("2023-07-03")) == {}  # held-out ของ Model A ล็อก → ไม่มีข้อมูล (ไม่ carry รอบเก่า)
