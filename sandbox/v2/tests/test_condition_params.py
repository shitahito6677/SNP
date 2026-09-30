"""Q2: ค่าที่ปรับได้ของ condition (PARAMS) — ตรวจชนิด/ช่วง, ส่งเข้า decide จริง, บันทึกในผล, condition ที่ไม่มี PARAMS config เหมือนเดิม"""
import json

import pandas as pd
import pytest

from sandbox.v2 import condition_registry as cr, engine
from sandbox.v2.server import create_app

SRC = '''NAME = "p"
DESCRIPTION = "p"
W = 1
MODE = "a"
PARAMS = {"W": {"type": "int", "default": 1, "min": 1, "max": 4, "label": "จำนวน", "help": "h"},
          "MODE": {"type": "choice", "default": "a", "choices": ["a", "b"], "label": "โหมด", "help": "h"}}
def decide(ctx):
    ctx.note("AAPL", f"W={W} MODE={MODE}")
    return {"AAPL": 0.25 * W}
'''
BASE = {"start": "2022-01-03", "end": "2022-01-31", "scope": {"mode": "tickers", "sectors": [], "tickers": ["AAPL", "MSFT"]},
        "stages": {"A": {"mode": "off", "version": None}}}


def test_params_parsed_and_validated():
    spec = cr.static_check(SRC)["params"]
    assert list(spec) == ["W", "MODE"] and spec["W"]["default"] == 1
    assert cr.resolve_params(spec, None) == {"W": 1, "MODE": "a"}
    assert cr.resolve_params(spec, {"W": "3", "MODE": "b"}) == {"W": 3, "MODE": "b"}
    for bad in ({"W": 9}, {"W": 1.5}, {"W": "x"}, {"MODE": "c"}, {"NOPE": 1}):
        with pytest.raises(ValueError):
            cr.resolve_params(spec, bad)
    assert not cr.static_check(SRC.replace('"default": 1,', '"default": W,'))["ok"]  # ต้องเป็นตัวอักษรล้วน


def test_params_reach_decide_and_are_recorded(tmp_path):
    conf, _ = engine.normalize_config(dict(BASE, condition={"source": SRC, "params": {"W": 3, "MODE": "b"}}))
    assert conf["condition"]["params"] == {"W": 3, "MODE": "b"}
    engine.run(conf, tmp_path / "r", log=lambda m: None)
    dec = pd.read_parquet(tmp_path / "r" / "decisions.parquet")
    assert "W=3 MODE=b" in list(dec[dec["ticker"] == "AAPL"]["notes"].iloc[0])
    assert json.loads((tmp_path / "r" / "config.json").read_text())["condition"]["params"] == {"W": 3, "MODE": "b"}
    tr = pd.read_parquet(tmp_path / "r" / "trades.parquet")
    assert abs(tr.iloc[0]["weight_after"] - 0.75) < 1e-6
    with pytest.raises(engine.ConfigError, match="ต้องอยู่ระหว่าง"):
        engine.normalize_config(dict(BASE, condition={"source": SRC, "params": {"W": 0}}))


def test_condition_without_params_config_unchanged():
    conf, _ = engine.normalize_config(dict(BASE, condition={"id": "equal_weight_A"}))
    assert "params" not in conf["condition"]


def test_condition_fixed_exposes_ma_and_help_says_only_minus1():
    spec = cr.static_check(cr.source("condition_fixed"))["params"]
    assert spec["MA_DAYS"]["default"] == 50 and spec["MA_TYPE"]["choices"] == ["SMA", "EMA"]
    for k in ("MA_DAYS", "MA_TYPE"):
        assert "ใช้แค่จังหวะยืนยันข่าว -1" in spec[k]["help"] and "SELL → คืนให้" in spec[k]["help"]
    r = create_app().test_client().get("/api/conditions/condition_fixed").get_json()
    assert r["params"]["MA_DAYS"]["max"] == 250
