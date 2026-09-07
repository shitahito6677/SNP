# Stage 5-6 ผลการทดลอง: exp_01 (baseline) vs exp_02 (full pipeline + sentiment)

รันจริงทั้งหมด (ไม่มีตัวเลขสมมติ) — XGBoost multiclass pooled model, train/test split ตามเวลา
(test = ข่าว 2 ปีสุดท้าย, ไม่สุ่มแบ่ง), `n_train = 4008`, `n_test = 363` เท่ากันทั้งสอง exp
(ไม่มีแถวไหนถูกตัดทิ้งจาก merge sentiment — sentiment.parquet ครอบคลุมข่าวทุกชิ้นที่อยู่ใน labels.parquet)

Random-guess baseline (5 class ใกล้เคียงสมดุลใน train) ≈ **20% accuracy**

## 1. ตารางเทียบผลหลัก

| Metric | exp_01 (baseline) | exp_02 (+ sentiment) | ผลต่าง |
|---|---|---|---|
| **Accuracy** | 0.2287 (22.9%) | 0.2176 (21.8%) | **-0.0110 (-4.8% relative)** |
| **Macro F1** | 0.2238 | 0.2114 | **-0.0124 (-5.5% relative)** |

### Per-class F1

| Class | exp_01 | exp_02 | ผลต่าง |
|---|---|---|---|
| -2 (แย่ที่สุด) | 0.2472 | 0.2500 | +0.0028 |
| -1 | 0.1923 | 0.1709 | -0.0214 |
| 0 (กลาง) | 0.2361 | 0.2073 | -0.0288 |
| 1 | 0.1905 | 0.1538 | -0.0367 |
| 2 (ดีที่สุด) | 0.2529 | 0.2750 | +0.0221 |

**สังเกต:** sentiment ช่วยเล็กน้อยเฉพาะ class สุดขั้ว (-2, 2) แต่ทำให้ class กลาง (-1, 0, 1) แย่ลงชัดเจน
ผลรวม macro F1 จึงลดลง เพราะ macro F1 ถ่วงน้ำหนักทุก class เท่ากัน

## 2. Confusion Matrix

แถว = actual, คอลัมน์ = predicted, ลำดับ class: `[-2, -1, 0, 1, 2]`

**exp_01 (baseline)**

| actual\\pred | -2 | -1 | 0 | 1 | 2 |
|---|---|---|---|---|---|
| **-2** | 22 | 16 | 18 | 22 | 34 |
| **-1** | 3 | 10 | 19 | 9 | 10 |
| **0** | 10 | 6 | 17 | 11 | 11 |
| **1** | 7 | 11 | 18 | 12 | 6 |
| **2** | 24 | 10 | 17 | 18 | 22 |

**exp_02 (+ sentiment)**

| actual\\pred | -2 | -1 | 0 | 1 | 2 |
|---|---|---|---|---|---|
| **-2** | 21 | 18 | 31 | 20 | 22 |
| **-1** | 10 | 10 | 16 | 8 | 7 |
| **0** | 7 | 9 | 17 | 12 | 10 |
| **1** | 5 | 13 | 19 | 9 | 8 |
| **2** | 13 | 16 | 26 | 14 | 22 |

ทั้งสองโมเดลมี pattern เดียวกันคือทำนาย class กลาง (0) เยอะเกินจริง (over-predict) และสับสนระหว่าง class ข้างเคียงบ่อย
(เช่น -2 กับ 2 ถูกทำนายเป็น 0 บ่อยพอสมควร) — ไม่มี class ไหนที่โมเดลแยกได้ชัดเจนจริงจัง

## 3. Feature Importance Top 10 ของ exp_02 (gain-based)

| อันดับ | Feature | Gain |
|---|---|---|
| 1 | `sector_XLU` | 2.826 |
| 2 | `sector_XLE` | 2.392 |
| 3 | **`sent_XLI`** | 2.141 |
| 4 | `US10Y` | 2.120 |
| 5 | `VIX` | 2.069 |
| 6 | `sector_XLRE` | 1.993 |
| 7 | **`sent_XLRE`** | 1.968 |
| 8 | **`sent_XLY`** | 1.957 |
| 9 | **`sent_XLC`** | 1.954 |
| 10 | **`sent_XLB`** | 1.945 |

sentiment feature ที่โมเดลให้น้ำหนักมากสุดคือ **`sent_XLI` (Industrials)** ตามด้วย `sent_XLRE`, `sent_XLY`, `sent_XLC`, `sent_XLB` —
5 จาก 10 อันดับแรกเป็น sentiment feature จริง แสดงว่าโมเดล "ใช้" sentiment ในการแตกกิ่งพอสมควร แต่การใช้นั้น
**ไม่ได้แปลงเป็น performance ที่ดีขึ้นบน test set** (ดูข้อ 1) — สอดคล้องกับการตั้งข้อสังเกตจาก Stage 4 ว่า sentiment
score ของหลาย sector (โดยเฉพาะ defensive sector) ไม่ได้สะท้อนทิศทางข่าวจริงมากเท่าที่ควร

## 4. ตีความตรงๆ

**sentiment features ไม่ได้ช่วย** — macro F1 ลดลงจาก **0.2238 เป็น 0.2114 (-5.5%)** และ accuracy ลดลงจาก
**22.9% เป็น 21.8% (-4.8%)** เมื่อเพิ่ม FinBERT sentiment ของทั้ง 11 sector เข้าไปเป็น feature

**เหตุผลที่น่าจะเป็นไปได้ (อิงจากสิ่งที่ตรวจสอบมาจริงในทุก stage ก่อนหน้า ไม่ใช่การเดา):**

1. **สัญญาณพื้นฐานอ่อนมากตั้งแต่ต้น** — แม้แต่ baseline ก็ทำได้แค่ ~23% (สูงกว่า random 20% เพียงเล็กน้อย)
   บ่งชี้ว่า sector + VIX + US10Y ล้วนๆ แทบไม่มีอำนาจพยากรณ์ผลกระทบ 21-วันของข่าวมหภาคต่อ sector เลย
   การเพิ่ม feature ที่มี noise สูงเข้าไปในสถานการณ์แบบนี้ มีโอกาสทำให้แย่ลงมากกว่าดีขึ้น (เพิ่ม dimension โดยไม่เพิ่ม signal จริง)

2. **คุณภาพของ sentiment feature เองมีปัญหาที่พบแล้วใน Stage 4** — FinBERT ให้คะแนนจาก "โทนคำอธิบาย" ทั้งประโยคที่ Qwen
   เขียน ไม่ใช่จาก "ทิศทางที่ Qwen ตั้งใจสื่อ" โดยตรง (เช่น sector defensive อย่าง XLP/XLV แทบไม่เคยได้คะแนนติดลบเลย
   แม้ Qwen จะเขียนกำกับว่า "Neutral" ก็ตาม) sentiment score ที่ได้จึงมี bias เชิงบวกเป็นระบบ ไม่ใช่สัญญาณสะอาด
   ที่แยกแยะผลกระทบเชิงบวก/ลบของข่าวจริงๆ ได้ดี

3. **ข้อมูล train มีจำกัด (4,008 แถว) เทียบกับจำนวน feature ที่เพิ่มขึ้น** (13 → 24 feature) — เพิ่มความเสี่ยง overfit
   ต่อ noise ใน training set แล้วไป generalize ได้แย่ลงบน test set

**สรุป:** ในรูปแบบปัจจุบัน pipeline ของ Model C (Qwen → FinBERT → XGBoost) ยังไม่ได้เพิ่มคุณค่าเชิงพยากรณ์เมื่อเทียบกับ
baseline ง่ายๆ — จุดที่ควรแก้ก่อนไปต่อคือคุณภาพของ sentiment signal (ข้อ 2) มากกว่าตัวโมเดล XGBoost เอง

## Reproducibility

- `experiments/exp_01_baseline_no_text/train.py` → `metrics.json`
- `experiments/exp_02_full_pipeline/train.py` → `metrics.json`
- ทั้งสองใช้ `experiments/common.py` ร่วมกัน (การันตีว่า model config, split, metric การคำนวณเหมือนกันทุกจุด
  ต่างกันเฉพาะการมี/ไม่มี `sent_XLK...sent_XLC` เป็น feature)
- macro features (`VIX`, `US10Y`) แคชไว้ที่ `data/raw/macro_features_raw.parquet`
