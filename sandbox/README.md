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
  config.py                    # universe (5 ticker) + sector/ETF mapping — ยืนยันจริงใน Phase 0
  events_store.py              # บันทึก/โหลด event ที่ inject จากหน้า Events (JSON Lines)
  inference/
    model_a.py / model_b.py / model_c.py   # STUB predict() — ดู inference/README.md สำหรับ contract
    _stub_utils.py               # helper ที่ stub ใช้ร่วมกัน (ลบทิ้งได้เมื่อ swap ครบ)
    README.md                    # input/output contract ของแต่ละโมเดล + วิธี swap เป็นของจริง
  rules/
    rule_table.json              # 27-row lookup table (A x B x C -> BUY/HOLD/SELL)
    engine.py                    # combine(a_result, b_result, c_result) -> signal
  app/
    server.py                    # Flask entry point (รันด้วย python -m sandbox.app.server)
  templates/                     # base.html + dashboard/events/rules/experiments.html
  static/css/style.css           # dark trading-dashboard theme (#0e1117)
  static/js/main.js              # Plotly.js candlestick + event marker + injection form
  scripts/
    phase0_validate_universe.py  # Phase 0 — validate universe (เสร็จแล้ว, ดู data/validation_report.md)
    generate_rule_table.py       # generate sandbox/rules/rule_table.json จาก formula
    smoke_test.py                # sanity check inference stub + rule engine แบบไม่ต้องเปิด server
  data/
    prices/{TICKER}.csv          # Phase 0 output
    validation_report.md         # Phase 0 output
    events/events.jsonl          # event ที่ inject จากหน้า Events (gitignored ตัวไฟล์ข้อมูล)
```

## วิธีรัน

```bash
# ติดตั้ง dependency ของ sandbox (Plotly.js โหลดผ่าน CDN ไม่ต้องติดตั้ง python package)
python3 -m pip install --user -r sandbox/requirements.txt

# รันจาก project root เสมอ (import sandbox.* ต้องเจอ)
cd /path/to/SNP-claude

# sanity check inference stub + rule engine แบบไม่ต้องเปิด server
python3 -m sandbox.scripts.smoke_test

# เปิด dashboard
python3 -m sandbox.app.server
# -> http://127.0.0.1:5050
```

## หน้าต่างๆ

- **Dashboard** (`/dashboard`) — กราฟแท่งเทียนราคา (Plotly.js) ต่อ ticker, เลือกช่วงวันที่ได้,
  เส้นประแนวตั้ง = macro event (สีตาม class, โผล่ทุก ticker แต่ class อาจต่างกันเพราะคนละ
  sector), จุดสีบนแท่งเทียน = company news event เฉพาะ ticker นั้น, คลิก marker เพื่อดู
  รายละเอียด (วันที่, class, score, is_stub badge)
- **Events** (`/events`) — manual event injection: พิมพ์ headline เอง เลือกเป็น macro
  (รันผ่าน Model C ทุก sector) หรือ company (รันผ่าน Model B ตัวเดียว) แล้วบันทึกเป็น event
- **Rules** (`/rules`) — 27-row rule engine lookup table (Model A × B × C → BUY/HOLD/SELL)
- **Experiments** (`/experiments`) — ประวัติ event ที่ inject ไปแล้วทั้งหมด

STUB badge มุมขวาบนทุกหน้า คำนวณจาก module-level `IS_STUB` ของแต่ละ inference module (ไม่ได้
hardcode, ไม่เรียก `predict()` จริงเพื่อเช็ค) — พอ Model A/B/C ถูกสลับเป็นของจริงครบทั้ง 3 ตัว
(ตั้ง `IS_STUB = False`) banner จะหายไปเองโดยไม่ต้องแก้โค้ด UI

## ขั้นต่อไป

หาโค้ด/เขียน inference ของ Model A (Piotroski) และ Model B (FinBERT company sentiment) ให้
จริง แล้ว wrap Model C เป็น inference function เดียว (`predict(headline, sector_etf)`) จาก
pipeline ที่มี train code ครบอยู่แล้ว — สลับทีละตัวใน `sandbox/inference/` ตาม contract ใน
`inference/README.md` โดยไม่ต้องแตะ `rules/`, `events_store.py`, หรือ `app/`
