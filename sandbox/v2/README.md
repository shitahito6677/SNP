# Sandbox v2 — "Pipeline Lab"

เว็บทดสอบ pipeline **A → B → C → เงื่อนไข Python** บนหุ้น S&P 500 ทั้งหมด: เลือก version โมเดลได้ (สแกนอัตโนมัติ),
รันพร้อม progress/ETA, บันทึกผลแล้วเปิดดูซ้ำได้ตัวเลขเดิมทุกหลัก, ดูกราฟหุ้นรายตัวพร้อมจุดซื้อ/ขายและเหตุผล

> ## ⚠️ Security — อ่านก่อนรัน
> หน้าเว็บนี้ **รันโค้ด Python ที่ผู้ใช้พิมพ์ได้** (exec ใน process แยก มี timeout แต่ **ไม่ใช่ sandbox ด้าน security**
> — โค้ดยังอ่าน/เขียนไฟล์และใช้เครือข่ายได้) server bind `127.0.0.1` เท่านั้น
> **ห้ามเปิดผ่าน ngrok / cloudflared / tunnel / LAN / แชร์ port** — ใครเข้าหน้านี้ได้ = รันโค้ดบนเครื่องคุณได้

## รัน (คำสั่งเดียว จาก repo root)

```bash
python3 -m sandbox.v2.server          # → http://127.0.0.1:5090
```

ครั้งแรกบนเครื่องใหม่ (ต้องมีเน็ต ครั้งเดียว — หลังจากนั้นใช้ offline ได้):

```bash
pip3 install --user flask pandas pyarrow yfinance lxml requests scipy statsmodels   # + pytest playwright ถ้าจะรัน test
python3 -m sandbox.v2.scripts.fetch_vendor      # Plotly + Monaco (gitignored) + ตรวจ checksum ของ lib ที่ commit ไว้
python3 -m sandbox.v2.scripts.update_prices     # ราคา S&P 500 (~2 นาที) → sandbox/v2/data/prices/ (gitignored)
```

sandbox v1 ยังใช้ได้เหมือนเดิม: `python3 -m sandbox.app.server` (port 5050 — ลิงก์ "Legacy v1" ในเว็บ)

## โครงสร้าง

| ไฟล์ | หน้าที่ |
|---|---|
| `config.py` | ค่ากลาง (PRICE_START, HELD_OUT_START, cost, port, timeout) |
| `prices.py` | อ่านราคา + held-out guard + `data_hash` |
| `registry.py` | สแกน `<export>/<version>/manifest.json` ของ A/B/C + validate |
| `signals.py` | as-of access (ห้ามคืนข้อมูลอนาคต) |
| `engine.py` | pipeline (`stage_day`) + simulator (next_close, cost, delist→cash) + benchmark SPY/EW + artifacts |
| `condition_worker.py` | process แยกที่รันโค้ดเงื่อนไข — ได้รับข้อมูล ≤ t ทีละวัน |
| `jobs.py` | 1 run = 1 process, สถานะใน SQLite (`jobs.db`), ETA จาก throughput จริง, cancel |
| `experiments_store.py` | บันทึก/เปิด/re-run diff/compare/bundle |
| `news.py` | ข่าว manual (`source="manual"`), @mention/auto-detect |
| `server.py` + `templates/` + `static/` | เว็บ (Flask + Alpine + lightweight-charts + Plotly + Monaco — vendored offline) |
| `tests/` | pytest (look-ahead, sanity, held-out, jobs, persistence, e2e, manual news) |
| `scripts/` | update_prices, data_quality, build_stubs, fetch_vendor, ui_smoke (Playwright), eval_mentions |

## เพิ่ม version โมเดลใหม่ (ไม่ต้องแก้โค้ดเว็บ)

1. สร้างโฟลเดอร์ `model_A/export/<version>/` (หรือ `model_B/export/…`, `model_c_rulebase/export/…`)
2. ใส่ `signals.parquet` (หรือ `.csv`) — column: `date`, `ticker` (A/B) หรือ `sector` = ETF เช่น `XLK` (C), `class`, `score`,
   `applicable`, `reasons` (list), `model_version`, `is_stub`
   - A: class `selected` / `not_selected` / `not_applicable` (+ `weight` ถ้ากฎมีน้ำหนักของตัวเอง) — **ต้องเป็น ranking ทั้ง universe** ห้ามคำนวณจาก subset
   - B/C: class `positive` / `neutral` / `negative`; `date` = วันที่สัญญาณใช้ได้ ณ close
3. ใส่ `manifest.json`: `model, version, short_label, display_name, is_stub, result_badge (real/stub/negative), signal_files,
   coverage {start, end, valid_through?}, rebalance (annual_june/monthly/event/daily), asof {max_age_days}?, source_experiment,
   created_at, notes, warnings[]`
4. เว็บ → Registry → **Rescan** (ไม่ผ่าน validation จะขึ้นรายการ invalid พร้อมเหตุผล) — ตัวอย่างเต็มดู `model_B/export/README.md`

สร้าง export ที่มีอยู่ใหม่: `cd model_A && python3 -m export.build_history` (ต้องมี `model_A/data/`),
`python3 -m model_c_rulebase.export.build_export`, `python3 -m sandbox.v2.scripts.build_stubs`

## เขียนเงื่อนไข (condition)

ไฟล์ `sandbox/v2/conditions/<id>.py` (หรือเขียนใน editor แล้วกด Save as new — ห้ามเขียนทับไฟล์เดิม):

```python
NAME = "C-veto: ขายเมื่อ sector ติดลบ"
DESCRIPTION = "…"

def decide(ctx):                       # เรียกทุกวันทำการ (close วัน t) → ซื้อขายที่ close วัน t+1
    w = {}
    for t in ctx.universe:             # หุ้นที่ผ่านกล่องที่เปิดทั้งหมด
        c = ctx.c_for(t)               # สัญญาณ C ของ sector ของหุ้นนี้ (หรือ None)
        if c and c["class"] == "negative":
            ctx.note(t, "sector ติดลบ → ไม่ถือ")   # แนบเหตุผลเข้า trade
            continue
        w[t] = 1.0
    s = sum(w.values())
    return {t: v / s for t, v in w.items()} if s else {}   # รวม ≤ 1 (ที่เหลือ = เงินสด); None = คงเป้าเดิม
```

`ctx`: `date`, `universe`, `a[t]` (`class, score, weight, reasons, date`), `b[t]`, `c[sector]`, `c_for(t)`, `sector_of(t)`, `etf_of(t)`,
`price(t)`, `history(t, lookback_days, field='adj')` (ห้ามขอเกิน `ctx.date`), `portfolio` (`value, cash, cash_weight, weights, units`),
`state` (dict จำค่าข้ามวัน), `stage_enabled`, `note(t, text)`

กติกา: long-only, น้ำหนัก ≥ 0 รวม ≤ 1, ticker ต้องอยู่ใน universe / SPY + sector ETF / ที่ถืออยู่ ·
rebalance เฉพาะวันที่ผลลัพธ์เปลี่ยนจากครั้งก่อน · `decide()` เกิน 10 วินาที/ครั้ง หรือ job เกิน 30 นาที → job fail

## ขอบเขตการลงทุน (ขั้น 0 ก่อนกล่อง A)
- หน้า Pipeline → "ขั้น 0 — ขอบเขตการลงทุน": `ทั้งตลาด (S&P 500)` (ค่าเริ่มต้น) / `เลือก Sector` (11 GICS ETF, เลือกได้หลายตัว) / `เลือกหุ้นเอง` (พิมพ์ `@ticker` หรือชื่อบริษัท แล้ว Enter)
- **A จัดอันดับจากทั้ง universe เสมอ** แล้วค่อยกรองเหลือ scope — record ของ A (class/score/เหตุผล) ที่เงื่อนไขเห็นเป็นค่าเดียวกับตอนไม่จำกัด scope
- funnel ขั้นแรก = หุ้นใน scope ที่มีราคาวันนั้น · EW benchmark = EW ของหุ้นใน scope · SPY = ตลาดรวม (ไม่เปลี่ยน)
- `config.json` เก็บ `scope: {mode, sectors, tickers, members}` → เปิดผลเก่า/Re-run ได้ scope เดิม
- sector ว่าง / ticker ไม่รู้จัก → preflight ปฏิเสธก่อนกด RUN; หุ้นใน scope ไม่ผ่าน A ทุกรอบ → เตือนก่อนรัน และหน้าผลบอกว่าทำไมพอร์ตว่าง
- หุ้นที่หลุด index (sector = Unknown, 59 ตัว) อยู่ได้เฉพาะ scope "ทั้งตลาด"

## นำเข้าข่าว CSV
- จับคู่ column จากคำในชื่อ (มีวงเล็บ/คำไทยนำหน้าได้ เช่น `ข่าวแบบย่อ (short_news)`) — หน้า preview แก้ mapping เองได้ก่อนบันทึก
- **label 5 ระดับ `-2..+2` คือค่าหลักของข่าว manual** (-2 negative แรงมาก · -1 negative · 0 neutral (ไม่ค่อยมีผล) · +1 positive · +2 positive แรงมาก) — ใช้ตลอดระบบ: หน้า preview (dropdown 5 ค่า), ฟอร์มพิมพ์เอง, trade reasons (`B: … label -2 negative แรงมาก · … [MANUAL]`), hover/marker บนหน้าหุ้น (`M-2`), `ctx.b[t]["label"]` / `ctx.c[etf]["label"]` ในเงื่อนไข
- `class` 3 กลุ่ม (≤-1 negative, 0 neutral, ≥1 positive) และ `score = label/2` **derive เพิ่ม** ใน record ของ signal เพื่อให้เกณฑ์กรองแบบ Model B (ตัด negative/neutral, score ≥) ใช้ได้เท่านั้น — ไม่เขียนทับ label
- label สเกลอื่น (เช่น ±1, ±5) → เทียบเป็น -2..+2 และเก็บค่าในไฟล์ไว้ที่ `label_raw`; ข้อความ positive/neutral/negative → +1/0/-1
- column อื่น (`source_url`, `label_reason`, …) เก็บเป็น `extra` ต่อแถว; แถวที่อ่านไม่ได้ถูกข้ามพร้อมเหตุผล ไม่ทำให้ทั้งไฟล์ fail

## Error / log
- ทุก error ของ API คืน JSON ข้อความภาษาไทย (ไม่มีหน้า 500 HTML ดิบ); error ที่ไม่คาดคิดมี `รหัสอ้างอิง` → ค้นใน `sandbox/v2/logs/server.log` (traceback เต็ม, gitignored)

## Held-out

ข้อมูลตั้งแต่ `2023-07-01` ล็อกไว้ (วันจบ default `2023-06-30`) — รันเข้าช่วงนี้ต้องเปิด toggle + พิมพ์ `ยืนยัน held-out`
และผลจะติด `held_out_touched: true` + badge **HELD-OUT** ถาวร เหตุผล: ดูผลช่วง held-out แล้วกลับไปปรับเงื่อนไข = เอาข้อสอบมาติว

## เปลี่ยนช่วงราคา

แก้บรรทัดเดียวใน `config.py`: `PRICE_START = "2010-06-01"` แล้วรัน `python3 -m sandbox.v2.scripts.update_prices`
(ดึงเฉพาะ ticker ที่ยังไม่ครอบคลุมช่วงใหม่ — ส่วนอื่นไม่ต้องแก้) · signal ของ Model A มีตั้งแต่ 2011-06 อยู่แล้ว

## ทดสอบ

```bash
python3 -m pytest sandbox/v2/tests -q            # 24 tests (~45 วิ)
python3 -m sandbox.v2.scripts.ui_smoke           # Playwright: คลิกทั้งเว็บ + screenshot → sandbox/v2/screenshots/
python3 -m sandbox.v2.scripts.eval_mentions      # ความแม่นยำ auto-detect ข่าว
```

## Git policy

commit: โค้ด, manifest/signal ของ export, `universe_manifest.json`, `DATA_QUALITY.md`, ผลทดลองส่วนข้อความ
(`config.json`, `condition_snapshot.py`, `metrics.json`, `provenance.json`, `summary.json`)
**ไม่ commit:** ราคา (`data/prices/`), `cache/`, `jobs.db`, parquet ของผลทดลอง, `manual_news.jsonl`, Plotly/Monaco, `.env`

## ข้อจำกัด

ดูหน้า About ในเว็บ และ `PROGRESS.md` / `DECISIONS_NEEDED.md` — สรุป: Model A ระดับ C (ไม่ผ่าน DSR) ยังไม่ freeze; ราคา 5 ปี
ทำให้ A รายปีมีแค่ 2 รอบก่อน held-out; B เป็น stub; C rulebase เป็น negative result และช่วง 2021+ อยู่ใน test set ของ exp_03;
survivorship (universe จากรายชื่อปัจจุบัน + หุ้นที่ Yahoo ไม่มีราคาหายไป)
