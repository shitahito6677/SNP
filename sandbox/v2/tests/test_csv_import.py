"""F1: นำเข้า CSV ข่าวจริง (column ไทยผสมอังกฤษ, label -2..+2, full_news ยาว) ต้องสำเร็จทั้งไฟล์ — ไม่มี 500 ดิบ"""
import csv
import hashlib
import json

import pytest

from sandbox.v2 import config as cfg, news
from sandbox.v2.server import create_app

FIXTURE = cfg.V2 / "tests" / "fixtures" / "manual_news_sample.csv"
# ไฟล์จริงมี 10 บรรทัด = หัวตาราง 1 + ข่าว META 9 แถว
EXPECTED_ROWS = 9


def _original():
    with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_NEWS", tmp_path / "manual_news.jsonl")
    app = create_app()
    return app.test_client()


def _import(client, text, mapping=None):
    r = client.post("/api/news/csv/preview", json={"text": text, "mapping": mapping})
    assert r.status_code == 200, r.get_data(as_text=True)
    prev = r.get_json()
    c = client.post("/api/news/csv/commit", json={"rows": prev["rows"]})
    assert c.status_code == 200, c.get_data(as_text=True)
    return prev, c.get_json()


def test_real_file_imports_every_row(client):
    orig = _original()
    assert len(orig) == EXPECTED_ROWS
    prev, res = _import(client, FIXTURE.read_text(encoding="utf-8"))
    m = prev["mapping"]
    assert m["ticker"] == "ticker" and m["date"] == "วันที่ข่าวออก (publish_date)"
    assert m["headline"] == "ข่าวแบบย่อ (short_news)" and m["body"] == "ข่าวแบบเต็ม (full_news)"
    assert m["sentiment"] == "label จาก Claude (-2..+2)"
    assert prev["problems"] == [] and all(not r["skip_reasons"] for r in prev["rows"])
    assert res["saved"] == EXPECTED_ROWS and res["errors"] == []

    saved = news._load()
    assert len(saved) == EXPECTED_ROWS
    assert all(n["tickers"] == ["META"] and n["source"] == "manual" and n["kind"] == "company" for n in saved)

    # วันที่ตรงกับต้นฉบับทุกแถว และช่วง 2021-10-25 → 2023-04-26
    by_head = {n["headline"]: n for n in saved}
    for o in orig:
        n = by_head[o["ข่าวแบบย่อ (short_news)"]]
        assert n["date"] == o["วันที่ข่าวออก (publish_date)"]
        # เนื้อข่าวเต็มไม่ถูกตัด/เพี้ยน (ความยาว + checksum)
        body = o["ข่าวแบบเต็ม (full_news)"]
        assert len(n["body"]) == len(body)
        assert hashlib.sha256(n["body"].encode()).hexdigest() == hashlib.sha256(body.encode()).hexdigest()
        # column ที่ไม่รู้จัก → metadata ต่อแถว (ไม่ทิ้ง)
        assert n["extra"]["แหล่งที่มา/ลิงค์ (source_url)"] == o["แหล่งที่มา/ลิงค์ (source_url)"]
        assert n["extra"]["เหตุผลของ label (label_reason)"] == o["เหตุผลของ label (label_reason)"]
        assert n["extra"]["ชื่อหุ้น (stock_name)"] == o["ชื่อหุ้น (stock_name)"]
        # label ดิบเก็บไว้
        assert n["label_raw"] == int(o["label จาก Claude (-2..+2)"]) and n["label_scale"] == "±2"
    dates = sorted(n["date"] for n in saved)
    assert dates[0] == "2021-10-25" and dates[-1] == "2023-04-26"


def test_numeric_label_maps_to_internal_scale(client):
    _import(client, FIXTURE.read_text(encoding="utf-8"))
    saved = news._load()
    worst = min(n["score"] for n in saved)
    for n in saved:
        raw = n["label_raw"]
        assert n["sentiment"] == ("positive" if raw > 0 else "negative" if raw < 0 else "neutral")
        assert n["score"] == raw / 2
        if raw == -2:  # แย่สุดของไฟล์ → แย่สุดของระบบภายใน (-1.0 = เท่ากับข่าว negative ที่พิมพ์เอง)
            assert n["sentiment"] == "negative" and n["score"] == -1.0 == worst
    assert {n["label_raw"] for n in saved} >= {-2, -1, 1, 2}


def test_bom_and_label_scale_from_values(client):
    """BOM ข้างหน้า + หัว column ไม่บอกสเกล → เดาสเกลจากค่าในไฟล์ (max |label| = 2)"""
    text = "﻿" + FIXTURE.read_text(encoding="utf-8").replace("label จาก Claude (-2..+2)", "label")
    prev, res = _import(client, text)
    assert prev["label_scale"] == 2 and res["saved"] == EXPECTED_ROWS


def test_text_labels_and_bad_rows_are_skipped_not_fatal(client):
    text = ("Headline,Date,Symbol,Sentiment,source_url\n"
            "Apple beats,2023-02-03,AAPL,positive,http://x\n"
            "Nvidia falls,2023-02-03,NVDA,Negative,\n"
            "no ticker known,2023-02-03,ZZZZQ,neutral,\n"
            "bad date,31/31/2023,MSFT,neutral,\n"
            "weird label,2023-02-03,MSFT,maybe,\n"
            ",2023-02-03,MSFT,neutral,\n")
    prev, res = _import(client, text)
    rows = {r["row"]: r for r in prev["rows"]}
    assert rows[1]["sentiment"] == "positive" and rows[2]["sentiment"] == "negative"
    assert rows[1]["extra"] == {"source_url": "http://x"}
    assert "ZZZZQ" in rows[3]["skip_reasons"][0]
    assert rows[4]["skip_reasons"][0].startswith("วันที่อ่านไม่ได้")
    assert rows[5]["skip_reasons"][0].startswith("label อ่านไม่ได้")
    assert "ไม่มีหัวข่าว" in rows[6]["skip_reasons"]
    assert res["saved"] == 2 and res["errors"] == []


def test_mapping_override(client):
    """เดา mapping ผิด/ไม่เจอ → ผู้ใช้เลือกเองได้"""
    text = "col_a,col_b,col_c\n2023-02-03,Apple beats,AAPL\n"
    r = client.post("/api/news/csv/preview", json={"text": text}).get_json()
    assert r["mapping"]["headline"] is None and r["problems"]
    prev, res = _import(client, text, {"date": "col_a", "headline": "col_b", "ticker": "col_c"})
    assert prev["problems"] == [] and res["saved"] == 1
    bad = client.post("/api/news/csv/preview", json={"text": text, "mapping": {"headline": "nope"}})
    assert bad.status_code == 400 and "nope" in bad.get_json()["error"]


@pytest.mark.parametrize("text, msg", [("", "ไฟล์ว่าง"), ("   \n", "ไฟล์ว่าง"), ("a,a\n1,2\n", "ซ้ำ"),
                                       ("h�,date\n", "UTF-8")])
def test_unreadable_file_gives_thai_400(client, text, msg):
    r = client.post("/api/news/csv/preview", json={"text": text})
    assert r.status_code == 400 and r.is_json
    assert r.get_json()["error"].startswith("อ่านไฟล์ไม่ได้") and msg in r.get_json()["error"]


def test_malformed_request_is_json_not_html(client):
    r = client.post("/api/news/csv/preview", data="not json", content_type="application/json")
    assert r.status_code == 400 and r.is_json and "อ่านไฟล์ไม่ได้" in r.get_json()["error"]


def test_internal_error_is_logged_and_readable(client, monkeypatch, tmp_path):
    """exception ที่ไม่คาดคิด → 500 แบบ JSON ภาษาไทย + error_id + traceback เต็มใน server log (ไม่ใช่หน้า HTML ดิบ)"""
    from sandbox.v2 import server

    def boom(*a, **k):
        raise RuntimeError("simulated failure xyz")
    monkeypatch.setattr(news, "csv_preview", boom)
    r = client.post("/api/news/csv/preview", json={"text": "a\n1\n"})
    assert r.status_code == 500 and r.is_json
    j = r.get_json()
    assert "อ่านไฟล์ CSV ไม่สำเร็จ" in j["error"] and j["error_id"] in j["error"]
    log = server.LOG_FILE.read_text(encoding="utf-8")
    assert f"error_id={j['error_id']}" in log and "simulated failure xyz" in log and "Traceback" in log


def test_commit_row_errors_do_not_fail_file(client):
    rows = [{"row": 1, "include": True, "headline": "ok", "date": "2023-02-03", "tickers": ["AAPL"], "sentiment": "neutral"},
            {"row": 2, "include": True, "headline": "bad", "date": "2023-02-03", "tickers": ["NOPE1"], "sentiment": "neutral"},
            {"row": 3, "include": True, "headline": "bad date", "date": "xx", "tickers": ["AAPL"], "sentiment": "neutral"}]
    r = client.post("/api/news/csv/commit", json={"rows": rows})
    assert r.status_code == 200
    j = r.get_json()
    assert j["saved"] == 1 and [e["row"] for e in j["errors"]] == [2, 3]
    assert json.loads(cfg.MANUAL_NEWS.read_text().splitlines()[0])["headline"] == "ok"
