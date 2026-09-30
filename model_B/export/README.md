# Model B export — วิธีเพิ่ม version ให้ sandbox v2 เห็น

ตอนนี้ **ยังไม่มี Model B จริง** (ไม่พบ weights ใน repo — ดู `sandbox/v2/RECON.md`) sandbox v2 ใช้ `B stub` ใน
`sandbox/v2/stubs/B/stub/` ไปก่อน

## เพิ่ม version แบบ precomputed (แนะนำ)
1. สร้างโฟลเดอร์ `model_B/export/<version>/`
2. ใส่ `signals.parquet` (หรือ `.csv`) ตาม contract:

   | column | type | ความหมาย |
   |---|---|---|
   | `date` | date | วันที่ข่าว/สัญญาณ **ใช้ได้ ณ close วันนั้น** (ข่าวหลังตลาดปิด → ใส่วันทำการถัดไป) |
   | `ticker` | str | ticker แบบ Yahoo (`BRK-B`) |
   | `class` | str | `positive` / `neutral` / `negative` (ต้องสอดคล้องกับ score: ≥1 positive, 0 neutral, ≤-1 negative) |
   | `score` | float | **ความแรงของข่าว -2..+2** (-2 negative แรงมาก · -1 negative · 0 ไม่ค่อยมีผล · +1 positive · +2 positive แรงมาก) — registry ปฏิเสธค่านอกช่วงเมื่อ applicable |
   | `applicable` | bool | False = โมเดลไม่ครอบคลุมหุ้นนี้ |
   | `reasons` | list[str] | เหตุผล เช่น headline + ผล FinBERT |
   | `model_version` | str | |
   | `is_stub` | bool | ต้องตรงกับ manifest |

3. ใส่ `manifest.json`:
   ```json
   {"model": "B", "version": "finbert-v1", "short_label": "B1", "display_name": "FinBERT company news v1",
    "rule_id": "finbert-v1", "is_stub": false, "result_badge": "real", "signal_files": ["signals.parquet"],
    "coverage": {"start": "2021-09-27", "end": "2023-06-30", "n_tickers": 480},
    "rebalance": "event", "asof": {"max_age_days": 10},
    "source_experiment": "exp_xx", "created_at": "2026-10-01T00:00:00Z", "notes": "..."}
   ```
   `asof.max_age_days` = สัญญาณหมดอายุหลังกี่วัน (ไม่มีข่าวใหม่ = ไม่มีสัญญาณ); `0` = point-in-time ใช้ได้เฉพาะวันที่มีข่าว
   `result_badge`: `real` (โมเดลจริง) · `stub` (สุ่ม) · `negative` (ผลทดสอบไม่ผ่าน) · `manual` (label จากผู้ใช้/Claude แบบไม่รู้ผลล่วงหน้า) · `oracle` (label ที่รู้ผลราคาจริงแล้ว — ใช้หาเพดานบนเท่านั้น)
5. กล่อง B ในหน้า Pipeline **ไม่กรองหุ้น** — แนบ record ให้ condition ผ่าน `ctx.b[ticker]`; หุ้นที่ไม่มีสัญญาณ ณ วันนั้น = `{"applicable": False, "score": None, "class": None}` (ไม่เดาค่า)
4. เปิดหน้า Registry ในเว็บ → กด **Rescan** → ถ้าไม่ผ่าน validation จะขึ้นในรายการ invalid พร้อมเหตุผล

## เพิ่ม version แบบ on-demand (รันเฉพาะหุ้นที่รอดจาก A)
- `manifest.json` ใส่ `"runtime": "on_demand"` และ `"signal_files": []`
- ใส่ `infer.py` ที่มี `def infer(tickers: list[str], dates: list[str]) -> pandas.DataFrame` (คืน column ตาม contract ข้างบน)
- ผลถูก cache ที่ `sandbox/v2/cache/` (gitignored) — ⚠️ interface นี้เตรียมไว้แล้วแต่ **ยังไม่เคยทดสอบกับโมเดลจริง**
