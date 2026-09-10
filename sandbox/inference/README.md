# Inference Contract — Model A / B / C

โฟลเดอร์นี้มี `predict()` ของทั้ง 3 โมเดล **เป็น stub ทั้งหมด** (ดูสถานะจริงใน
`experiments/log.md` — Model A/B ยังไม่ได้เขียน, Model C มีโค้ด train ครบแต่ยังไม่ได้ wrap
inference) จุดประสงค์ของไฟล์นี้คือ fix "หน้าตา" ของ input/output ไว้ล่วงหน้า เพื่อให้
Phase 2-5 (dashboard, rule engine, ฯลฯ) เขียนต่อได้เลยโดยไม่ต้องรอโมเดลจริง แล้วพอโมเดลจริง
พร้อม แค่แก้ "ข้างใน" ฟังก์ชันให้ตรง signature เดิม ส่วนที่เหลือไม่ต้องแตะ

## กติกาการ swap เป็นของจริง

1. ห้ามเปลี่ยนชื่อ/ตำแหน่ง module (`sandbox/inference/model_a.py` ฯลฯ) และชื่อฟังก์ชัน
   (`predict`) — โค้ดที่เรียกใช้ (`sandbox/rules/engine.py`, `sandbox/app/server.py`)
   import ตรงจาก path นี้
2. ห้ามเปลี่ยน parameter name/order และ return dict key — โค้ดปลายทางอ่านด้วย key name
3. เมื่อเป็นโมเดลจริงแล้ว ให้เซ็ต `is_stub: False` ใน return dict (หรือเอา key นี้ออกแล้วให้
   caller default เป็น False — แต่แนะนำให้คงไว้แล้วเซ็ต False จะชัดกว่า)
4. ลบการ import จาก `sandbox/inference/_stub_utils.py` ออกจากไฟล์ที่ swap แล้ว (ไฟล์นั้นมีไว้
   ให้ stub ใช้ร่วมกันเท่านั้น ไม่ใช่ของ production)

## Model A — Piotroski Fundamental Screening

`sandbox/inference/model_a.py`

```python
def predict(ticker: str, date: str) -> dict:
    ...
```

| | field | type | ค่าที่เป็นไปได้ |
|---|---|---|---|
| input | `ticker` | str | ต้องอยู่ใน `sandbox.config.TICKERS` (`NVDA`, `META`, `TSLA`, `SCHW`, `FDX`) |
| input | `date` | str | ISO date `"YYYY-MM-DD"` |
| output | `class` | str | `"buy"` \| `"hold"` \| `"sell"` |
| output | `score` | float | confidence ของ `class`, ช่วง `[0, 1]` |
| output | `is_stub` | bool | `True` ถ้ายังเป็น stub, `False` เมื่อเป็นโมเดลจริง |

## Model B — FinBERT Company News Sentiment

`sandbox/inference/model_b.py`

```python
def predict(headline: str, ticker: str) -> dict:
    ...
```

| | field | type | ค่าที่เป็นไปได้ |
|---|---|---|---|
| input | `headline` | str | ข้อความข่าวรายบริษัท (free text ใดก็ได้ รวมถึงข่าวที่ user พิมพ์เองใน manual event injection) |
| input | `ticker` | str | ต้องอยู่ใน `sandbox.config.TICKERS` |
| output | `class` | str | `"positive"` \| `"neutral"` \| `"negative"` |
| output | `score` | float | confidence ของ `class`, ช่วง `[0, 1]` |
| output | `is_stub` | bool | `True` ถ้ายังเป็น stub, `False` เมื่อเป็นโมเดลจริง |

## Model C — Macro/FOMC News → Qwen → FinBERT → XGBoost (per GICS sector)

`sandbox/inference/model_c.py`

```python
def predict(headline: str, sector: str) -> dict:
    ...
```

| | field | type | ค่าที่เป็นไปได้ |
|---|---|---|---|
| input | `headline` | str | ข้อความข่าวมหภาค/FOMC (free text) |
| input | `sector` | str | sector **ETF code** เช่น `"XLK"` — ต้องอยู่ใน `sandbox.config.SECTOR_ETF.values()` — **ไม่ใช่** GICS sector name และไม่ใช่ ticker (ใช้ `sandbox.config.ticker_to_etf(ticker)` เพื่อแปลงจาก ticker) |
| output | `class` | str | `"positive"` \| `"neutral"` \| `"negative"` |
| output | `score` | float | confidence ของ `class`, ช่วง `[0, 1]` |
| output | `is_stub` | bool | `True` ถ้ายังเป็น stub, `False` เมื่อเป็นโมเดลจริง |

หมายเหตุ: โมเดลจริงเทรนแยกตาม 11 GICS sector ETF (ดู `CLAUDE.md`) — caller ส่ง ETF code ตรงๆ
(เช่น `"XLK"`) ไม่ต้อง map เพิ่มข้างในฟังก์ชันแล้ว (`ticker -> sector -> ETF` แปลงที่ caller
ด้วย `sandbox.config.ticker_to_etf()` ก่อนเรียก)

## ทำไม stub ถึง "สุ่ม" แต่ deterministic

`sandbox/inference/_stub_utils.py` seed ผลลัพธ์จาก sha256 ของ input string (ไม่ใช้
`hash()` built-in เพราะถูกสุ่มด้วย `PYTHONHASHSEED` คนละ process) input เดียวกัน → output
เดียวกันเสมอ ไม่ว่าจะรันกี่ครั้ง กี่ process — เพื่อให้ผลของ dashboard/rule engine
reproducible ระหว่าง debug แม้ underlying model ยังเป็น placeholder
