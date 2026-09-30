# Export / adapter สำหรับ web test simulator (`sandbox/`)

> ## ⚠️ ทดลองระบบ ข้อมูลไม่ครบ ไม่ใช่หลักฐานว่ากฎชนะตลาด
> - ทั้งสองกฎอยู่ **ระดับ C ("ไม่ผ่าน")** ตาม `../PREREG_AUTORUN.md` (ไม่ผ่าน S3: DSR < 0.95) และ **ยังไม่ freeze** → `model_version = "experimental-not-frozen"`
> - ผู้ใช้สั่งให้ทำเป็น **เดโมระบบ** เท่านั้น — **ห้ามใช้ผลใน sandbox เลือกหรือปรับกฎ** (ไม่นับเป็น trial และไม่ใช่การประเมินผล)
> - **held-out ยังล็อก:** มีคะแนนเฉพาะวันที่ก่อน 2023-06-30; วันหลังจากนั้น adapter คืน `hold` + `applicable: False`
>   (sandbox ใช้ราคา 2021-09 – 2026-09 → ช่วงที่มีคะแนนจริงคือ 2021-09 – 2023-06 เท่านั้น)

## กฎที่ export (อันดับ 1–2 ใน `../LEADERBOARD.md` ตาม Sharpe ช่วงตัดสิน)
| rule | trial | สรุป | ความถี่ | ข้อมูลใน export |
|---|---|---|---|---|
| `rule1` | `r004_Q_LOWACC_overall_W_CAP` | accruals ต่ำ top 20% (ขั้นต่ำ 50), ถ่วงน้ำหนักตาม market cap | รายปี (มิ.ย.) | rebalance 2021-06-30, 2022-06-30 |
| `rule2` | `r004_C_SHYQMOM_overall_W_CAP` | shareholder yield + quality + momentum top 20% (ขั้นต่ำ 50), ถ่วงน้ำหนักตาม market cap | รายเดือน | 2021-06-30 – 2023-05-31 (24 รอบ) |

ทั้งสองกฎทำงานบน S&P 500 ไม่รวมกลุ่มการเงิน → **SCHW ได้ `applicable: False` เสมอ**

## BMF20 (round 013) — history export สำหรับ sandbox v2 (`bmf20-funnel`, `bmf20-weighted`)
> ⚠️ ทดลองระบบ ข้อมูลไม่ครบ ไม่ใช่หลักฐานว่ากฎชนะตลาด · ระดับ C (ตก S1, S2, S3, S6) · `experimental-not-frozen` · ใช้ได้ถึง 30 มิ.ย. 2023 เท่านั้น

| โฟลเดอร์ | กฎ | เนื้อหา |
|---|---|---|
| `bmf20-funnel/` | BM 100 ตัวแรก → F-score 20 ตัว (`r013_BMF20_FUNNEL`) | `manifest.json` + `signals.parquet`: ทุกหุ้นใน universe ต่อรอบ มิ.ย. 2011–2022 (`selected` 20 ตัว / `not_selected` / `not_applicable` พร้อมเหตุผล) |
| `bmf20-weighted/` | 0.6·percentile BM + 0.4·percentile F → 20 ตัว (`r013_BMF20_WEIGHTED`) | เหมือนกัน |

- `score` 0–100 (มาก = ดี; ความหมายต่อกฎอยู่ใน `score_meaning`), `weight` = 0.05 สำหรับ 20 ตัวที่เลือก, `reasons` = [คำเตือน, อันดับตามกฎ, "BM อันดับ x/n, F-score y/9", ปีงบที่ใช้]
- รูปแบบเดียวกับ history export ของ sandbox v2 (`export/DATA_CONTRACT.md` บน branch `feature/sandbox-v2`) — ตรวจกับ validation ของ registry แล้ว 0 error
- สร้างใหม่: `python3 -m export.build_bmf20` (อ่าน `rounds/round_013/scores.csv` เท่านั้น; ตรวจว่าตรงกับ `picks_*.csv` ทุกรอบ)

## ไฟล์
| ไฟล์ | เนื้อหา |
|---|---|
| `build_scores.py` | คำนวณคะแนนล่วงหน้าจาก panel ของ AUTORUN (ตรวจแล้วว่าชุดหุ้นที่เลือกตรงกับ backtest round 004 ทุกรอบ: rule1 12 รอบ, rule2 144 รอบ) |
| `scores_rule1.csv`, `scores_rule2.csv` | คะแนนต่อหุ้นต่อรอบ (อันดับ, percentile, เลือก/ไม่เลือก, น้ำหนัก cap, ข้อมูลประกอบ) |
| `not_applicable_rule*.csv` | สมาชิกที่ไม่อยู่ใน universe พร้อมเหตุผล |
| `adapter.py` | `predict(ticker, date, rule)` — อ่าน CSV เท่านั้น ไม่เรียกโค้ดวิจัย |
| `model_a_experimental.py` | signature เดียวกับ sandbox: `predict(ticker, date)` + `IS_STUB = False` (เลือกกฎด้วย env `MODEL_A_RULE`) |

## Output (ตรง contract ใน `sandbox/inference/README.md` + key เพิ่ม)
| key | ค่า |
|---|---|
| `class` | `"buy"` = อยู่ในพอร์ต top 20%; `"sell"` = percentile ≤ 20 (สัญญาณแสดงผลเท่านั้น — กฎจริงเป็น long-only); `"hold"` = อื่น ๆ หรือใช้ไม่ได้ |
| `score` | percentile ภายใน universe ในช่วง [0, 1] (0.5 เมื่อ `applicable = False`) |
| `is_stub` | `False` |
| `score_0_100`, `signal`, `reasons`, `model_version`, `applicable` | ตามสเปก Phase 0; `reasons[0]` = ข้อความเตือนเสมอ |
| `disclaimer`, `rule`, `rebalance_date` | ข้อความเตือน, กฎที่ใช้, วัน rebalance ที่ใช้คะแนน |

## วิธีต่อเข้า sandbox (ยังไม่ได้แก้ไฟล์ใน `sandbox/` — ต้องให้ผู้ใช้อนุมัติ/ทำเอง)
1. รันจาก repo root เหมือนเดิม (`python3 -m sandbox.app.server`) — `model_A` import ได้เป็น namespace package
2. แก้ `sandbox/inference/model_a.py` ให้เหลือ:
   ```python
   from model_A.export.model_a_experimental import predict, IS_STUB  # noqa: F401
   ```
   และตั้ง `MODEL_A_RULE=rule2` ถ้าต้องการกฎอันดับ 2
3. `sandbox/scripts/smoke_test.py` บรรทัดที่ assert `model_a.is_stub is True` และ `model_a.IS_STUB is True` จะ fail — ต้องเปลี่ยนเป็น `False`
4. `sandbox/engine/combine.py` ใช้แค่ `class` → ทำงานได้ทันที; ถ้าจะแสดง `reasons`/`disclaimer` บนหน้า Dashboard ต้องเพิ่มใน `server.py` / `main.js`
   (แนะนำให้แสดง `disclaimer` ทุกครั้งที่แสดงผล Model A)
5. ทดสอบ: `python3 -c "from model_A.export.model_a_experimental import predict; print(predict('FDX','2023-01-03'))"`

## สร้างคะแนนใหม่
```bash
cd model_A && python3 -m export.build_scores   # ต้องมี data/interim (panel) — ไม่แตะ held-out
```
