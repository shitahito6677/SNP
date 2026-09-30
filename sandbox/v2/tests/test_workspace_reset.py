"""N1: ล้างข้อมูลทดลองต้อง backup ครบก่อนลบ และกู้คืนได้"""
import json
import shutil

import pytest

from sandbox.v2 import config as cfg, workspace
from sandbox.v2.server import create_app


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    for name in ("conditions", "experiments", "backups"):
        (tmp_path / name).mkdir()
    for p in cfg.CONDITIONS_DIR.glob("*.py"):
        if p.stem in workspace.SYSTEM_CONDITIONS:
            shutil.copy2(p, tmp_path / "conditions" / p.name)
    (tmp_path / "conditions" / "my_rule.py").write_text('NAME = "x"\nDESCRIPTION = "x"\ndef decide(ctx):\n    return {}\n')
    exp = tmp_path / "experiments" / "20260101-000000_mine"
    exp.mkdir()
    (exp / "config.json").write_text("{}")
    news = tmp_path / "manual_news.jsonl"
    news.write_text(json.dumps({"id": "n1", "headline": "h", "tickers": ["AAPL"], "date": "2022-01-03", "deleted": False}, ensure_ascii=False) + "\n")
    monkeypatch.setattr(cfg, "CONDITIONS_DIR", tmp_path / "conditions")
    monkeypatch.setattr(cfg, "EXPERIMENTS_DIR", tmp_path / "experiments")
    monkeypatch.setattr(cfg, "MANUAL_NEWS", news)
    monkeypatch.setattr(workspace, "BACKUP_ROOT", tmp_path / "backups")
    return tmp_path


def test_reset_backs_up_then_clears_and_restores(ws):
    assert workspace.plan()["conditions"] == ["my_rule.py"] and workspace.plan()["news"] == 1
    with pytest.raises(PermissionError):
        workspace.reset("yes")
    raw = cfg.MANUAL_NEWS.read_bytes()
    res = workspace.reset(workspace.CONFIRM_TEXT)
    assert res["after"] == dict(res["after"], news=0, conditions=[], experiments=[])
    d = next((ws / "backups").iterdir())
    assert (d / "manual_news.jsonl").read_bytes() == raw and list(d.glob("manual_news_backup_*.csv"))
    assert (d / f"conditions_backup_{d.name}" / "my_rule.py").exists()
    assert (d / f"experiments_backup_{d.name}" / "20260101-000000_mine" / "config.json").exists()
    assert {p.stem for p in cfg.CONDITIONS_DIR.glob("*.py")} == workspace.SYSTEM_CONDITIONS & {p.stem for p in cfg.CONDITIONS_DIR.glob("*.py")}
    assert (cfg.CONDITIONS_DIR / "equal_weight_A.py").exists()  # template ของระบบยังอยู่
    r = workspace.restore(d)
    assert r == {"news": 1, "conditions_restored": 1, "experiments_restored": 1}


def test_api_requires_confirm(ws):
    c = create_app().test_client()
    assert c.get("/api/workspace").get_json()["confirm_text"] == workspace.CONFIRM_TEXT
    assert c.post("/api/workspace/reset", json={"confirm": "nope"}).status_code == 400
    assert workspace.plan()["news"] == 1
