"""K1: นำเข้าไฟล์ CSV ที่โตขึ้นเรื่อย ๆ ซ้ำทั้งไฟล์ — ข่าวซ้ำเป๊ะ (hash ตรง) ข้ามอัตโนมัติ, แถวใหม่เข้า, เกือบซ้ำให้ผู้ใช้ตัดสิน"""
import csv
import io
import json
import time

import pytest

from sandbox.v2 import config as cfg, news, prices
from sandbox.v2.server import create_app

FIXTURE = cfg.V2 / "tests" / "fixtures" / "manual_news_sample.csv"
N_FIXTURE = 9  # หัวตาราง 1 + ข่าว META 9 แถว


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_NEWS", tmp_path / "manual_news.jsonl")
    return create_app().test_client()


def _rows(path=FIXTURE):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        return rd.fieldnames, list(rd)


def _csv(fields, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _import(client, text, actions=None):
    prev = client.post("/api/news/csv/preview", json={"text": text}).get_json()
    rows = prev["rows"]
    for r in rows:  # ทำเหมือน UI: ส่งทุกแถวกลับ (รวมแถวซ้ำ) — server ต้องข้ามเองได้
        if actions and r["row"] in actions:
            r["dup_action"] = actions[r["row"]]
            r["include"] = actions[r["row"]] in ("replace", "keep_both")
    res = client.post("/api/news/csv/commit", json={"rows": rows}).get_json()
    return prev, res


def _live():
    return [r for r in news._load() if not r.get("deleted")]


def test_reimport_same_file_skips_everything_silently(client):
    text = FIXTURE.read_text(encoding="utf-8")
    prev, res = _import(client, text)
    assert prev["dup_summary"]["new"] == N_FIXTURE and res["saved"] == N_FIXTURE
    prev, res = _import(client, text)
    assert prev["dup_summary"] == {"new": 0, "exact": N_FIXTURE, "review": 0, "invalid": 0}
    assert all(r["dup_action"] == "skip" and not r["include"] for r in prev["rows"])  # ไม่มีอะไรให้ผู้ใช้ต้องเลือก
    assert res["saved"] == 0 and res["skipped_exact"] == N_FIXTURE and res["review_pending"] == 0
    assert len(_live()) == N_FIXTURE


def test_growing_file_imports_only_new_rows(client):
    fields, rows = _rows()
    _import(client, _csv(fields, rows))
    extra = [dict(rows[0], **{"ticker": "AAPL", "ชื่อหุ้น (stock_name)": "Apple Inc. (AAPL)",
                              "ข่าวแบบย่อ (short_news)": "Apple unveils new product line", "วันที่ข่าวออก (publish_date)": "2022-09-07"}),
             dict(rows[0], **{"ticker": "MSFT", "ชื่อหุ้น (stock_name)": "Microsoft (MSFT)",
                              "ข่าวแบบย่อ (short_news)": "Microsoft cloud revenue beats", "วันที่ข่าวออก (publish_date)": "2022-10-25"})]
    prev, res = _import(client, _csv(fields, rows + extra))
    assert prev["dup_summary"]["new"] == 2 and prev["dup_summary"]["exact"] == N_FIXTURE and prev["dup_summary"]["review"] == 0
    assert res["saved"] == 2 and res["skipped_exact"] == N_FIXTURE
    assert len(_live()) == N_FIXTURE + 2  # 11 ไม่ใช่ 20
    prev, res = _import(client, _csv(fields, rows + extra))  # import ไฟล์ที่โตแล้วซ้ำอีก → ไม่มีอะไรใหม่
    assert res["saved"] == 0 and res["skipped_exact"] == N_FIXTURE + 2


def test_case_and_whitespace_variants_are_exact(client):
    fields, rows = _rows()
    _import(client, _csv(fields, rows))
    col = "ข่าวแบบย่อ (short_news)"
    rows2 = [dict(r, **{col: "  " + "   ".join(r[col].upper().split()) + " "}) for r in rows]
    prev, res = _import(client, _csv(fields, rows2))
    assert prev["dup_summary"]["exact"] == N_FIXTURE and res["saved"] == 0


def test_same_ticker_and_date_different_headline_needs_review(client):
    fields, rows = _rows()
    _import(client, _csv(fields, rows))
    col = "ข่าวแบบย่อ (short_news)"
    alt = dict(rows[1], **{col: "Meta shares plunge after results (different wording)"})  # META 2022-02-02
    prev, res = _import(client, _csv(fields, [alt]))
    r = prev["rows"][0]
    assert r["dup"]["status"] == "review" and not r["include"] and r["dup_action"] is None
    assert r["dup"]["matches"][0]["headline"] == rows[1][col]
    assert res["saved"] == 0 and res["review_pending"] == 1 and len(_live()) == N_FIXTURE  # ไม่เลือก = ไม่บันทึก (ไม่เดาแทน)
    _, res = _import(client, _csv(fields, [alt]), {1: "skip"})
    assert res["saved"] == 0 and res["skipped_by_user"] == 1
    _, res = _import(client, _csv(fields, [alt]), {1: "keep_both"})
    assert res["saved"] == 1 and len(_live()) == N_FIXTURE + 1
    alt2 = dict(rows[2], **{col: "Meta Q1 2022 rewritten headline"})
    _, res = _import(client, _csv(fields, [alt2]), {1: "replace"})
    assert res["saved"] == 1 and res["replaced"] == 1 and len(_live()) == N_FIXTURE + 1
    assert rows[2][col] not in {x["headline"] for x in _live()}


def test_typo_fix_is_not_auto_skipped(client):
    """แก้ typo ในไฟล์ที่อัปเดต → hash ไม่ตรงเป๊ะ → ต้องให้ผู้ใช้ตรวจ ไม่ข้ามเงียบ ๆ"""
    fields, rows = _rows()
    _import(client, _csv(fields, rows))
    col = "ข่าวแบบย่อ (short_news)"
    fixed = [dict(rows[0], **{col: rows[0][col].replace("EPS", "E.P.S.")})]
    prev, _ = _import(client, _csv(fields, fixed))
    assert prev["rows"][0]["dup"]["status"] == "review"


def test_duplicate_rows_inside_one_file(client):
    fields, rows = _rows()
    prev, res = _import(client, _csv(fields, rows + rows[:3]))
    assert prev["dup_summary"]["new"] == N_FIXTURE and prev["dup_summary"]["exact"] == 3
    assert res["saved"] == N_FIXTURE and res["skipped_exact"] == 3


def test_existing_rows_are_migrated_with_backup(client):
    _import(client, FIXTURE.read_text(encoding="utf-8"))
    rows = news._load()
    for r in rows:
        r.pop("content_hashes")
    news._write(rows)
    raw = cfg.MANUAL_NEWS.read_bytes()
    assert news.ensure_hashes() == N_FIXTURE
    bak = cfg.MANUAL_NEWS.with_name(cfg.MANUAL_NEWS.name + ".bak-before-content-hash")
    assert bak.read_bytes() == raw
    assert all(r["content_hashes"] == news.hashes_for(r["tickers"], r["date"], r["headline"]) for r in news._load())
    assert news.ensure_hashes() == 0
    _, res = _import(client, FIXTURE.read_text(encoding="utf-8"))
    assert res["skipped_exact"] == N_FIXTURE and res["saved"] == 0


def test_form_add_rejects_exact_duplicate(client):
    b = {"headline": "Same news", "date": "2022-06-01", "tickers": ["AAPL"], "label": 1}
    assert client.post("/api/news", json=b).status_code == 201
    r = client.post("/api/news", json=dict(b, headline="  SAME   news "))
    assert r.status_code == 400 and "มีอยู่แล้ว" in r.get_json()["error"]


def test_600_row_file_is_fast(client):
    fields, rows = _rows()
    tick = [t for t in prices.available_tickers("stock")][:60]
    big = [dict(rows[i % len(rows)], **{"ticker": tick[i % 60], "ข่าวแบบย่อ (short_news)": f"Synthetic headline number {i}",
                                         "วันที่ข่าวออก (publish_date)": f"2022-{1 + i % 12:02d}-{1 + i % 27:02d}"})
           for i in range(600)]
    t0 = time.time()
    prev, res = _import(client, _csv(fields, big))
    t1 = time.time() - t0
    assert res["saved"] == 600, (res["errors"][:3], res)
    t0 = time.time()
    new_row = dict(big[0], **{"ข่าวแบบย่อ (short_news)": "one more new row", "วันที่ข่าวออก (publish_date)": "2021-11-15"})  # ticker+วันที่ใหม่
    prev, res = _import(client, _csv(fields, big + [new_row]))
    t2 = time.time() - t0
    assert res["saved"] == 1 and res["skipped_exact"] == 600
    print(f"600 แถวแรก {t1:.2f}s · import ซ้ำ 601 แถว {t2:.2f}s")
    assert t1 < 20 and t2 < 20
