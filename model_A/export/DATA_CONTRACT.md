# DATA CONTRACT — `model_A/export/`

เขียนจาก **โค้ดจริง** (อ่าน ณ 2026-09-27 บน commit `7f9f037`) ไม่ใช่จากสเปคของ sandbox v2 —
จุดที่สเปคต่างจากโค้ดระบุไว้ท้ายไฟล์ ทุกการอ้างอิงเป็น `ไฟล์:บรรทัด` ภายใน `model_A/`

## 1. ไฟล์ที่มีอยู่จริง

| ไฟล์ | สร้างโดย | เนื้อหา |
|---|---|---|
| `scores_rule1.csv` | `export/build_scores.py` | `r004_Q_LOWACC_overall_W_CAP` — 2 รอบ rebalance (2021-06-30, 2022-06-30), 741 แถว |
| `scores_rule2.csv` | `export/build_scores.py` | `r004_C_SHYQMOM_overall_W_CAP` — 24 รอบรายเดือน (2021-06-30 → 2023-05-31), 8,976 แถว |
| `not_applicable_rule{1,2}.csv` | `export/build_scores.py` | สมาชิก S&P 500 ณ วัน R ที่ไม่อยู่ใน universe + เหตุผล |
| `adapter.py` | มือ | `predict(ticker, date, rule)` → dict (อ่าน CSV เท่านั้น) |
| `model_a_experimental.py` | มือ | signature ของ sandbox v1: `predict(ticker, date)` (เลือกกฎด้วย env `MODEL_A_RULE`) |

**ข้อสำคัญ:** export มี **แค่ 2 กฎ และเฉพาะรอบตั้งแต่ มิ.ย. 2021** (`build_scores.py:19` `START = 2021-06-01`)
ไม่ใช่ประวัติทุกรอบตั้งแต่ 2011 และไม่มี `r001_Q_LOWACC_overall` (EW), `_BUFFER`, `_W_IV`
→ sandbox v2 สร้างประวัติครบ 5 กฎด้วย `export/build_history.py` (เรียก `rounds.round_004.run.build` เดิม ไม่ re-implement)

## 2. Column ของ `scores_rule*.csv` (1 แถว = หุ้น × วัน rebalance ที่อยู่ใน universe และมีค่าสัญญาณ)

| column | type | ความหมาย |
|---|---|---|
| `R` | date | วัน rebalance (วันทำการสุดท้ายของเดือนตามปฏิทิน SPY — `lib/panel.py:104-111`) |
| `cik` | float | SEC CIK |
| `ticker` | str | ticker ณ วัน R ตามรายชื่อ fja05680 |
| `yahoo` | str | ticker ใน Yahoo ที่ใช้ดึงราคา (ต่างจาก `ticker` 19 แถวใน rule1 เช่นหุ้นที่เปลี่ยนชื่อ) |
| `cur_ticker` | str/NaN | ticker ปัจจุบันของ CIK นั้น (NaN = บริษัทไม่อยู่ใน map ปัจจุบัน เช่น ถูกซื้อไปแล้ว) |
| `sic_group` | str | กลุ่ม SIC (ไม่ใช่ GICS) |
| `fy_t_end` | date | วันสิ้นปีบัญชีของงบที่ใช้ (point-in-time) |
| `mcap` | float | market cap ณ วัน R (USD) |
| `value` | float | ค่าสัญญาณดิบ (rule1 = `Q_LOWACC`; rule2 = composite 0–1) — **มากกว่า = ดีกว่า** |
| `pct` | float | percentile rank ของ `value` ภายใน universe วันนั้น (0–1] (`build_scores.py:36`) |
| `rank` | int | อันดับ 1 = ดีที่สุด (เสมอกันเรียงด้วย `yahoo`) |
| `n_ranked` | int | จำนวนหุ้นที่มีค่าสัญญาณในวันนั้น |
| `n_selected` | int | `min(n_ranked, max(50, round(0.2·n_ranked)))` (`build_scores.py:31`, `rounds/round_004/run.py:37`) |
| `selected` | bool | `rank ≤ n_selected` |
| `cap_weight` | float/NaN | `mcap / Σ mcap(selected)` เฉพาะตัวที่ถูกเลือก (`build_scores.py:38`) |
| rule2 เท่านั้น: `p_shy`, `p_quality`, `p_mom` | float | percentile รายเสา |
| rule2 เท่านั้น: `A_SHY`, `C_MOM`, `Q_GPA`, `Q_ROIC`, `Q_LOWACC` | float | ค่าดิบรายสัญญาณ |

`not_applicable_rule*.csv`: `R, cik, ticker, yahoo, price_flag, cur_ticker, reason_not_applicable`
(`price_flag` ∈ `ok` / `no_price` / `ok_no_shares` / `ok_shares_suspect`)

## 3. Output ของ `adapter.predict()`
`class` (`buy` = selected, `sell` = pct ≤ 0.20 — แสดงผลเท่านั้น กฎจริง long-only, `hold` = อื่น ๆ),
`score` (= pct, 0.5 ถ้าใช้ไม่ได้), `score_0_100`, `signal` (= class), `reasons` (list, `[0]` = disclaimer เสมอ),
`model_version` = `"experimental-not-frozen"`, `applicable`, `is_stub` = False, `disclaimer`, `rule`, `rebalance_date`
— วันที่ ≥ 2023-06-30 คืน `hold` + `applicable: False` เสมอ (`adapter.py:24,56`)

## 4. Universe rule (`lib/panel.py:67-96`)
1. สมาชิก S&P 500 ณ วัน R จาก fja05680/sp500 (pin commit `a2430f2af0` — `lib/paths.py:24`)
2. `in_U = ~financial & cik ไม่ว่าง & yahoo ไม่ว่าง & price_flag == "ok"` (`lib/panel.py:96`)
3. financial = SIC 6000–6799 (`lib/audit.py:50`) → เช่น SCHW ไม่อยู่ใน universe เสมอ
4. ราคาจริง (ย้อน split) < $1 → ไม่ใช่ `ok` (`lib/audit.py:116,154`)
5. งบ: ใช้ค่าที่ filed ครั้งแรกของแต่ละ tag และ `filed ≤ R − 1 วัน`; งบต้องไม่เก่ากว่า 18 เดือน (`lib/pit.py:5-10,22`)
6. held-out: `lib/guard.py:13` `CUTOFF = 2023-06-30`; rebalance ต้อง `< CUTOFF` (`lib/panel.py:111`)

## 5. คำตอบ 3 จุดที่สเปคบอกว่า "ยังไม่แน่ใจ"

1. **ตัวหารของ accruals** — ค่าเฉลี่ยสินทรัพย์รวมต้นงวด/ปลายงวด:
   `Q_LOWACC = −(NI_t − CFO_t) / avg(TA_t, TA_{t−1})` (`lib/signals_v2.py:6,50,54`);
   ถ้าไม่มี `TA_{t−1}` → NaN (ไม่ถูกจัดอันดับ)
2. **window ของ W_IV** — std ของผลตอบแทนรายวัน **252 วันทำการ** ล่าสุด ≤ R (ปฏิทิน SPY),
   ต้องมีราคาใช้ได้ ≥ 200 วัน (`lib/signals_price.py:5,8,31,35`); น้ำหนัก = `1/vol`, ตัวที่ไม่มี vol ใช้ median
   ของกลุ่มที่เลือก (`rounds/round_004/run.py:53-56`)
3. **field ที่ใช้ใน SHYQMOM** — composite ของ 3 เสา น้ำหนักเท่ากัน (`rounds/round_004/run.py:29`,
   `rounds/round_002/run.py:16-26`): แต่ละเสา = ค่าเฉลี่ย percentile rank ของ field ในเสา, composite = ค่าเฉลี่ยของเสา
   (**ต้องมีครบทุกเสา** ไม่งั้น NaN)
   - `A_SHY` = (ปันผลจ่าย + ซื้อหุ้นคืน − ออกหุ้นใหม่) / market cap, tag ที่ไม่มี = 0 (`lib/signals_a.py:10,77`)
   - Quality = `Q_GPA` (gross profit/TA), `Q_ROIC` (EBIT/(TA − CL − cash), ตัวหาร ≤ 0 = NaN), `Q_LOWACC` (`rounds/round_003/run.py:9`, `lib/signals_v2.py:4-6`)
   - `C_MOM` = P(R−21) / P(R−252) − 1 (momentum 12-1, `lib/signals_price.py:4,30`)

## 6. กฎทั้ง 5 ที่ sandbox v2 ใช้ (ทั้งหมดสร้างด้วย `rounds/round_004/run.py:33 build()`)

| label | trial | base | variant | ความถี่ | น้ำหนัก |
|---|---|---|---|---|---|
| A1 | `r001_Q_LOWACC_overall` | LOWACC | (ไม่มี → เลือก top n) | A (มิ.ย.) | EW |
| A2 | `r004_Q_LOWACC_overall_W_CAP` | LOWACC | `W_CAP` | A | market cap ณ R |
| A3 | `r004_Q_LOWACC_overall_BUFFER` | LOWACC | `BUFFER` (ถือต่อถ้ายังอยู่ top 30%) | A | EW |
| A4 | `r004_Q_LOWACC_overall_W_IV` | LOWACC | `W_IV` | A | 1/vol 252 วัน |
| A5 | `r004_C_SHYQMOM_overall_W_CAP` | SHYQMOM | `W_CAP` | M | market cap ณ R |

## 7. จุดที่สเปค sandbox v2 ต่างจากโค้ดจริง
- สเปค: "เลือก accruals ต่ำสุด 20%" → โค้ด: top 20% ของ `−accruals` **โดยมีขั้นต่ำ 50 ตัว**
- สเปค: "ราคาตั้งแต่ มิ.ย. 2010" → ไฟล์ราคาใน `data/raw/prices/` เริ่ม 2008-01-01 (panel ใช้ตั้งแต่ rebalance 2011-06)
- **จังหวะเทรด:** backtest ของ Model A ซื้อที่ adj close **ของวัน R เอง** (`lib/backtest.py:42`) ขณะที่ sandbox v2 ใช้
  `next_close` (close วัน R+1) → ผลใน sandbox จะไม่เท่ากับ NAV ใน `data/interim/r00x_nav.parquet` เป๊ะ (คาดว่าต่างเล็กน้อย)
- export เดิมไม่มีประวัติก่อน 2021-06 และไม่มีกฎ A1/A3/A4 (ดูข้อ 1)
