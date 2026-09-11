# SNP Sandbox — Ensemble testing (Model A+B+C)

Web sandbox สำหรับทดสอบว่าจะ combine สัญญาณจาก Model A (Piotroski Fundamental) + Model B
(FinBERT Company News Sentiment) + Model C (Macro/Sector News → Qwen → FinBERT → XGBoost)
เป็นสัญญาณซื้อ/ขาย/ถือเดียวยังไง **ไม่ใช่ backtest ผลตอบแทนจริง** (เป็นงานคนละ phase ทำทีหลัง)

## สถานะ ณ ตอนนี้

Model A และ Model B **ยังไม่มีโค้ดจริง** เลย (ดู `experiments/log.md`) Model C มีโค้ด train
ครบ (`src/s1_fetch_news.py` .. `src/s4_sentiment.py`) แต่ยังไม่ได้ wrap เป็น inference
function ทั้ง 3 โมเดลใน `sandbox/inference/` ตอนนี้จึงเป็น **stub ทั้งหมด** — deterministic
(seed จาก input) ไม่ใช่ prediction จริง แต่ interface (function signature + return schema)
fix ไว้แล้ว พร้อมสลับเป็นของจริงทีหลังโดยไม่ต้องแก้โค้ดที่เรียกใช้

## โครงสร้าง

```
sandbox/
  config.py                    # universe (5 ticker) + sector/ETF mapping + price date range — ยืนยันจริงใน Phase 0
  events_store.py              # บันทึก/โหลด manual event จากหน้า Events (CSV, source="manual" เสมอ)
  events_bulk.py                # parse+validate CSV bulk upload (preview ก่อน commit เสมอ)
  experiments_db.py            # Phase 5 — SQLite (sandbox/experiments.db) run/list/diff experiment
  historical_data.py           # เชื่อม macro (C) event จริง (477 ข่าว FOMC/Beige Book) เข้า dashboard
  analytics/
    indicators.py                # SMA20/50, RSI(14), MACD(12,26,9) — คำนวณจากราคาที่มีอยู่แล้ว
  inference/
    model_a.py / model_b.py / model_c.py   # STUB predict() — ดู inference/README.md สำหรับ contract
    _stub_utils.py               # helper ที่ stub ใช้ร่วมกัน (ลบทิ้งได้เมื่อ swap ครบ)
    README.md                    # input/output contract ของแต่ละโมเดล + วิธี swap เป็นของจริง
  engine/
    combine.py                    # combine(a, b, c, rule_path) -> decision, lookup ตรง ห้าม fallback
    simulate.py                    # Strategy engine — วน day-by-day, เรียก strategy.on_day(), trade log เต็ม
  rules/
    rule_v1.json, rule_v2.json..  # versioned lookup table (27 แถวเสมอ) — ห้ามทับของเก่า มีแต่เพิ่ม version ใหม่
    rule_v1_logic.py               # decide(a,b,c) -> str ต้นทางของ rule_v1.json ("A เป็นหลัก, B/C เป็น veto")
    versions.py                   # list/load/save version ผ่าน UI (save = สร้างไฟล์ใหม่เสมอ)
  strategy/
    base.py                        # Strategy interface + PortfolioState (cash/holdings/last_sell_price)
    strategy_v1.py                  # sell บน C=negative, ซื้อคืน -20%, DCA เข้า C=positive
  app/
    server.py                    # Flask entry point (รันด้วย python -m sandbox.app.server)
  templates/                     # base.html + dashboard/events/rules/experiments/strategies.html
  static/css/style.css           # dark trading-dashboard theme (#0e1117)
  static/js/main.js              # Plotly.js candlestick + event marker + injection/rule-edit/strategy form
  scripts/
    phase0_validate_universe.py  # Phase 0 — validate universe (เสร็จแล้ว, ดู data/validation_report.md)
    generate_rule_table.py       # import decide(a,b,c) จาก logic module (เช่น rule_v1_logic) -> rule_v{N}.json
    smoke_test.py                # sanity check inference stub + config แบบไม่ต้องเปิด server
    test_combine.py              # unit test ของ sandbox/engine/combine.py + rule_v1_logic.py (unittest, 13 case)
  data/
    prices/{TICKER}.csv          # Phase 0 output
    validation_report.md         # Phase 0 output
    manual_events.csv            # Phase 3 output — event ที่ inject จากหน้า Events
                                  # (gitignored ตัวไฟล์ข้อมูล, source="manual" เสมอ,
                                  # แยกขาดจาก data/raw/macro_news_raw.parquet ที่ root repo)
  experiments.db                 # Phase 5 output — SQLite, gitignored, regenerable ผ่านหน้า Experiments
```

## วิธีรัน

```bash
# ติดตั้ง dependency ของ sandbox (Plotly.js โหลดผ่าน CDN ไม่ต้องติดตั้ง python package)
python3 -m pip install --user -r sandbox/requirements.txt

# รันจาก project root เสมอ (import sandbox.* ต้องเจอ)
cd /path/to/SNP-claude

# sanity check inference stub + config แบบไม่ต้องเปิด server
python3 -m sandbox.scripts.smoke_test

# unit test ของ rule engine (sandbox/engine/combine.py)
python3 -m unittest sandbox.scripts.test_combine -v

# เปิด dashboard
python3 -m sandbox.app.server
# -> http://127.0.0.1:5050
```

## หน้าต่างๆ

- **Dashboard** (`/dashboard`) — กราฟแท่งเทียนราคา (Plotly.js) ต่อ ticker, เลือกช่วงวันที่ได้,
  เส้นประแนวตั้ง = macro event (สีตาม class, โผล่ทุก ticker แต่ class อาจต่างกันเพราะคนละ
  sector), จุดสีบนแท่งเทียน = company news event เฉพาะ ticker นั้น, คลิก marker เพื่อดู
  รายละเอียด (วันที่, class, score, is_stub badge)
- **Events** (`/events`) — manual event injection: เลือก ticker ก่อน แล้วเลือก scope B
  (หุ้นนี้เท่านั้น, Model B) หรือ C (ทุกหุ้น, Model C แยกตาม sector) เลือกวันที่ (จำกัดในช่วง
  ที่มีข้อมูลราคาจริง) พิมพ์ headline แล้ว "รันผ่านโมเดล" — ปุ่ม B จะ disable อัตโนมัติถ้า
  ticker นั้นไม่อยู่ใน `config.TICKERS_WITH_COMPANY_NEWS` (เช็คทั้ง client-side และ server-side)
  มี disclaimer ชัดเจนว่าเป็นการทดสอบพฤติกรรม stub ไม่ใช่ backtest
- **Rules** (`/rules`) — 27-row rule engine lookup table (Model A × B × C → buy/hold/sell)
  editable ผ่าน UI (dropdown ต่อแถว) กด "Save as new version" สร้าง `rule_v{n+1}.json` ใหม่
  เสมอ ห้ามทับไฟล์เดิม — ดู version เก่าได้ผ่าน `/rules?version=n`
- **Experiments** (`/experiments`) — รัน experiment ใหม่ (เลือก rule version + ticker_set +
  date range → สแกน manual event หาคู่ (ticker,date) ที่มีทั้ง B+C แล้วรัน `combine()`, บันทึก
  ลง `sandbox/experiments.db`), รายการ experiment ที่ save ไว้ (เลือก 2 อันมา diff ดูว่า
  decision ต่างกันวันไหน — เฉพาะ rule-lookup experiment เท่านั้น), และประวัติ manual event
  ทั้งหมด
- **Strategies** (`/strategies`) — เลือก strategy file + ticker_set + date range + เงินทุน
  ตั้งต้น กด "Run simulation" วน day-by-day เรียก `strategy.on_day()` เห็น trade log +
  กราฟมูลค่าพอร์ต เก็บลง `sandbox/experiments.db` ตารางเดียวกับ rule-lookup experiment
  (แยกด้วย `rule_version = "strategy:<name>"`) — banner บังคับเตือนว่าใช้ signal จาก stub
  เสมอ (ทดสอบ logic ไม่ใช่ทดสอบกำไรจริง)

STUB badge มุมขวาบนทุกหน้า คำนวณจาก module-level `IS_STUB` ของแต่ละ inference module (ไม่ได้
hardcode, ไม่เรียก `predict()` จริงเพื่อเช็ค) — พอ Model A/B/C ถูกสลับเป็นของจริงครบทั้ง 3 ตัว
(ตั้ง `IS_STUB = False`) banner จะหายไปเองโดยไม่ต้องแก้โค้ด UI

## ขั้นต่อไป

หาโค้ด/เขียน inference ของ Model A (Piotroski) และ Model B (FinBERT company sentiment) ให้
จริง แล้ว wrap Model C เป็น inference function เดียว (`predict(headline, sector_etf)`) จาก
pipeline ที่มี train code ครบอยู่แล้ว — สลับทีละตัวใน `sandbox/inference/` ตาม contract ใน
`inference/README.md` โดยไม่ต้องแตะ `rules/`, `events_store.py`, หรือ `app/`
