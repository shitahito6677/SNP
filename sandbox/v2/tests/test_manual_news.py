"""ข่าว manual: ใช้ใน pipeline เฉพาะเมื่อเปิด toggle, ติด source=manual, วันตลาดปิด → วันทำการถัดไป"""
import pytest

from sandbox.v2 import config as cfg, engine, news


@pytest.fixture()
def tmp_news(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_NEWS", tmp_path / "manual_news.jsonl")
    return tmp_path


CHECK = '''NAME = "t"
DESCRIPTION = "t"
def decide(ctx):
    b = ctx.b.get("NVDA")
    if ctx.date == "2022-03-07":
        ctx.state["seen"] = b
        if EXPECT_MANUAL:
            assert b and b.get("source") == "manual" and b["class"] == "negative", b
        else:
            assert not b or b.get("source") != "manual", b
    return {}
'''


def _run(tmp, include):
    src = CHECK.replace("EXPECT_MANUAL", str(include))
    conf, _ = engine.normalize_config({"start": "2022-02-01", "end": "2022-03-31", "include_manual": include,
                                       "stages": {"B": {"mode": "on", "version": "B:stub"}},
                                       "condition": {"source": src}})
    return engine.run(conf, tmp / f"run{include}", log=lambda m: None)


def test_manual_news_only_when_toggled(tmp_news):
    row = news.add({"headline": "NVDA manual test", "date": "2022-03-05", "tickers": ["NVDA"], "sentiment": "negative"})
    assert row["source"] == "manual" and row["effective_date"] == "2022-03-07"  # เสาร์ → จันทร์
    _run(tmp_news, True)
    _run(tmp_news, False)


def test_manual_news_never_touches_training_data(tmp_news):
    news.add({"headline": "x", "date": "2022-03-07", "sectors": ["XLK"], "sentiment": "positive"})
    assert cfg.MANUAL_NEWS.parent == tmp_news
    assert "data/raw" not in str(cfg.MANUAL_NEWS) and "data/processed" not in str(cfg.MANUAL_NEWS)


def test_add_requires_target(tmp_news):
    with pytest.raises(ValueError):
        news.add({"headline": "no target", "date": "2022-03-07"})
