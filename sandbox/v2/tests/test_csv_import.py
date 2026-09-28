"""F1: นำเข้า CSV ข่าวจริง (column ไทยผสมอังกฤษ, label -2..+2, full_news ยาว) ต้องสำเร็จทั้งไฟล์ — ไม่มี 500 ดิบ"""
import csv
import hashlib
import json

import pandas as pd
import pytest

from sandbox.v2 import config as cfg, news
from sandbox.v2.server import create_app

FIXTURE = cfg.V2 / "tests" / "fixtures" / "manual_news_sample.csv"
# ไฟล์จริงมี 10 บรรทัด = หัวตาราง 1 + ข่าว META 9 แถว
EXPECTED_ROWS = 9
# ไฟล์จริงชุดใหญ่ (20 แถว, 7 ticker) — มี label ครบทั้ง 5 ระดับ (-2, -1, 0, 1, 2)
FIVE = cfg.V2 / "tests" / "fixtures" / "manual_news_5levels.csv"
LABEL_COL = "label จาก Claude (-2..+2)"


def _original_of(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _original():
    return _original_of(FIXTURE)


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
        # label -2..+2 เป็นฟิลด์หลัก (ค่าในไฟล์ตรงกับสเกลระบบ จึงไม่ต้องมี label_raw ซ้ำ)
        assert n["label"] == int(o[LABEL_COL]) and "label_raw" not in n and "sentiment" not in n
    dates = sorted(n["date"] for n in saved)
    assert dates[0] == "2021-10-25" and dates[-1] == "2023-04-26"


def test_five_label_levels_are_kept_distinct(client):
    """label 5 ระดับ ต้องไม่ถูกยุบเป็น 3 กลุ่ม: preview → บันทึก → signal (ctx.b) → chip ใน trade reasons → hover หน้าหุ้น"""
    from sandbox.v2 import engine, signals, stock_view

    orig = _original_of(FIVE)
    want = [int(o[LABEL_COL]) for o in orig]
    assert set(want) == {-2, -1, 0, 1, 2}
    prev, res = _import(client, FIVE.read_text(encoding="utf-8"))
    assert [r["label"] for r in prev["rows"]] == want and res["saved"] == len(orig)
    saved = news._load()
    assert sorted(n["label"] for n in saved) == sorted(want)

    # signal ที่ condition เห็น (ctx.b) + class 3 กลุ่มที่ derive เฉพาะเพื่อเกณฑ์กรองแบบ Model B
    recs = signals.load_manual_news("b")
    by = {}
    for r in recs:
        by.setdefault(r["label"], r)
    assert set(by) == {-2, -1, 0, 1, 2}
    assert [by[v]["class"] for v in (-2, -1, 0, 1, 2)] == ["negative", "negative", "neutral", "positive", "positive"]
    assert [by[v]["score"] for v in (-2, -1, 0, 1, 2)] == [-2.0, -1.0, 0.0, 1.0, 2.0]  # สัญญา B: score = label -2..+2
    texts = [by[v]["label_text"] for v in (-2, -1, 0, 1, 2)]
    assert len(set(texts)) == 5 and texts[0] == "negative แรงมาก" and texts[4] == "positive แรงมาก"
    assert len({by[v]["reasons"][0].split("]")[0] for v in by}) == 5  # "[−2 negative แรงมาก]" ≠ "[−1 negative]" …

    # chip ใน trade reasons แยก 5 ระดับ
    chips = {v: engine._chip("B", "B stub", by[v]) for v in by}
    assert len(set(c.split(" · ")[0] for c in chips.values())) == 5
    assert "label -2 negative แรงมาก" in chips[-2] and "label +2 positive แรงมาก" in chips[2] and "label +1 positive ·" in chips[1]

    # hover หน้าหุ้น: MSFT มี label 0 และ +1, META มี -2 -1 +1 +2
    meta = stock_view.build("META")["layers"]["manual"]
    msft = stock_view.build("MSFT")["layers"]["manual"]
    got = {m["label"]: m["label_text"] for m in meta + msft}
    assert got == {v: news.LABELS[v] for v in (-2, -1, 0, 1, 2)}


def test_label_reaches_condition_and_trade_reasons(client, tmp_path):
    """condition อ่าน ctx.b[t]["label"] ได้ และ reasons ของ trade แสดงความแรงต่างกัน (ไม่ใช่ 'positive' เหมือนกันหมด)"""
    from sandbox.v2 import engine

    _import(client, FIXTURE.read_text(encoding="utf-8"))  # META: -2 -1 +1 +2
    src = '''NAME = "label test"
DESCRIPTION = "ถือ META ตามความแรงของข่าว manual"
def decide(ctx):
    b = ctx.b.get("META")
    if not b or b.get("source") != "manual":
        return None
    assert b["label"] in (-2, -1, 1, 2) and isinstance(b["label"], int), b
    return {"META": {2: 1.0, 1: 0.5}.get(b["label"], 0.0)}
'''
    conf, _ = engine.normalize_config({"include_manual": True, "stages": {"B": {"mode": "on", "version": "B:stub"}},
                                       "condition": {"source": src}})
    engine.run(conf, tmp_path / "run", log=lambda m: None)
    tr = pd.read_parquet(tmp_path / "run" / "trades.parquet")
    manual = [c for rs in tr["reasons"] for c in rs if "[MANUAL]" in c]
    seen = {lab for lab in (-2, -1, 1, 2) for c in manual if f"label {lab:+d} " in c}
    assert seen == {-2, -1, 1, 2}, manual[:6]


def test_other_numeric_scale_is_mapped_to_five_levels(client):
    text = "Headline,Date,Ticker,score (-1..+1)\nA,2023-02-03,AAPL,-1\nB,2023-02-03,AAPL,-0.4\nC,2023-02-03,AAPL,0\nD,2023-02-03,AAPL,0.5\nE,2023-02-03,AAPL,1\n"
    prev = client.post("/api/news/csv/preview", json={"text": text, "mapping": {"headline": "Headline", "date": "Date", "ticker": "Ticker",
                                                                             "sentiment": "score (-1..+1)"}}).get_json()
    assert [r["label"] for r in prev["rows"]] == [-2, -1, 0, 1, 2]
    client.post("/api/news/csv/commit", json={"rows": prev["rows"]})
    saved = news._load()
    assert [n["label"] for n in saved] == [-2, -1, 0, 1, 2] and saved[1]["label_raw"] == -0.4


def test_manual_form_label_and_legacy_rows(client):
    """ฟอร์มพิมพ์เองส่ง label -2..+2 ได้; ข่าวเก่าที่มีแค่ sentiment → +1/0/-1; label ผิดรูป → 400"""
    assert client.post("/api/news", json={"headline": "x", "date": "2023-02-03", "tickers": ["AAPL"], "label": -2}).get_json()["label"] == -2
    assert client.post("/api/news", json={"headline": "y", "date": "2023-02-03", "tickers": ["AAPL"], "sentiment": "positive"}).get_json()["label"] == 1
    assert news.label_of({"sentiment": "negative"}) == -1 and news.label_of({}) == 0
    for bad in (3, 1.5, "abc"):
        r = client.post("/api/news", json={"headline": "z", "date": "2023-02-03", "tickers": ["AAPL"], "label": bad})
        assert r.status_code == 400 and "-2..+2" in r.get_json()["error"]


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
    assert rows[1]["label"] == 1 and rows[2]["label"] == -1
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
    rows = [{"row": 1, "include": True, "headline": "ok", "date": "2023-02-03", "tickers": ["AAPL"], "label": 0},
            {"row": 2, "include": True, "headline": "bad", "date": "2023-02-03", "tickers": ["NOPE1"], "sentiment": "neutral"},
            {"row": 3, "include": True, "headline": "bad date", "date": "xx", "tickers": ["AAPL"], "sentiment": "neutral"}]
    r = client.post("/api/news/csv/commit", json={"rows": rows})
    assert r.status_code == 200
    j = r.get_json()
    assert j["saved"] == 1 and [e["row"] for e in j["errors"]] == [2, 3]
    assert json.loads(cfg.MANUAL_NEWS.read_text().splitlines()[0])["headline"] == "ok"


def test_rows_saved_by_first_f1_format_keep_their_strength(client):
    """ข่าวที่นำเข้าช่วง F1 แรก (เก็บ sentiment 3 กลุ่ม + label_raw/label_scale) และข่าวพิมพ์เองรุ่นเก่า (sentiment อย่างเดียว)
    ต้องอ่านกลับได้ความแรงเดิม — ไม่ยุบ ±2 เป็น ±1 และไม่ต้องแก้ไฟล์เดิม"""
    from sandbox.v2 import signals, stock_view

    legacy = [dict(id=f"x{v}", source="manual", headline=f"h{v}", body="", date="2022-02-02", effective_date="2022-02-02",
                   kind="company", tickers=["META"], sectors=[], sentiment=news.label_class(v), score=v / 2,
                   label_raw=v, label_scale="±2", deleted=False) for v in (-2, -1, 0, 1, 2)]
    legacy.append(dict(id="old", source="manual", headline="typed", body="", date="2022-02-03", effective_date="2022-02-03",
                       kind="company", tickers=["META"], sectors=[], sentiment="negative", score=-1.0, deleted=False))
    news._write(legacy)
    before = cfg.MANUAL_NEWS.read_bytes()
    assert [news.label_of(n) for n in legacy] == [-2, -1, 0, 1, 2, -1]
    assert sorted(r["label"] for r in signals.load_manual_news("b")) == [-2, -1, -1, 0, 1, 2]
    assert sorted(m["label"] for m in stock_view.build("META")["layers"]["manual"]) == [-2, -1, -1, 0, 1, 2]
    assert sorted(n["label"] for n in client.get("/api/news").get_json()) == [-2, -1, -1, 0, 1, 2]
    assert cfg.MANUAL_NEWS.read_bytes() == before  # อ่านอย่างเดียว ไม่เขียนทับ
