# Model A — Rebuild from scratch (SPEC สำหรับ Claude Code)

> วิธีใช้: วางไฟล์นี้ที่ `~/Desktop/SNP-claude/model_A/SPEC.md` แล้วสั่ง Claude Code ว่า
> "อ่าน model_A/SPEC.md แล้วเริ่มที่ Phase 0 ถ้าไม่เข้าใจตรงไหนให้ถามก่อน"

## 0) เป้าหมาย

สร้าง Model A (Fundamental, rule-based) ของโปรเจค SNP ใหม่ทั้งหมด เพราะโค้ดเก่าจากเทอมที่แล้วถูกทิ้งไปหมดแล้ว
เริ่มจาก "วิธีเดิม" (Piotroski: BM ratio + F-score จากข้อมูล SEC) เพื่อให้ได้ baseline ที่เชื่อถือได้ แล้วค่อยเพิ่มสัญญาณใหม่ทีละเวอร์ชัน
ทุกเวอร์ชันเป็น Jupyter notebook แยกไฟล์ **รันครบและเก็บ output ไว้แล้ว** เพื่อให้ผู้ใช้เปิดอ่านผลได้เลย
ผลลัพธ์สุดท้ายต้องเสียบเข้า web test simulator (`sandbox/`) ที่ผู้ใช้พัฒนาเองได้

ผู้ใช้เป็นนักศึกษา data science ชอบคำอธิบายภาษาง่ายพร้อมอุปมา ชอบทำทีละขั้น และใช้ไทยปนอังกฤษ
**ถ้าไม่เข้าใจหรือไม่ชัดเจนตรงไหน ให้ถามผู้ใช้ก่อนทำ อย่าเดา**

## 1) หลักการทำงาน (ห้ามละเมิด)

1. ทุกตัวเลขต้องมาจากโค้ดที่รันจริง ห้ามเดาหรือแต่งผล
2. แยกป้ายให้ชัดในทุก notebook ว่าอะไรคือ "ทดสอบแล้ว" กับ "ไอเดียที่ยังไม่ลอง"
3. Pre-register ก่อนดูผล: เขียนเกณฑ์ผ่าน/ไม่ผ่านและช่วง held-out ลงใน `model_A/PREREG.md` แล้ว commit ก่อนรันผลของเวอร์ชันนั้น
4. ผลลบ (ไม่ชนะ benchmark) ก็รายงานตามจริง ถือเป็นข้อค้นพบที่ใช้ได้
5. นับจำนวน variant ที่ลองทั้งหมดใน `model_A/experiments_log.csv` (version, สิ่งที่เปลี่ยน, จำนวน variant สะสม) เพื่อประเมินความเสี่ยง multiple testing
6. ห้ามแตะโค้ด Model B / Model C ห้าม commit `.env` และข้อมูลดิบขนาดใหญ่
7. ทำงานบน branch ใหม่ เช่น `feature/model-a-rebuild` แล้ว `git commit` ทุกเวอร์ชัน

## 2) โครงสร้างโฟลเดอร์

```
model_A/
  SPEC.md                    (ไฟล์นี้)
  PREREG.md                  (เกณฑ์ผ่าน/ไม่ผ่านต่อเวอร์ชัน เขียนก่อนรัน)
  experiments_log.csv
  lib/                       (โค้ด .py ที่ notebook เรียกใช้: data loader, point-in-time, metrics, backtest)
  notebooks/
    v0_data_audit.ipynb
    v1_baseline_piotroski.ipynb
    v2_quality_value.ipynb
    v3_rule_engine.ipynb
    v4_growth_gscore.ipynb   (ทำเมื่อ v3 เสร็จและผู้ใช้อนุมัติ)
    v9_compare_all.ipynb
  reports/                   (สำเนา .html ของทุก notebook ที่รันแล้ว)
  export/                    (คะแนนต่อหุ้นต่อวัน + adapter สำหรับ sandbox)
```

## 3) Data hygiene (ตัวตัดสินว่าผลเชื่อถือได้ไหม)

- **Point-in-time:** ใช้วันที่ยื่นงบจริง (SEC `filed` date) ไม่ใช่วันสิ้นงวดบัญชี และเผื่อ lag ก่อนเอาไปใช้ตัดสินใจ กันไม่ให้มองอนาคต (look-ahead bias)
- **Survivorship:** ใช้รายชื่อสมาชิก S&P 500 ณ วันนั้น ไม่ใช่รายชื่อปัจจุบัน ถ้าหาข้อมูล historical constituents ไม่ได้ ต้องบอกผู้ใช้ตรง ๆ และใส่คำเตือนไว้ในทุกผลลัพธ์
- **Sector การเงิน:** สัญญาณบางตัว (Piotroski, Altman Z, gross profit) ใช้กับธนาคาร/ประกันไม่ได้ ต้องแยกออกมา ไม่ใช้กฎเดียวกันกับ sector อื่น
- ใช้ราคา adjusted (split/dividend), ตรวจ missing data และ outlier แล้วรายงานจำนวนแถวที่ตัดออกพร้อมเหตุผล
- ผลของ v0 ต้องตอบให้ได้ว่า ข้อมูลที่มีในโฟลเดอร์ `data/` ครอบคลุมช่วงเวลาไหน กี่ ticker และมีช่องว่างตรงไหน

## 4) แต่ละเวอร์ชันทำอะไร

**v0 data audit** สำรวจข้อมูลที่มี ตรวจ point-in-time และ survivorship สรุปว่าข้อมูลพอสำหรับเวอร์ชันถัดไปไหม

**v1 baseline Piotroski (วิธีเดิม)** สร้าง BM ratio และ F-score 9 ข้อใหม่จากข้อมูล SEC แล้วทำ ablation แยก 3 พอร์ต: BM สูงอย่างเดียว, F-score สูงอย่างเดียว, BM สูง + F-score สูง
เหตุผล: งานวิจัยกับ S&P 500 ชี้ว่า กำไรอาจมาจาก "ความถูก" (BM สูง) มากกว่า "คุณภาพ" (F-score) ต้องแยกให้เห็นว่าของเดิมชนะเพราะอะไร

**v2 quality + value** เพิ่มสัญญาณที่ยังไม่เคยลอง แล้วทดสอบทีละตัวก่อน (rank IC, quintile spread, แยกช่วงเวลา และแยก sector)
- Quality: gross profit / total assets (Novy-Marx), ROIC
- Value ทางเลือกแทน BM: earnings yield (หรือ EV/EBIT), FCF yield
- คุณภาพกำไรและการลงทุน: accruals, net share issuance, asset growth
- จัดอันดับภายใน sector (sector-neutral) เทียบกับจัดอันดับรวม

**v3 rule engine เต็มรูป** ต่อ 3 ชั้น
1. ตัวกรองความเสี่ยง: Altman Z (ไม่ใช้กับการเงิน), Beneish M-score
2. ให้คะแนนเป็นเสา: Quality, Value, Safety, Payout/Shareholder yield (รวมกันแบบ quality + value เพราะงานวิจัยพบว่าการรวมสองมุมช่วยเพิ่มผลมากกว่าใช้อย่างเดียว)
3. กฎแยกสำหรับกลุ่มการเงิน

**v4 growth (G-score)** สำหรับหุ้น BM ต่ำ ที่ Piotroski เดิมมองข้าม (งานต้นฉบับพบว่าผลส่วนใหญ่มาจากฝั่ง short ระวังตอนใช้กับพอร์ต long-only)

**v9 compare** เทียบทุกเวอร์ชันในตารางและกราฟเดียว พร้อมสรุปผ่าน/ไม่ผ่านตาม PREREG

## 5) วิธีประเมิน (ให้เสนอค่าเริ่มต้นแล้วถามผู้ใช้ยืนยันก่อนล็อกใน PREREG)

- Rebalance: รายปี (แบบ Piotroski) เป็นหลัก และลองรายไตรมาสเป็น variant ในเวอร์ชันหลัง ๆ
- น้ำหนัก: equal-weight ในพอร์ตที่เลือก
- ต้นทุนซื้อขาย: เสนอค่าสมมติ เช่น 10 bps ต่อข้าง แล้วให้ผู้ใช้ยืนยัน
- Benchmark: SPY, equal-weight S&P 500 (สร้างจาก universe เดียวกัน) และ Dow Jones กับ SET ให้ตรงกับที่เคยเปรียบเทียบไว้ ถ้ามีข้อมูล
- ทดสอบทั้ง Lumpsum และ DCA เหมือนเดิม
- ตัวชี้วัด: CAGR, volatility, Sharpe, max drawdown, turnover, rank IC, quintile spread, ผลแยกช่วงเวลา (sub-period) และแยก sector
- Held-out: กันช่วงท้ายของข้อมูลไว้ไม่แตะจนกว่าจะสรุป (เสนอ 3 ปีสุดท้าย ให้ผู้ใช้ยืนยัน)
- ข้อควรรู้จากงานวิจัย: สัญญาณสาธารณะมักอ่อนลงหลังตีพิมพ์ (ประมาณครึ่งหนึ่งในงาน McLean & Pontiff) แต่ไม่ได้ลดเหลือศูนย์ และประสิทธิภาพของ F-score ลดลงในช่วงหลังตามงาน Li & Mohanram (2019) จึงไม่ควรคาดหวังผลระดับงานต้นฉบับ

## 6) มาตรฐานของ notebook

- เซลล์แรกเป็น markdown ภาษาไทย: ทำอะไร ทำไม และอ่านผลอย่างไร (มีอุปมาง่าย ๆ)
- เซลล์สุดท้ายเป็นสรุปผล ข้อจำกัด และ "ทดสอบแล้ว vs ยังเป็นแค่ไอเดีย"
- โค้ดยาว ๆ ย้ายไป `lib/` ให้ notebook อ่านง่าย มี seed คงที่
- **ต้องรันจริงทั้งไฟล์ก่อนส่งมอบ** ด้วย `jupyter nbconvert --to notebook --execute --inplace` แล้วส่งออก `.html` ไปที่ `reports/` เพื่อให้เปิดอ่านง่าย
- ตารางสรุปตัวเลขสำคัญและกราฟแสดงผลใน notebook เลย

## 7) ต่อกับ web test simulator (`sandbox/`)

- **อ่านโค้ด `sandbox/` ก่อน** โดยเฉพาะ stub interface ของ Model A (ที่มี `is_stub: True`) แล้วทำ adapter ให้ตรงกับ interface นั้นเป๊ะ อย่าเดาโครงสร้าง
- Output ต่อหุ้นต่อวัน: คะแนน 0-100, สัญญาณ (buy / hold / avoid), เหตุผลรายกฎที่ทำให้ได้คะแนนนั้น (ให้ sandbox แสดงอธิบายได้), `is_stub: False`, เวอร์ชันของโมเดล
- เก็บคะแนนที่คำนวณไว้เป็นไฟล์ใน `export/` พร้อม adapter ใน `export/`
- ห้ามแก้ไฟล์ใน `sandbox/` จนกว่าจะแจ้งผู้ใช้และได้รับอนุมัติ

## 8) ลำดับงาน (หยุดให้ผู้ใช้ตรวจทุก phase, `git commit` แล้วค่อย `/clear`)

- **Phase 0:** สำรวจ repo (`CLAUDE.md`, `data/`, `src/`, `sandbox/`) แล้วสรุปให้ผู้ใช้ พร้อมถามคำถามด้านล่าง
- **Phase 1:** v0 data audit
- **Phase 2:** เขียน PREREG ของ v1, รัน v1 baseline
- **Phase 3:** v2, **Phase 4:** v3, **Phase 5:** v9 compare + adapter + ทดสอบใน sandbox
- v4 ทำเมื่อผู้ใช้อนุมัติ

## 9) คำถามที่ต้องถามผู้ใช้ก่อนเริ่ม (หลังสำรวจ repo แล้ว)

1. ข้อมูลใน `data/` มีอะไรบ้างที่ยังใช้ได้ (ข้อมูลงบ SEC, ราคา, รายชื่อ S&P 500) ถ้าขาดจะหาจากไหน (เช่น SEC EDGAR API, แหล่งราคาที่ใช้ได้)
2. มีข้อมูลรายชื่อสมาชิก S&P 500 ย้อนหลังไหม ถ้าไม่มีจะรับความเสี่ยง survivorship bias ไหมหรือจะหาเพิ่ม
3. ยืนยันค่าเริ่มต้นในข้อ 5 (ความถี่ rebalance, ต้นทุน, ช่วง held-out, benchmark) และเกณฑ์ผ่าน/ไม่ผ่านที่จะล็อกใน PREREG
4. Interface ของ Model A ใน `sandbox/` ที่ต้องต่อ ถ้าอ่านโค้ดแล้วยังมีจุดกำกวม
