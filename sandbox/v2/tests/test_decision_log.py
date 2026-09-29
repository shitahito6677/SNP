"""N5: บันทึก "ทำไมวันนี้ทำ/ไม่ทำ" ต่อหุ้นต่อวัน (บันทึกตอนรัน) + condition_fixed อ่านข่าว ±2 ถูก"""
import json

import pandas as pd
import pytest

from sandbox.v2 import condition_registry, config as cfg, engine, experiments_store as xs, registry
from sandbox.v2.server import create_app

BAD_DAY = "2021-09-15"  # KR (อยู่ในรายชื่อ bmf20 รอบ 2021-06-30) มีข่าว -2


@pytest.fixture()
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_NEWS", tmp_path / "manual_news.jsonl")
    c = create_app().test_client()
    for d, lab in ((BAD_DAY, -2), ("2021-10-06", 1)):
        assert c.post("/api/news", json={"headline": f"KR news {d}", "date": d, "tickers": ["KR"], "label": lab,
                                         "label_method": "real_time"}).status_code == 201
    conf, _ = engine.normalize_config({"start": "2021-06-30", "end": "2021-12-31",
                                       "stages": {"A": {"mode": "on", "version": "A:bmf20-weighted"},
                                                  "B": {"mode": "on", "version": "B:manual-labels-realtime"}},
                                       "condition": {"id": "condition_fixed"}})
    d = tmp_path / "run"
    engine.run(conf, d, log=lambda m: None)
    yield d, c
    registry.scan()


def test_condition_fixed_reads_minus2_and_sells_half(run):
    d, _ = run
    tr = pd.read_parquet(d / "trades.parquet")
    kr = tr[(tr["ticker"] == "KR") & (tr["side"] == "sell")]
    assert len(kr) >= 1 and str(kr["decision_date"].iloc[0]) == BAD_DAY  # ข่าว -2 → ขายครึ่งวันนั้นเลย (เดิมอ่านเป็น -1 → ไม่ขาย)
    r0 = kr.iloc[0]
    assert abs(r0["weight_after"] - r0["weight_before"] / 2) < 0.01
    assert any("ข่าว -2 → ขายครึ่งทันที" in x for x in r0["reasons"])


def test_decision_log_for_any_day(run):
    d, _ = run
    ans = xs.decisions(d, "KR", BAD_DAY)
    assert ans["found"] and ans["exact"]
    row = ans["row"]
    assert row["b"]["label"] == -2 and row["b"]["applicable"] is True  # ctx.b ดิบทั้งก้อน
    assert "ลดเป้า" in row["summary"] and any("ขายครึ่งทันที" in n for n in row["notes"])
    assert row["state"]["cut"]["done"] is False and "w" in row["state"]  # สถานะ cut ของหุ้นนี้ ณ วันนั้น
    later = xs.decisions(d, "KR", "2021-09-20")["row"]  # วันถัดมา: อยู่ในสถานะขายครึ่งค้าง → ข้ามการตรวจข่าว
    assert any("_is_reduced=True" in n for n in later["notes"]) and later["b"]["applicable"] is False
    wk = xs.decisions(d, "KR", "2021-09-18")  # วันเสาร์ → แสดงวันทำการก่อนหน้า
    assert not wk["exact"] and wk["row"]["date"] == "2021-09-17" and wk["note"]
    other = xs.decisions(d, "AAPL", BAD_DAY)
    assert other["available"] and not other["found"]


def test_api_and_old_results(run, tmp_path):
    d, c = run
    (tmp_path / "old").mkdir()
    assert xs.decisions(tmp_path / "old", "KR", BAD_DAY)["available"] is False  # ผลก่อน N5 → บอกให้ Re-run
    cols = pd.read_parquet(d / "decisions.parquet").columns.tolist()
    assert cols == engine.DECISION_COLS
    assert "decisions.parquet" in xs.OPTIONAL_ARTIFACTS


def test_condition_fixed_only_changes_news_parsing():
    src = condition_registry.source("condition_fixed")
    assert '"label", "score",' in src and src.index('"label", "score"') < src.index('"class", "cls"')
    html = (cfg.V2 / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="explain-panel"' in html and 'id="explain-b"' in html and 'id="explain-state"' in html
