"""
ดึงโลโก้บริษัทมา cache ในเครื่อง → sandbox/v2/static/logos/{ticker}.png (gitignored) — รันครั้งเดียวตอน setup เหมือน fetch_vendor

    python3 -m sandbox.v2.scripts.fetch_logos            # ดึงเฉพาะตัวที่ยังไม่มีใน cache
    python3 -m sandbox.v2.scripts.fetch_logos --retry-skipped  # ลองตัวที่เคยหาไม่เจอ/ชื่อไม่ตรงอีกรอบ (ปกติไม่ยิงซ้ำ)
    python3 -m sandbox.v2.scripts.fetch_logos --refresh  # ดึงใหม่ทั้งหมด

แหล่ง: Wikidata (CC0) → property P154 "logo image" ของบริษัทที่มี ticker (P249) บน NYSE/NASDAQ → ไฟล์บน Wikimedia Commons
(Commons รับเฉพาะไฟล์ที่ license อนุญาตให้ใช้ซ้ำได้ — เก็บ license/ผู้สร้างของทุกไฟล์ไว้ที่ logos/ATTRIBUTION.json)
- ตรวจชื่อบริษัทใน Wikidata ให้ตรงกับชื่อใน universe_manifest ก่อนใช้ (กัน ticker ที่ถูกใช้ซ้ำโดยบริษัทอื่น) ไม่ตรง/กำกวม = ไม่ใช้ → fallback avatar
- สุภาพกับ server: User-Agent ระบุโปรเจค, ยิงทีละ request มี delay, เจอ 429/5xx ถอยแล้วหยุด — ไม่ยิงซ้ำตัวที่ cache แล้ว
- โลโก้เป็นเครื่องหมายการค้าของแต่ละบริษัท ใช้เพื่อระบุบริษัทในเครื่องมือวิจัยส่วนตัวนี้เท่านั้น
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from datetime import datetime, timezone

import requests

from sandbox.v2 import config as cfg, prices

UA = "SNP-sandbox-v2-logo-cache/1.0 (https://github.com/shitahito6677/SNP; personal research tool; one-time fetch)"
SPARQL = "https://query.wikidata.org/sparql"
COMMONS = "https://commons.wikimedia.org/w/api.php"
EXCHANGES = {"Q13677": "NYSE", "Q82059": "NASDAQ"}
QUERY = """
SELECT ?item ?itemLabel ?ticker ?exch ?logo WHERE {
  VALUES ?exch { %s }
  ?item p:P414 ?st . ?st ps:P414 ?exch ; pq:P249 ?ticker .
  ?item wdt:P154 ?logo .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}""" % " ".join(f"wd:{q}" for q in EXCHANGES)
STOP = {"inc", "incorporated", "corp", "corporation", "co", "company", "companies", "plc", "ltd", "limited", "holdings", "holding",
        "group", "the", "and", "&", "of", "sa", "nv", "ag", "lp", "llc", "class", "a", "b", "c", "trust", "international", "intl"}
# ตรวจด้วยตา (ไฟล์ .jpg/.gif ทุกไฟล์ใน cache, 2026-09-28): P154 ของ Wikidata บางรายการเป็นภาพถ่าย ไม่ใช่โลโก้ → ไม่ใช้ ให้เป็น avatar
EXCLUDE = {"CTSH": "ไฟล์ logo image ใน Wikidata เป็นภาพถ่ายป้ายบนอาคาร ไม่ใช่โลโก้"}
DELAY_SEC = 0.5
THUMB_PX = 128


def _tokens(name: str) -> set:
    name = re.sub(r"\(.*?\)", " ", (name or "").lower()).replace("&", " and ")
    return {t for t in re.findall(r"[a-z0-9]+", name) if t not in STOP}


GENERIC_FIRST = {"american", "general", "first", "united", "national", "global", "international", "public", "southern",
                 "northern", "western", "eastern", "new", "royal", "digital", "universal", "state"}


def name_match(ours: str, theirs: str, ticker: str = "") -> bool:
    """ชื่อใน manifest กับ label ใน Wikidata ต้องเป็นบริษัทเดียวกัน:
    - label คือ ticker เอง (เช่น "AMD", "SLB") — บริษัทที่เรียกตัวเองด้วยชื่อย่อ
    - คำสำคัญตัวแรกตรงกัน (ยกเว้นคำกว้าง ๆ เช่น American/General ที่ต้องทับกันเกินครึ่ง)
    - หรือคำสำคัญทับกัน ≥ ครึ่ง"""
    if ticker and theirs.strip().upper().replace(".", "-") == ticker:
        return True
    a, b = _tokens(ours), _tokens(theirs)
    if not a or not b:
        return False
    fa = [t for t in re.findall(r"[a-z0-9]+", re.sub(r"\(.*?\)", " ", ours.lower())) if t not in STOP][:1]
    fb = [t for t in re.findall(r"[a-z0-9]+", re.sub(r"\(.*?\)", " ", theirs.lower())) if t not in STOP][:1]
    a2, b2 = a - GENERIC_FIRST, b - GENERIC_FIRST  # คำกว้าง ๆ (American, General …) ไม่นับเป็นหลักฐานว่าเป็นบริษัทเดียวกัน
    overlap = len(a2 & b2) / min(len(a2), len(b2)) if a2 and b2 else float(a == b)
    return (fa == fb and fa[0] not in GENERIC_FIRST) or overlap >= 0.5


def _get(sess, url, **kw):
    for attempt in range(3):
        r = sess.get(url, timeout=60, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After", "0") or 0) or 10 * (attempt + 1)
            print(f"  {r.status_code} จาก {url.split('?')[0]} — รอ {wait} วินาที", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"server ตอบ {r.status_code} ซ้ำหลายครั้ง — หยุดเพื่อไม่ให้ยิงรัว (รันใหม่ภายหลังได้ ตัวที่ได้แล้วอยู่ใน cache)")


def candidates(sess) -> dict:
    """ticker (รูปแบบ Yahoo) → [{item, label, file}] จาก Wikidata"""
    r = _get(sess, SPARQL, params={"query": QUERY, "format": "json"})
    out = {}
    for b in r.json()["results"]["bindings"]:
        t = b["ticker"]["value"].strip().upper().replace(".", "-")
        f = requests.utils.unquote(b["logo"]["value"].rsplit("/", 1)[-1])
        c = {"item": b["item"]["value"].rsplit("/", 1)[-1], "label": b["itemLabel"]["value"], "file": f}
        if c not in out.setdefault(t, []):
            out[t].append(c)
    return out


def choose(ticker: str, name: str, cands: list):
    """คืน (candidate, เหตุผล) — กำกวม/ชื่อไม่ตรง = (None, เหตุผล) ไม่เดา"""
    ok = [c for c in cands if name_match(name, c["label"], ticker)]
    if not ok:
        return None, f"ชื่อใน Wikidata ไม่ตรง ({', '.join(sorted({c['label'] for c in cands}))[:120]})"
    items = {c["item"] for c in ok}
    if len(items) > 1:
        return None, f"ticker ตรงกับหลายบริษัท ({', '.join(sorted({c['label'] for c in ok}))[:120]})"
    files = sorted({c["file"] for c in ok})  # บริษัทเดียวมีหลายโลโก้ (เช่นโลโก้เก่า/ใหม่ ที่ rank เท่ากัน) → เลือกตามชื่อไฟล์แบบคงที่
    return dict(ok[0], file=files[0], n_files=len(files)), None


def imageinfo(sess, files: list) -> dict:
    out = {}
    for i in range(0, len(files), 40):
        batch = files[i:i + 40]
        r = _get(sess, COMMONS, params={"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata",
                                        "iiurlwidth": THUMB_PX, "titles": "|".join("File:" + f for f in batch)})
        q = r.json().get("query", {})
        norm = {n["to"]: n["from"] for n in q.get("normalized", [])}
        for p in q.get("pages", {}).values():
            if "imageinfo" not in p:
                continue
            ii = p["imageinfo"][0]
            md = ii.get("extmetadata", {})
            title = norm.get(p["title"], p["title"])
            out[title.split(":", 1)[1]] = {
                "thumb": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl"),
                "license": (md.get("LicenseShortName") or {}).get("value"),
                "artist": re.sub(r"<[^>]+>", "", (md.get("Artist") or {}).get("value", ""))[:200],
                "attribution_required": (md.get("AttributionRequired") or {}).get("value"),
            }
        time.sleep(DELAY_SEC)
    return out


def to_png(raw: bytes) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGBA")
    im.thumbnail((THUMB_PX, THUMB_PX))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ดึงใหม่แม้มีใน cache แล้ว")
    ap.add_argument("--limit", type=int, default=0, help="ดึงไม่เกิน N ตัว (ทดสอบ)")
    ap.add_argument("--retry-skipped", action="store_true", help="ลองตัวที่รอบก่อนข้ามไปแล้วอีกครั้ง")
    args = ap.parse_args(argv)

    d = cfg.LOGOS_DIR
    d.mkdir(parents=True, exist_ok=True)
    attr_f, man_f = d / "ATTRIBUTION.json", d / "_fetch_report.json"
    attribution = json.loads(attr_f.read_text()) if attr_f.exists() else {}
    man = prices.manifest()["tickers"]
    want = sorted(t for t, r in man.items() if r.get("status") == "ok" and r.get("kind") == "stock")
    for t in EXCLUDE:  # ลบของที่เคย cache ไว้ก่อนตรวจพบ
        (d / f"{t}.png").unlink(missing_ok=True)
        attribution.pop(t, None)
    attr_f.write_text(json.dumps(attribution, ensure_ascii=False, indent=1, sort_keys=True))
    prev_skip = (json.loads(man_f.read_text()).get("skipped") or {}) if man_f.exists() else {}
    todo = [t for t in want if t not in EXCLUDE and (args.refresh or not (d / f"{t}.png").exists())
            and (args.refresh or args.retry_skipped or t not in prev_skip)]
    print(f"หุ้น status ok {len(want)} ตัว · มีใน cache {sum(1 for t in want if (d / f'{t}.png').exists())} · "
          f"เคยข้าม {sum(1 for t in want if t in prev_skip)} (ไม่ยิงซ้ำ — ใช้ --retry-skipped) · ต้องหา {len(todo)}", flush=True)
    if not todo:
        return 0

    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    cands = candidates(sess)
    print(f"Wikidata: บริษัทบน NYSE/NASDAQ ที่มีโลโก้ {len(cands)} ticker", flush=True)
    picked, skipped = {}, {}
    for t in todo:
        name = man[t].get("name")
        if t in EXCLUDE:
            skipped[t] = EXCLUDE[t]
        elif not name or name == t:
            skipped[t] = "ไม่มีชื่อบริษัทใน manifest ให้ตรวจ (หุ้นที่หลุด index) → ไม่เดา"
        elif t not in cands:
            skipped[t] = "ไม่พบใน Wikidata (ไม่มี ticker บน NYSE/NASDAQ หรือไม่มีโลโก้)"
        else:
            c, why = choose(t, name, cands[t])
            if c:
                picked[t] = c
            else:
                skipped[t] = why
    if args.limit:
        picked = dict(list(picked.items())[:args.limit])
    info = imageinfo(sess, sorted({c["file"] for c in picked.values()}))
    got = 0
    for i, (t, c) in enumerate(sorted(picked.items())):
        ii = info.get(c["file"])
        if not ii or not ii.get("thumb"):
            skipped[t] = f"Commons ไม่มีไฟล์ {c['file']}"
            continue
        try:
            raw = _get(sess, ii["thumb"]).content
            (d / f"{t}.png").write_bytes(to_png(raw))
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001 — ไฟล์เดียวเสียไม่หยุดทั้งหมด
            skipped[t] = f"ดาวน์โหลด/แปลงไฟล์ไม่ได้: {type(e).__name__}: {e}"[:200]
            continue
        attribution[t] = {"company": man[t].get("name"), "wikidata": c["item"], "wikidata_label": c["label"], "file": c["file"],
                          "commons_page": ii["page"], "license": ii["license"], "artist": ii["artist"],
                          "attribution_required": ii["attribution_required"],
                          "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        got += 1
        if got % 50 == 0:
            print(f"  ได้แล้ว {got}/{len(picked)}", flush=True)
            attr_f.write_text(json.dumps(attribution, ensure_ascii=False, indent=1, sort_keys=True))
        time.sleep(DELAY_SEC)
    attr_f.write_text(json.dumps(attribution, ensure_ascii=False, indent=1, sort_keys=True))
    man_f.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": "Wikidata P154 → Wikimedia Commons",
                                 "fetched": got, "skipped": dict(prev_skip, **skipped)}, ensure_ascii=False, indent=1, sort_keys=True))
    have = sum(1 for t in want if (d / f"{t}.png").exists())
    print(f"เสร็จ: ได้ใหม่ {got} · ข้าม {len(skipped)} · มีโลโก้ใน cache รวม {have}/{len(want)} (ที่เหลือใช้ avatar)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
